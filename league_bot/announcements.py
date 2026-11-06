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
# The broadcast run of show sets Expected At when the evening runs late (or early); from this difference with
# Scheduled At the bot tells the players, and again only after another shift of at least this much.
SHIFT_NOTICE = timedelta(minutes=10)
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


def _time(match: dict[str, Any], field_name: str) -> datetime | None:
    value = str(match.get(field_name) or "").strip()
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _scheduled(match: dict[str, Any]) -> datetime | None:
    return _time(match, "scheduled_at")


def _start(match: dict[str, Any]) -> datetime | None:
    """When the match really starts: the expected time from the broadcast if there is one, else the scheduled time."""
    return _time(match, "expected_at") or _scheduled(match)


def _shift(match: dict[str, Any]) -> datetime | None:
    """The expected time if it differs enough from the schedule to tell the players, else None."""
    expected, scheduled = _time(match, "expected_at"), _scheduled(match)
    if not expected or not scheduled or abs(expected - scheduled) < SHIFT_NOTICE:
        return None
    return expected


def _shift_told(done: set[str], expected: datetime) -> bool:
    """Already told the players about (about) this expected time."""
    for item in done:
        if item.startswith("shift:"):
            try:
                told = datetime.fromtimestamp(int(item[6:]), timezone.utc)
            except ValueError:
                continue
            if abs(told - expected) < SHIFT_NOTICE:
                return True
    return False


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
    start = _start(match)
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
        if _reminder_due(match, now) or (_start(match) or now) < now:
            done.add("reminder")
        shift = _shift(match)
        if shift:
            done.add(f"shift:{int(shift.timestamp())}")
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
        shift = _shift(match)
        if (_playable(match) and shift and shift > now and str(match.get("status") or "") in PRE_START
                and not _shift_told(done, shift)):
            done.add(f"shift:{int(shift.timestamp())}")
            scheduled = _scheduled(match)
            word = "later" if scheduled and shift > scheduled else "earlier"
            planned = f" (planned <t:{int(scheduled.timestamp())}:t>)" if scheduled else ""
            messages.append(f"**Schedule update:** {one} vs {two} now starts {word}, around <t:{int(shift.timestamp())}:t>{planned}.")
        if _playable(match) and _reminder_due(match, now) and "reminder" not in done:
            done.add("reminder")
            start = _start(match)
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
