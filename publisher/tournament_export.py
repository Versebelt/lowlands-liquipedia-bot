"""Generate safe Liquipedia wikicode from the GeoNederland tournament API."""

from __future__ import annotations

import base64
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests


TEST_MARKER = "<!-- LOWLANDS_LEAGUE_MANAGED_TEST_PAGE -->"
SUPPORTED_BRACKET_SIZES = {2, 4, 8, 16, 32, 64}
AMSTERDAM = ZoneInfo("Europe/Amsterdam")


class TournamentExportError(RuntimeError):
    """A validation or retrieval error safe to show in Actions."""


@dataclass(frozen=True)
class TournamentSource:
    api_url: str
    secret: str
    tournament_id: str


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise TournamentExportError(f"Required environment value {name} is missing.")
    return value


def load_source() -> TournamentSource:
    tournament_id = required_env("TOURNAMENT_ID")
    if not re.fullmatch(r"[A-Za-z0-9-]{1,80}", tournament_id):
        raise TournamentExportError("TOURNAMENT_ID contains unsupported characters.")
    api_url = required_env("TOURNAMENT_API_URL")
    if not api_url.startswith("https://"):
        raise TournamentExportError("TOURNAMENT_API_URL must use HTTPS.")
    return TournamentSource(
        api_url=api_url,
        secret=required_env("TOURNAMENT_API_SECRET"),
        tournament_id=tournament_id,
    )


def fetch_tournament(source: TournamentSource) -> dict[str, Any]:
    query = urlencode(
        {
            "action": "public_tournament",
            "tournament_id": source.tournament_id,
            "secret": source.secret,
        }
    )
    separator = "&" if "?" in source.api_url else "?"
    try:
        response = requests.get(
            f"{source.api_url}{separator}{query}",
            headers={"User-Agent": "GeoNederlandTournamentBot/1.0 (https://geonederland.gg)"},
            timeout=(15, 60),
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, requests.JSONDecodeError) as exc:
        raise TournamentExportError(f"Could not retrieve tournament data: {exc}") from exc
    if not payload.get("ok"):
        raise TournamentExportError(str(payload.get("error") or "Tournament API rejected the request."))
    tournament = payload.get("tournament")
    if not isinstance(tournament, dict):
        raise TournamentExportError("Tournament API response does not contain a tournament object.")
    return tournament


def wiki_text(value: Any, *, fallback: str = "TBD", limit: int = 100) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = text.replace("{{", "(").replace("}}", ")").replace("|", "-")
    text = re.sub(r"\s+", " ", text).strip()
    return (text[:limit] or fallback)


def country_code(value: Any) -> str:
    return re.sub(r"[^a-z]", "", str(value or "").lower())[:3]


def parse_score(value: Any) -> tuple[str, str]:
    match = re.fullmatch(r"\s*(\d{1,2})\s*[-–:]\s*(\d{1,2})\s*", str(value or ""))
    return match.groups() if match else ("", "")


def match_date(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=AMSTERDAM)
        local = parsed.astimezone(AMSTERDAM)
    except ValueError:
        return ""
    abbreviation = "CEST" if local.dst() and local.dst().total_seconds() else "CET"
    return f"{local:%Y-%m-%d %H:%M} {{{{Abbr/{abbreviation}}}}}"


def validate_tournament(tournament: dict[str, Any]) -> int:
    size = int(tournament.get("bracket_size") or 0)
    if size not in SUPPORTED_BRACKET_SIZES:
        raise TournamentExportError(
            f"Unsupported bracket size {size}; expected one of {sorted(SUPPORTED_BRACKET_SIZES)}."
        )
    participants = tournament.get("participants")
    matches = tournament.get("matches")
    if not isinstance(participants, list) or not isinstance(matches, list):
        raise TournamentExportError("Tournament participants or matches are missing.")
    if len(matches) > size - 1:
        raise TournamentExportError("Tournament contains more matches than a single-elimination bracket permits.")
    bracket_id = str(tournament.get("liquipedia_bracket_id") or "")
    if not re.fullmatch(r"[A-Za-z0-9]{12}", bracket_id):
        raise TournamentExportError("Tournament does not have a valid persistent Liquipedia bracket ID.")
    return size


