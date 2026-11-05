"""Tournament announcements: what the bot posts when the Admin sheet changes.

Pure functions only: the bot polls the tournament API (action=bracket) and feeds the matches in here. The first poll
after a (re)start is a baseline, so a restart never repeats old announcements. Messages never contain mentions,
party links or Discord IDs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

PRE_START = {"", "Waiting for opponent", "Waiting for players", "Waiting for broadcast", "Ready to start"}
REMINDER_BEFORE = timedelta(minutes=15)
EMPTY = {"", "TBD", "BYE"}


@dataclass
class MatchState:
    done: set[str] = field(default_factory=set)


State = dict[str, MatchState]


def _names(match: dict[str, Any]) -> tuple[str, str]:
    return str(match.get("player1") or "").strip(), str(match.get("player2") or "").strip()


def _playable(match: dict[str, Any]) -> bool:
    one, two = _names(match)
    return one not in EMPTY and two not in EMPTY


def _scheduled(match: dict[str, Any]) -> datetime | None:
    value = str(match.get("scheduled_at") or "").strip()
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _best_of(match: dict[str, Any]) -> str:
    try:
        best_of = int(match.get("best_of") or 0)
    except (TypeError, ValueError):
        return ""
    return f"best of {best_of}" if best_of > 1 else ""


def _is_stream(match: dict[str, Any]) -> bool:
    return bool(match.get("highlighted")) and (bool(match.get("admin_released")) or str(match.get("status")) == "Live")


def _is_result(match: dict[str, Any]) -> bool:
    return str(match.get("status")) == "Complete" and bool(str(match.get("winner") or "").strip())


def _reminder_due(match: dict[str, Any], now: datetime) -> bool:
    start = _scheduled(match)
    return bool(start) and str(match.get("status") or "") in PRE_START and now < start <= now + REMINDER_BEFORE


def _https(value: object) -> str:
    text = str(value or "").strip()
    return text if text.startswith("https://") else ""


def is_hidden(config: dict[str, Any] | None) -> bool:
    """Visibility Hidden in the Tournaments tab: a practice run that stays out of public channels."""
    return str((config or {}).get("Visibility") or "").strip().lower() == "hidden"


HIDDEN_PREFIX = "\N{LOCK} **Hidden tournament** (only admins see this) \N{EM DASH} "
NOT_PUBLIC = "There is no public tournament right now."


def baseline(matches: list[dict[str, Any]], now: datetime) -> State:
    """Everything that is already true counts as announced."""
    state: State = {}
    for match in matches:
        done = set()
        if _is_stream(match):
            done.add("stream")
        if _is_result(match):
            done.add("result")
        if _reminder_due(match, now) or (_scheduled(match) or now) < now:
            done.add("reminder")
        state[str(match.get("match_id") or "")] = MatchState(done)
    return state


def next_opponent(matches: list[dict[str, Any]], winner: str, after: str) -> str:
    """The winner's next opponent, if that match already has one."""
    for match in matches:
        if str(match.get("match_id")) == after or str(match.get("status")) == "Complete":
            continue
        one, two = _names(match)
        if winner in (one, two):
            other = two if one == winner else one
            return "" if other in EMPTY else other
    return ""


def announcements(
    state: State, matches: list[dict[str, Any]], now: datetime, stream_url: str = ""
) -> tuple[list[str], State]:
    """New messages since the previous poll, and the updated state."""
    messages: list[str] = []
    new_state: State = {}
    for match in matches:
        match_id = str(match.get("match_id") or "")
        if not match_id:
            continue
        done = set(state.get(match_id, MatchState()).done)
        one, two = _names(match)
        round_name = str(match.get("round") or "").strip()
        details = ", ".join(part for part in (round_name, _best_of(match)) if part)
        if _playable(match) and _is_stream(match) and "stream" not in done:
            done.add("stream")
            url = _https(match.get("stream_url")) or _https(stream_url)
            text = f"**Now on stream:** {one} vs {two}" + (f" ({details})" if details else "")
            messages.append(text + (f"\nWatch live: <{url}>" if url else ""))
        if _is_result(match) and "result" not in done:
            done.add("result")
            winner = str(match.get("winner")).strip()
            loser = two if winner == one else one
            score = str(match.get("series_score") or "").strip()
            if score and winner == two and "-" in score:
                # The sheet stores Player 1 - Player 2; show the winner's score first.
                score = "-".join(reversed(score.split("-", 1)))
            text = f"**Result:** **{winner}** beats {loser}" + (f" {score}" if score else "") + (f" ({round_name})" if round_name else "") + "."
            opponent = next_opponent(matches, winner, match_id)
            messages.append(text + (f" Next up for {winner}: {opponent}." if opponent else ""))
        if _playable(match) and _reminder_due(match, now) and "reminder" not in done:
            done.add("reminder")
            start = _scheduled(match)
            when = f"<t:{int(start.timestamp())}:t>" if start else ""
            messages.append(f"**Starting soon:** {one} vs {two}" + (f" ({details})" if details else "") + (f" at {when}." if when else "."))
        new_state[match_id] = MatchState(done)
    return messages, new_state


def results_text(matches: list[dict[str, Any]], tournament_name: str = "") -> str:
    """Completed matches of the active tournament, for /uitslagen."""
    lines = []
    for match in matches:
        if not _is_result(match):
            continue
        one, two = _names(match)
        winner = str(match.get("winner")).strip()
        score = str(match.get("series_score") or "").strip()
        bold = lambda name: f"**{name}**" if name == winner else name  # noqa: E731
        round_name = str(match.get("round") or "").strip()
        lines.append((f"{round_name}: " if round_name else "") + f"{bold(one)} {score or 'vs'} {bold(two)}")
    if not lines:
        return "No completed matches yet."
    return "\n".join(([f"**{tournament_name}**"] if tournament_name else []) + lines)
