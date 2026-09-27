"""Send one scheduled Lowlands League reminder through a Discord webhook."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable
from zoneinfo import ZoneInfo


AMSTERDAM = ZoneInfo("Europe/Amsterdam")
DEFAULT_SEASON_START = date(2026, 9, 7)
DEFAULT_SEASON_WEEKS = 10
DEFAULT_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "15lCX6ljpsGh6bwzHZcctb24DIn-r4wqRGt6gZtLE_k4"
)


class ReminderError(RuntimeError):
    """Raised when reminder configuration or delivery is invalid."""


@dataclass(frozen=True)
class Config:
    webhook_url: str
    generic_role_id: str
    player_user_ids: tuple[str, ...]
    season_start: date
    season_weeks: int
    sheet_url: str


def clean_snowflake(value: str, mention_prefix: str = "") -> str:
    snowflake = value.strip()
    if mention_prefix and snowflake.startswith(mention_prefix) and snowflake.endswith(">"):
        snowflake = snowflake[len(mention_prefix) : -1]
    if snowflake and not snowflake.isdigit():
        raise ReminderError(f"Invalid Discord ID: {value!r}")
    return snowflake


def parse_ids(value: str, mention_prefix: str = "") -> tuple[str, ...]:
    seen: set[str] = set()
    role_ids: list[str] = []
    for item in value.replace("\n", ",").split(","):
        role_id = clean_snowflake(item, mention_prefix)
        if role_id and role_id not in seen:
            seen.add(role_id)
            role_ids.append(role_id)
    return tuple(role_ids)


def load_config() -> Config:
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook_url.startswith("https://discord.com/api/webhooks/"):
        raise ReminderError("DISCORD_WEBHOOK_URL is missing or invalid.")

    generic_role_id = clean_snowflake(
        os.environ.get("DISCORD_GENERIC_ROLE_ID", ""), "<@&"
    )
    if not generic_role_id:
        raise ReminderError("DISCORD_GENERIC_ROLE_ID is missing.")

    try:
        season_start = date.fromisoformat(
            os.environ.get("LOWLANDS_SEASON_START", DEFAULT_SEASON_START.isoformat())
        )
        season_weeks = int(
            os.environ.get("LOWLANDS_SEASON_WEEKS", str(DEFAULT_SEASON_WEEKS))
        )
    except ValueError as exc:
        raise ReminderError(f"Invalid season configuration: {exc}") from exc

    return Config(
        webhook_url=webhook_url,
        generic_role_id=generic_role_id,
        player_user_ids=parse_ids(
            os.environ.get("DISCORD_PLAYER_USER_IDS", ""), "<@"
        ),
        season_start=season_start,
        season_weeks=season_weeks,
        sheet_url=os.environ.get("LOWLANDS_PUBLIC_SHEET_URL", DEFAULT_SHEET_URL).strip(),
    )


def current_week(today: date, season_start: date, season_weeks: int) -> int | None:
    delta = (today - season_start).days
    week = delta // 7 + 1
    return week if 1 <= week <= season_weeks else None


def resolve_kind(requested: str, now: datetime) -> str:
    if requested != "auto":
        return requested
    by_weekday = {0: "open", 4: "friday", 6: "sunday"}
    try:
        return by_weekday[now.weekday()]
    except KeyError as exc:
        raise ReminderError("Automatic reminder ran on an unsupported weekday.") from exc


def user_mentions(user_ids: Iterable[str]) -> str:
    return " ".join(f"<@{user_id}>" for user_id in user_ids)


def build_message(
    kind: str, week: int, config: Config
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    generic = f"<@&{config.generic_role_id}>"
    if kind == "open":
        content = (
            f"{generic}\n\n"
            f"**Week {week} is now open!**\n"
            "The five seeds are ready. Please complete all of them before "
            "Sunday at 23:59 (Europe/Amsterdam).\n\n"
            f"**Results and information:** {config.sheet_url}"
        )
        allowed = (config.generic_role_id,)
    elif kind == "friday":
        content = (
            f"{generic}\n\n"
            f"**Week {week} reminder**\n"
            "If you have not played all five seeds yet, please remember to do so. "
            "The deadline is Sunday at 23:59 (Europe/Amsterdam).\n\n"
            f"**Results and information:** {config.sheet_url}"
        )
        allowed = (config.generic_role_id,)
    elif kind == "sunday":
        if not config.player_user_ids:
            raise ReminderError(
                "DISCORD_PLAYER_USER_IDS is empty; refusing to send the Sunday reminder."
            )
        mentions = user_mentions(config.player_user_ids)
        content = (
            f"{mentions}\n\n"
            f"**Final reminder for Week {week}**\n"
            "Today is the final day to complete any remaining seeds. "
            "The deadline is 23:59 (Europe/Amsterdam).\n\n"
            f"**Results and information:** {config.sheet_url}"
        )
        allowed_roles = ()
        allowed_users = config.player_user_ids
    else:
        raise ReminderError(f"Unsupported reminder kind: {kind}")

    if len(content) > 2000:
        raise ReminderError(
            f"Discord message is {len(content)} characters; the maximum is 2000."
        )
    if kind != "sunday":
        allowed_roles = allowed
        allowed_users = ()
    return content, allowed_roles, allowed_users


def payload_for(
    content: str,
    allowed_role_ids: Iterable[str],
    allowed_user_ids: Iterable[str],
) -> dict[str, object]:
    return {
        "content": content,
        "username": "Lowlands League",
        "allowed_mentions": {
            "parse": [],
            "roles": list(allowed_role_ids),
            "users": list(allowed_user_ids),
            "replied_user": False,
        },
    }


def send_webhook(webhook_url: str, payload: dict[str, object]) -> None:
    separator = "&" if "?" in webhook_url else "?"
    request = urllib.request.Request(
        f"{webhook_url}{separator}wait=true",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Lowlands-League-Reminder/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status not in (200, 204):
                raise ReminderError(f"Discord returned HTTP {response.status}.")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise ReminderError(f"Discord returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ReminderError(f"Discord request failed: {exc.reason}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--kind",
        choices=("auto", "open", "friday", "sunday"),
        default="auto",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the payload without contacting Discord.",
    )
    args = parser.parse_args()

    try:
        config = load_config()
        now = datetime.now(AMSTERDAM)
        week = current_week(now.date(), config.season_start, config.season_weeks)
        if week is None:
            print("No reminder sent: today is outside the configured regular season.")
            return 0

        kind = resolve_kind(args.kind, now)
        content, allowed_roles, allowed_users = build_message(kind, week, config)
        payload = payload_for(content, allowed_roles, allowed_users)
        if args.dry_run:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0

        send_webhook(config.webhook_url, payload)
        print(
            f"Discord reminder sent successfully: kind={kind}, week={week}, "
            f"role_mentions={len(allowed_roles)}, user_mentions={len(allowed_users)}"
        )
        return 0
    except ReminderError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