def participant_lines(tournament: dict[str, Any]) -> list[str]:
    participants = sorted(
        tournament.get("participants", []),
        key=lambda player: (int(player.get("seed") or 9999), wiki_text(player.get("player"))),
    )
    lines = ["==Participants==", "{{ParticipantTable|title=Participants"]
    for player in participants:
        name = wiki_text(player.get("player"))
        flag = country_code(player.get("country"))
        lines.append(f"|{{{{1Opponent|{name}|flag={flag}}}}}")
    lines.append("}}")
    return lines


def bracket_lines(tournament: dict[str, Any], size: int) -> list[str]:
    player_countries = {
        wiki_text(player.get("player")): country_code(player.get("country"))
        for player in tournament.get("participants", [])
    }
    matches = sorted(
        tournament.get("matches", []),
        key=lambda match: int(match.get("order") or 0),
    )
    rounds: list[str] = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for match in matches:
        round_name = wiki_text(match.get("round"), fallback="Round")
        if round_name not in grouped:
            rounds.append(round_name)
            grouped[round_name] = []
        grouped[round_name].append(match)

    expected_rounds = size.bit_length() - 1
    if len(rounds) > expected_rounds:
        raise TournamentExportError("Tournament contains too many rounds for its bracket size.")

    bracket_id = str(tournament["liquipedia_bracket_id"])
    lines = ["==Results==", f"{{{{Bracket|Bracket/{size}|id={bracket_id}"]
    for round_index, round_name in enumerate(rounds, start=1):
        lines.append("")
        lines.append(f"<!-- {round_name} -->")
        for match_index, match in enumerate(grouped[round_name], start=1):
            player1 = wiki_text(match.get("player1"))
            player2 = wiki_text(match.get("player2"))
            score1, score2 = parse_score(match.get("series_score"))
            finished = bool(match.get("winner")) or str(match.get("status", "")).lower() in {
                "complete", "completed", "finished"
            }
            date = match_date(match.get("scheduled_at"))
            flag1 = player_countries.get(player1, "")
            flag2 = player_countries.get(player2, "")
            lines.extend(
                [
                    f"|R{round_index}M{match_index}={{{{Match",
                    f"    |opponent1={{{{SoloOpponent|{player1}|flag={flag1}|score={score1}}}}}",
                    f"    |opponent2={{{{SoloOpponent|{player2}|flag={flag2}|score={score2}}}}}",
                    f"    |finished={'true' if finished else 'false'}" + (f" |date={date}" if date else ""),
                    "}}",
                ]
            )
    lines.append("}}")
    return lines


def build_wikicode(tournament: dict[str, Any]) -> str:
    size = validate_tournament(tournament)
    name = wiki_text(tournament.get("name"), fallback="GeoNederland Tournament", limit=160)
    lines = [
        TEST_MARKER,
        "<!-- Generated from the GeoNederland Tournament Admin sheet. -->",
        f"{{{{DISPLAYTITLE:{name}}}}}",
        "",
        f"'''{name}''' is a GeoNederland tournament.",
        "",
    ]
    lines.extend(participant_lines(tournament))
    lines.append("")
    lines.extend(bracket_lines(tournament, size))
    winner = wiki_text(tournament.get("winner"), fallback="", limit=100)
    if winner:
        lines.extend(["", "==Winner==", f"{{{{player|{winner}}}}}"])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    try:
        tournament = fetch_tournament(load_source())
        wikicode = build_wikicode(tournament)
        output_path = os.environ.get("TOURNAMENT_WIKICODE_PATH", "tournament-wikicode.txt")
        with open(output_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(wikicode)
        encoded = base64.b64encode(wikicode.encode("utf-8")).decode("ascii")
        github_output = os.environ.get("GITHUB_OUTPUT")
        if github_output:
            with open(github_output, "a", encoding="utf-8") as handle:
                handle.write(f"content_b64={encoded}\n")
                handle.write(f"tournament_name={wiki_text(tournament.get('name'), limit=160)}\n")
        print(json.dumps({"ok": True, "tournament": tournament.get("id"), "bytes": len(wikicode.encode('utf-8'))}))
        return 0
    except TournamentExportError as exc:
        print(f"::error::{exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

