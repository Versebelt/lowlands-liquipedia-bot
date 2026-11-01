"""Live data feeds and HTML overlays for the GeoGuessr livestream.

Everything here is read-only towards the league sheet and the tournament web
app, and only uses the public allowlisted tournament payload
(``public_tournament``), so party links and Discord identities never reach a
broadcast feed.

Feeds are served as flat rows (every value a string) because that is what vMix
Data Sources, GT Title fields, CasparCG templates, Unreal Engine and After
Effects data-driven templates all understand:

    /broadcast/feed/<name>.json   root array of objects
    /broadcast/feed/<name>.csv    header row + data rows
    /broadcast/feed/<name>.xml    <rows><row><field>value</field></row></rows>

The HTML overlays in ``broadcast_static`` poll the same JSON feeds.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from xml.sax.saxutils import escape

from aiohttp import web

from .sheets import PublicSheet, display_number, number
from .tournament import TournamentApi, TournamentError

STATIC_DIR = Path(__file__).with_name("broadcast_static")
OVERLAYS = ("scorebug", "matchup", "bracket", "schedule", "standings", "lowerthird", "ticker", "control")
FEEDS = ("match", "matches", "bracket", "schedule", "participants", "standings", "tournament", "control")
FLAG_URL = "https://flagcdn.com/w160/{code}.png"
DONE_STATUSES = {"complete", "disqualified"}
LIVE_STATUSES = {"live", "pending result"}
MAX_TEXT = 200

try:
    from zoneinfo import ZoneInfo

    AMSTERDAM = ZoneInfo("Europe/Amsterdam")
except Exception:  # pragma: no cover - tzdata missing on the host
    AMSTERDAM = timezone.utc


def text(value: object, limit: int = MAX_TEXT) -> str:
    """Return a single-line, length-limited string that is safe in any feed format."""
    cleaned = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value if value is not None else "")).strip()
    return cleaned[:limit]


def flag_url(country: str) -> str:
    code = re.sub(r"[^a-z]", "", str(country or "").lower())
    return FLAG_URL.format(code=code) if len(code) == 2 else ""


def https_url(value: object) -> str:
    url = text(value, 1000)
    return url if re.match(r"^https://[a-z0-9.-]+(?:[/:?#]\S*)?$", url, re.I) else ""


def parse_score(series_score: object) -> tuple[str, str]:
    found = re.match(r"^\s*(\d{1,2})\s*[-–:]\s*(\d{1,2})\s*$", str(series_score or ""))
    return (found.group(1), found.group(2)) if found else ("0", "0")


def local_time(iso: object, pattern: str = "%H:%M") -> str:
    raw = str(iso or "").strip()
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(AMSTERDAM).strftime(pattern)


DAYS = ("ma", "di", "wo", "do", "vr", "za", "zo")
MONTHS = ("jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec")


def dutch_day(iso: object) -> str:
    """Locale-independent Dutch date such as 'za 12 dec'."""
    stamp = local_time(iso, "%w %d %m")
    if not stamp:
        return ""
    weekday, day, month = (int(part) for part in stamp.split())
    return f"{DAYS[(weekday - 1) % 7]} {day} {MONTHS[month - 1]}"


def is_done(match: dict[str, Any]) -> bool:
    return str(match.get("status") or "").strip().lower() in DONE_STATUSES or bool(match.get("winner"))


def is_bye(name: object) -> bool:
    return str(name or "").strip().upper() in {"BYE", ""}


# --------------------------------------------------------------------------
# Row builders. Pure functions: tournament payload / sheet rows in, rows out.
# --------------------------------------------------------------------------


def _participants_by_name(tournament: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item.get("player") or ""): item for item in tournament.get("participants") or []}


def match_row(match: dict[str, Any], tournament: dict[str, Any], control: dict[str, str] | None = None) -> dict[str, str]:
    control = control or {}
    people = _participants_by_name(tournament)
    best_of = int(number(match.get("best_of")) or tournament.get("default_best_of") or 3)
    score1, score2 = parse_score(match.get("series_score"))
    # Live per-game score from the control panel, until the sheet has the official result.
    if control.get("match_id") and control.get("match_id") == match.get("match_id") and not is_done(match):
        score1 = control.get("p1_score") or score1
        score2 = control.get("p2_score") or score2
    winner = text(match.get("winner"))
    row = {
        "tournament": text(tournament.get("name")),
        "match_id": text(match.get("match_id")),
        "round": text(match.get("round")),
        "best_of": str(best_of),
        "first_to": str(best_of // 2 + 1),
        "format": f"Best of {best_of}",
        "status": text(match.get("status")),
        "live": "1" if str(match.get("status") or "").strip().lower() in LIVE_STATUSES else "",
        "scheduled": local_time(match.get("scheduled_at")),
        "scheduled_day": dutch_day(match.get("scheduled_at")),
        "series_score": f"{score1}-{score2}",
        "winner": winner,
    }
    for side in ("1", "2"):
        name = text(match.get(f"player{side}") or "TBD")
        person = people.get(name, {})
        country = text(person.get("country"), 3).upper()
        row.update({
            f"p{side}_name": name,
            f"p{side}_name_upper": name.upper(),
            f"p{side}_seed": str(person.get("seed") or ""),
            f"p{side}_country": country,
            f"p{side}_flag": flag_url(country),
            f"p{side}_avatar": https_url(match.get(f"player{side}_avatar_url") or person.get("avatar_url")),
            f"p{side}_score": score1 if side == "1" else score2,
            f"p{side}_winner": "1" if winner and winner == name else "",
        })
    return row


def featured_match(tournament: dict[str, Any], match_id: str = "") -> dict[str, Any] | None:
    """Pick the match the stream is about.

    An explicit match ID wins. Otherwise: a highlighted match that is running,
    then the next highlighted match, then the last finished highlighted match,
    and finally the first open match of the bracket.
    """
    matches = sorted(tournament.get("matches") or [], key=lambda item: int(number(item.get("order"))))
    if match_id:
        wanted = match_id.strip().upper()
        for match in matches:
            if str(match.get("match_id") or "").upper() == wanted:
                return match
    highlighted = [match for match in matches if match.get("highlighted")]
    for match in highlighted:
        if str(match.get("status") or "").strip().lower() in LIVE_STATUSES and not is_done(match):
            return match
    for match in highlighted:
        if not is_done(match):
            return match
    if highlighted:
        return highlighted[-1]
    for match in matches:
        if not is_done(match) and not (is_bye(match.get("player1")) or is_bye(match.get("player2"))):
            return match
    return matches[-1] if matches else None


def empty_match_row(tournament: dict[str, Any]) -> dict[str, str]:
    return match_row({"player1": "TBD", "player2": "TBD", "status": "No match"}, tournament)


def match_feed(tournament: dict[str, Any], control: dict[str, str] | None = None, match_id: str = "") -> list[dict[str, str]]:
    control = control or {}
    chosen = featured_match(tournament, match_id or control.get("match_id", ""))
    return [match_row(chosen, tournament, control) if chosen else empty_match_row(tournament)]


def matches_feed(tournament: dict[str, Any], control: dict[str, str] | None = None) -> list[dict[str, str]]:
    matches = sorted(tournament.get("matches") or [], key=lambda item: int(number(item.get("order"))))
    rows = []
    for index, match in enumerate(matches, start=1):
        row = match_row(match, tournament, control)
        row["order"] = str(index)
        row["highlighted"] = "1" if match.get("highlighted") else ""
        row["done"] = "1" if is_done(match) else ""
        rows.append(row)
    return rows


def bracket_feed(tournament: dict[str, Any], control: dict[str, str] | None = None) -> list[dict[str, str]]:
    """All matches with their round column and slot, ready for a bracket layout."""
    rounds = [str(item) for item in tournament.get("rounds") or []]
    rows = matches_feed(tournament, control)
    slot: dict[str, int] = {}
    for row in rows:
        if row["round"] not in rounds:
            rounds.append(row["round"])
        slot[row["round"]] = slot.get(row["round"], 0) + 1
        row["round_index"] = str(rounds.index(row["round"]) + 1)
        row["round_count"] = str(len(tournament.get("rounds") or rounds))
        row["slot"] = str(slot[row["round"]])
    return rows


def schedule_feed(tournament: dict[str, Any], limit: int = 8) -> list[dict[str, str]]:
    """Upcoming and running matches, live first, then by scheduled time and bracket order."""
    matches = [
        match for match in tournament.get("matches") or []
        if not is_done(match) and not (is_bye(match.get("player1")) or is_bye(match.get("player2")))
    ]

    def key(match: dict[str, Any]) -> tuple[int, str, int]:
        live = str(match.get("status") or "").strip().lower() in LIVE_STATUSES
        return (0 if live else 1, str(match.get("scheduled_at") or "9999"), int(number(match.get("order"))))

    return [match_row(match, tournament) for match in sorted(matches, key=key)[: max(1, limit)]]


def participants_feed(tournament: dict[str, Any]) -> list[dict[str, str]]:
    placements = [str(name) for name in tournament.get("placements") or []]
    rows = []
    for person in sorted(tournament.get("participants") or [], key=lambda item: int(number(item.get("seed")) or 999)):
        name = text(person.get("player"))
        country = text(person.get("country"), 3).upper()
        rows.append({
            "seed": str(person.get("seed") or ""),
            "player": name,
            "player_upper": name.upper(),
            "country": country,
            "flag": flag_url(country),
            "avatar": https_url(person.get("avatar_url")),
            "placement": str(placements.index(name) + 1) if name in placements else "",
        })
    return rows


def tournament_feed(tournament: dict[str, Any], control: dict[str, str] | None = None) -> list[dict[str, str]]:
    control = control or {}
    matches = tournament.get("matches") or []
    done = sum(1 for match in matches if is_done(match))
    open_rounds = [str(match.get("round")) for match in sorted(matches, key=lambda m: int(number(m.get("order")))) if not is_done(match)]
    return [{
        "tournament": text(tournament.get("name")),
        "tournament_upper": text(tournament.get("name")).upper(),
        "status": text(tournament.get("status")),
        "phase": text(tournament.get("phase")),
        "format": text(tournament.get("type")),
        "players": str(tournament.get("participant_count") or len(tournament.get("participants") or [])),
        "matches_total": str(len(matches)),
        "matches_done": str(done),
        "current_round": text(open_rounds[0]) if open_rounds else "",
        "winner": text(tournament.get("winner")),
        "start": local_time(tournament.get("start_at"), "%d-%m-%Y %H:%M"),
        "caster_1": text(control.get("caster_1")),
        "caster_2": text(control.get("caster_2")),
        "ticker": text(control.get("ticker"), 500),
    }]


def standings_feed(rows: list[dict[str, str]], limit: int = 16) -> list[dict[str, str]]:
    result = []
    for row in rows[: max(1, limit)]:
        country = text(row.get("country"), 3).upper()
        result.append({
            "rank": text(row.get("rank")),
            "player": text(row.get("player")),
            "player_upper": text(row.get("player")).upper(),
            "country": country,
            "flag": flag_url(country),
            "points": display_number(row.get("points")),
            "weeks": text(row.get("weeks")),
            "moving": display_number(row.get("moving")),
            "nm": display_number(row.get("nm")),
            "nmpz": display_number(row.get("nmpz")),
            "playoffs": text(row.get("playoffs")),
        })
    return result


# --------------------------------------------------------------------------
# Output formats
# --------------------------------------------------------------------------


def to_csv(rows: list[dict[str, str]]) -> str:
    buffer = io.StringIO()
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return buffer.getvalue()


def to_xml(rows: list[dict[str, str]]) -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<rows>"]
    for row in rows:
        fields = "".join(f"<{key}>{escape(str(value))}</{key}>" for key, value in row.items())
        lines.append(f"  <row>{fields}</row>")
    lines.append("</rows>")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Data source with caching, single-flight refresh and stale-on-error
# --------------------------------------------------------------------------


@dataclass
class CachedValue:
    loader: Callable[[], Any]
    seconds: float
    value: Any = None
    loaded_at: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def get(self) -> tuple[Any, bool]:
        """Return (value, stale). A failed refresh keeps the last good value on air."""
        if self.value is not None and time.monotonic() - self.loaded_at < self.seconds:
            return self.value, False
        async with self.lock:
            if self.value is not None and time.monotonic() - self.loaded_at < self.seconds:
                return self.value, False
            try:
                self.value = await asyncio.to_thread(self.loader)
                self.loaded_at = time.monotonic()
                return self.value, False
            except Exception as exc:
                if self.value is None:
                    raise
                logging.warning("Broadcast refresh failed, serving last good data: %s", exc)
                # Retry after a short pause instead of on every request.
                self.loaded_at = time.monotonic() - self.seconds + min(self.seconds, 5)
                return self.value, True


class BroadcastData:
    def __init__(self, sheet: PublicSheet, tournament_api: TournamentApi, cache_seconds: float | None = None) -> None:
        self.sheet = sheet
        self.api = tournament_api
        self.cache_seconds = cache_seconds if cache_seconds is not None else float(os.environ.get("BROADCAST_CACHE_SECONDS", "8"))
        self.fixed_tournament = os.environ.get("BROADCAST_TOURNAMENT_ID", "").strip()
        self.control_secret = os.environ.get("BROADCAST_CONTROL_SECRET", "").strip()
        self.control: dict[str, str] = {}
        self._tournaments: dict[str, CachedValue] = {}
        self._active = CachedValue(self._load_active_id, 60)
        self._standings = CachedValue(self.sheet.standings, max(self.cache_seconds, 60))

    def _load_active_id(self) -> str:
        config = self.api.bracket().get("config") or {}
        active = str(config.get("Tournament ID") or "").strip()
        if not active:
            raise TournamentError("No active tournament is configured.")
        return active

    async def tournament_id(self, requested: str = "") -> str:
        wanted = (requested or self.control.get("tournament_id") or self.fixed_tournament).strip()
        if wanted:
            if not re.fullmatch(r"[A-Za-z0-9-]{1,80}", wanted):
                raise TournamentError("Invalid tournament ID.")
            return wanted
        active, _ = await self._active.get()
        return active

    async def tournament(self, requested: str = "") -> tuple[dict[str, Any], bool]:
        tournament_id = await self.tournament_id(requested)
        cached = self._tournaments.get(tournament_id)
        if cached is None:
            cached = CachedValue(
                lambda: self.api.get("public_tournament", tournament_id=tournament_id).get("tournament") or {},
                self.cache_seconds,
            )
            self._tournaments[tournament_id] = cached
        return await cached.get()

    async def standings(self) -> tuple[list[dict[str, str]], bool]:
        return await self._standings.get()

    async def feed(self, name: str, query: dict[str, str]) -> tuple[list[dict[str, str]], bool]:
        limit = int(number(query.get("limit")) or 0)
        if name == "standings":
            rows, stale = await self.standings()
            return standings_feed(rows, limit or 16), stale
        if name == "control":
            return [self.public_control()], False
        tournament, stale = await self.tournament(query.get("tournament", ""))
        if name == "match":
            return match_feed(tournament, self.control, query.get("match", "")), stale
        if name == "matches":
            return matches_feed(tournament, self.control), stale
        if name == "bracket":
            return bracket_feed(tournament, self.control), stale
        if name == "schedule":
            return schedule_feed(tournament, limit or 8), stale
        if name == "participants":
            return participants_feed(tournament), stale
        if name == "tournament":
            return tournament_feed(tournament, self.control), stale
        raise web.HTTPNotFound(text="Unknown feed.")

    def public_control(self) -> dict[str, str]:
        keys = ("tournament_id", "match_id", "p1_score", "p2_score", "caster_1", "caster_2", "ticker",
                "lower_title", "lower_subtitle", "lower_visible", "updated_at")
        return {key: text(self.control.get(key), 500) for key in keys}

    def update_control(self, payload: dict[str, Any]) -> dict[str, str]:
        allowed = {
            "tournament_id": 80, "match_id": 40, "p1_score": 2, "p2_score": 2, "caster_1": 60,
            "caster_2": 60, "ticker": 500, "lower_title": 80, "lower_subtitle": 120, "lower_visible": 1,
        }
        for key, limit in allowed.items():
            if key not in payload:
                continue
            value = text(payload.get(key), limit)
            if key in {"p1_score", "p2_score", "lower_visible"} and value and not value.isdigit():
                raise ValueError(f"{key} must be a number.")
            if key in {"tournament_id", "match_id"} and value and not re.fullmatch(r"[A-Za-z0-9-]+", value):
                raise ValueError(f"{key} may only contain letters, digits and dashes.")
            self.control[key] = value
        self.control["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return self.public_control()


# --------------------------------------------------------------------------
# HTTP routes
# --------------------------------------------------------------------------

CORS = {"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"}


def _respond(rows: list[dict[str, str]], extension: str, stale: bool) -> web.Response:
    headers = dict(CORS)
    if stale:
        headers["X-Broadcast-Stale"] = "1"
    if extension == "csv":
        return web.Response(text=to_csv(rows), content_type="text/csv", charset="utf-8", headers=headers)
    if extension == "xml":
        return web.Response(text=to_xml(rows), content_type="application/xml", charset="utf-8", headers=headers)
    return web.Response(text=json.dumps(rows, ensure_ascii=False), content_type="application/json", charset="utf-8", headers=headers)


def setup_routes(app: web.Application, data: BroadcastData) -> None:
    async def feed(request: web.Request) -> web.Response:
        name, extension = request.match_info["name"], request.match_info["ext"]
        if name not in FEEDS:
            raise web.HTTPNotFound(text="Unknown feed.")
        try:
            rows, stale = await data.feed(name, dict(request.query))
        except web.HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 - never put internal errors on air
            logging.warning("Broadcast feed %s failed: %s", name, exc)
            return web.json_response({"error": "Feed temporarily unavailable."}, status=503, headers=CORS)
        return _respond(rows, extension, stale)

    async def overlay(request: web.Request) -> web.FileResponse:
        name = request.match_info["name"]
        if name not in OVERLAYS:
            raise web.HTTPNotFound(text="Unknown overlay.")
        return web.FileResponse(STATIC_DIR / f"{name}.html", headers={"Cache-Control": "no-cache"})

    async def asset(request: web.Request) -> web.FileResponse:
        name = request.match_info["name"]
        if name not in {"overlay.css", "overlay.js"}:
            raise web.HTTPNotFound()
        return web.FileResponse(STATIC_DIR / name, headers={"Cache-Control": "no-cache"})

    async def index(_: web.Request) -> web.FileResponse:
        return web.FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    async def control(request: web.Request) -> web.Response:
        if not data.control_secret:
            return web.json_response({"error": "BROADCAST_CONTROL_SECRET is not configured."}, status=503)
        supplied = request.headers.get("X-Broadcast-Secret", "")
        if not secrets.compare_digest(supplied.encode(), data.control_secret.encode()):
            return web.json_response({"error": "Wrong control secret."}, status=403)
        try:
            payload = await request.json()
            if not isinstance(payload, dict):
                raise ValueError("Expected a JSON object.")
            return web.json_response(data.update_control(payload), headers={"Cache-Control": "no-store"})
        except (ValueError, json.JSONDecodeError) as exc:
            return web.json_response({"error": str(exc)}, status=400)

    async def redirect(_: web.Request) -> web.Response:
        raise web.HTTPFound("/broadcast/")

    app.router.add_get("/broadcast", redirect)
    app.router.add_get("/broadcast/", index)
    app.router.add_get(r"/broadcast/feed/{name}.{ext:(json|csv|xml)}", feed)
    app.router.add_get("/broadcast/overlay/{name}", overlay)
    app.router.add_get("/broadcast/assets/{name}", asset)
    app.router.add_post("/broadcast/control", control)
