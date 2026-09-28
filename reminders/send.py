"""Resolve sheet-provided Discord names and send one seed reminder."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable


API_BASE = "https://discord.com/api/v10"
DEFAULT_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "15lCX6ljpsGh6bwzHZcctb24DIn-r4wqRGt6gZtLE_k4"
)


class ReminderError(RuntimeError):
    """Raised when reminder configuration, resolution, or delivery is invalid."""


@dataclass(frozen=True)
class Config:
    bot_token: str
    guild_id: str
    channel_id: str
    generic_role_id: str
    sheet_url: str


def clean_snowflake(value: str) -> str:
    snowflake = value.strip()
    if snowflake and not snowflake.isdigit():
        raise ReminderError(f"Invalid Discord ID: {value!r}")
    return snowflake


def load_config() -> Config:
    config = Config(
        bot_token=os.environ.get("DISCORD_BOT_TOKEN", "").strip(),
        guild_id=clean_snowflake(os.environ.get("DISCORD_GUILD_ID", "")),
        channel_id=clean_snowflake(os.environ.get("DISCORD_CHANNEL_ID", "")),
        generic_role_id=clean_snowflake(
            os.environ.get("DISCORD_GENERIC_ROLE_ID", "")
        ),
        sheet_url=os.environ.get("LOWLANDS_PUBLIC_SHEET_URL", DEFAULT_SHEET_URL).strip(),
    )
    missing = [
        name
        for name, value in (
            ("DISCORD_BOT_TOKEN", config.bot_token),
            ("DISCORD_GUILD_ID", config.guild_id),
            ("DISCORD_CHANNEL_ID", config.channel_id),
            ("DISCORD_GENERIC_ROLE_ID", config.generic_role_id),
        )
        if not value
    ]
    if missing:
        raise ReminderError("Missing GitHub secrets: " + ", ".join(missing))
    return config


def discord_request(
    config: Config,
    method: str,
    path: str,
    payload: dict[str, object] | None = None,
) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        API_BASE + path,
        data=data,
        headers={
            "Authorization": f"Bot {config.bot_token}",
            "Content-Type": "application/json",
            "User-Agent": "Lowlands-League-Reminder/2.0",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        raise ReminderError(f"Discord returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ReminderError(f"Discord request failed: {exc.reason}") from exc


def list_guild_members(config: Config) -> list[dict[str, Any]]:
    members: list[dict[str, Any]] = []
    after = "0"
    while True:
        query = urllib.parse.urlencode({"limit": 1000, "after": after})
        page = discord_request(
            config, "GET", f"/guilds/{config.guild_id}/members?{query}"
        )
        if not isinstance(page, list):
            raise ReminderError("Discord returned an invalid guild-member response.")
        members.extend(page)
        if len(page) < 1000:
            break
        after = str(page[-1].get("user", {}).get("id", ""))
        if not after:
            raise ReminderError("Discord member pagination returned no user ID.")
    return members


def normalized_name(value: object) -> str:
    return str(value or "").strip().removeprefix("@").casefold()


def member_names(member: dict[str, Any]) -> set[str]:
    user = member.get("user") or {}
    return {
        name
        for name in (
            normalized_name(user.get("username")),
            normalized_name(user.get("global_name")),
            normalized_name(member.get("nick")),
        )
        if name
    }


def resolve_players(
    requested_players: list[dict[str, object]], members: list[dict[str, Any]]
) -> list[dict[str, object]]:
    resolved: list[dict[str, object]] = []
    problems: list[str] = []
    for player in requested_players:
        discord_name = normalized_name(player.get("discord"))
        label = str(player.get("player") or discord_name or "Unknown player").strip()
        if not discord_name:
            problems.append(f"{label}: Discord name is blank")
            continue
        matches = [member for member in members if discord_name in member_names(member)]
        if len(matches) != 1:
            problems.append(
                f"{label}: {len(matches)} Discord matches for {player.get('discord')!r}"
            )
            continue
        user_id = str((matches[0].get("user") or {}).get("id", ""))
        if not user_id:
            problems.append(f"{label}: matched member has no user ID")
            continue
        resolved.append({**player, "user_id": user_id, "player": label})

    if problems:
        raise ReminderError(
            "Player-name resolution failed; no message was sent:\n- "
            + "\n- ".join(problems)
        )
    return resolved


def mentions(values: Iterable[str], role: bool = False) -> str:
    marker = "@&" if role else "@"
    return " ".join(f"<{marker}{value}>" for value in values)


def build_payload(
    kind: str,
    week: int,
    config: Config,
    resolved_players: list[dict[str, object]],
) -> dict[str, object]:
    if kind == "test":
        content = (
            "**Lowlands League reminder system test**\n"
            "The Discord bot can successfully post announcements. "
            "No players or roles were mentioned in this test."
        )
        allowed_mentions = {"parse": [], "roles": [], "users": []}
    elif kind == "open":
        content = (
            f"<@&{config.generic_role_id}>\n\n"
            f"**Week {week} is now open!**\n"
            "The weekly seeds are ready. Please complete all of them before "
            "Sunday at 23:59 (Europe/Amsterdam).\n\n"
            f"**Results and information:** {config.sheet_url}"
        )
        allowed_mentions = {"parse": [], "roles": [config.generic_role_id], "users": []}
    elif kind == "friday":
        content = (
            f"<@&{config.generic_role_id}>\n\n"
            f"**Week {week} reminder**\n"
            "Please check whether you have completed every seed. "
            "The deadline is Sunday at 23:59 (Europe/Amsterdam).\n\n"
            f"**Results and information:** {config.sheet_url}"
        )
        allowed_mentions = {"parse": [], "roles": [config.generic_role_id], "users": []}
    elif kind == "sunday":
        if not resolved_players:
            raise ReminderError("The Sunday reminder contains no incomplete players.")
        user_ids = [str(player["user_id"]) for player in resolved_players]
        detail = "\n".join(
            f"- **{player['player']}** — {int(player.get('missing', 0))} seed(s) remaining"
            for player in resolved_players
        )
        content = (
            f"{mentions(user_ids)}\n\n"
            f"**Final reminder for Week {week}**\n"
            "According to the latest sheet import, you still have at least one seed "
            "to complete. The deadline is today at 23:59 (Europe/Amsterdam).\n\n"
            f"{detail}\n\n"
            f"**Results and information:** {config.sheet_url}"
        )
        allowed_mentions = {"parse": [], "roles": [], "users": user_ids}
    else:
        raise ReminderError(f"Unsupported reminder kind: {kind}")

    if len(content) > 2000:
        raise ReminderError(
            f"Discord message is {len(content)} characters; the maximum is 2000."
        )
    return {
        "content": content,
        "allowed_mentions": {**allowed_mentions, "replied_user": False},
    }


def parse_players(value: str) -> list[dict[str, object]]:
    try:
        players = json.loads(value or "[]")
    except json.JSONDecodeError as exc:
        raise ReminderError(f"Invalid player JSON: {exc}") from exc
    if not isinstance(players, list) or not all(isinstance(item, dict) for item in players):
        raise ReminderError("Player JSON must be a list of objects.")
    return players


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--kind", choices=("test", "open", "friday", "sunday"), required=True
    )
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--players-json", default="[]")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        config = load_config()
        players = parse_players(args.players_json)
        resolved = (
            resolve_players(players, list_guild_members(config))
            if args.kind == "sunday"
            else []
        )
        payload = build_payload(args.kind, args.week, config, resolved)
        if args.dry_run:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        discord_request(
            config,
            "POST",
            f"/channels/{config.channel_id}/messages",
            payload,
        )
        print(
            f"Discord reminder sent: kind={args.kind}, week={args.week}, "
            f"individual_mentions={len(resolved)}"
        )
        return 0
    except ReminderError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
