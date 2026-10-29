"""Tournament bridge between Discord and the Admin spreadsheet web app."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import discord
import requests


class TournamentError(RuntimeError):
    """Raised when the tournament web app rejects or cannot serve a request."""


@dataclass
class TournamentApi:
    url: str = ""
    secret: str = ""
    timeout: int = 30

    @classmethod
    def from_env(cls) -> "TournamentApi":
        return cls(
            os.environ.get("TOURNAMENT_API_URL", "").strip(),
            os.environ.get("TOURNAMENT_API_SECRET", "").strip(),
        )

    @property
    def configured(self) -> bool:
        return bool(self.url and self.secret)

    def _require_config(self) -> None:
        if not self.configured:
            raise TournamentError(
                "Tournament control is not configured yet. Set TOURNAMENT_API_URL and "
                "TOURNAMENT_API_SECRET on Render."
            )

    @staticmethod
    def _payload(response: requests.Response) -> dict[str, Any]:
        try:
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise TournamentError(f"Tournament API request failed: {exc}") from exc
        if not payload.get("ok"):
            raise TournamentError(str(payload.get("error") or "Tournament API rejected the request."))
        return payload

    def get(self, action: str, **parameters: object) -> dict[str, Any]:
        self._require_config()
        query = urlencode({"secret": self.secret, "action": action, **parameters})
        return self._payload(requests.get(f"{self.url}?{query}", timeout=self.timeout))

    def post(self, action: str, **parameters: object) -> dict[str, Any]:
        self._require_config()
        body = {"secret": self.secret, "action": action, **parameters}
        return self._payload(requests.post(self.url, json=body, timeout=self.timeout)).get("data", {})

    def match_for_user(
        self, discord_user_id: int, discord_name: str = "", discord_display_name: str = ""
    ) -> dict[str, Any] | None:
        return self.get(
            "match",
            discord_user_id=str(discord_user_id),
            discord_name=discord_name,
            discord_display_name=discord_display_name,
        ).get("match")

    def bracket(self) -> dict[str, Any]:
        return self.get("bracket")


def tournament_match_embed(match: dict[str, Any], bracket_url: str = "", rules_url: str = "") -> discord.Embed:
    highlighted = bool(match.get("highlighted"))
    player_one = str(match.get("player1") or "TBD")
    player_two = str(match.get("player2") or "TBD")
    title = f"{match.get('round', 'Match')} · {match.get('match_id', '')}"
    description = (
        f"## {player_one}  **vs**  {player_two}\n"
        f"Best of {match.get('best_of', 3)}"
    )
    embed = discord.Embed(
        title=title,
        description=description,
        color=0xF47806 if highlighted else 0x01397A,
        url=bracket_url or None,
    )
    ready_one = "Ready" if match.get("player1_ready") else "Not ready"
    ready_two = "Ready" if match.get("player2_ready") else "Not ready"
    embed.add_field(name="Players", value=f"{match.get('player1')}: **{ready_one}**\n{match.get('player2')}: **{ready_two}**", inline=True)
    embed.add_field(name="Series", value=str(match.get("series_score") or "0-0"), inline=True)
    embed.add_field(name="Status", value=str(match.get("status") or "Unknown"), inline=False)
    embed.add_field(
        name="Party host",
        value=(
            f"**{player_one}** is de bovenste/linker speler en maakt de GeoGuessr-party aan. "
            "Deze speler stuurt de partylink hier in; de tegenstander joint via die link."
        ),
        inline=False,
    )
    if highlighted:
        permission = "Released by admin" if match.get("admin_released") else "Waiting for admin start permission"
        embed.add_field(name="Featured broadcast match", value=permission, inline=False)
    if match.get("party_url"):
        embed.add_field(name="Party", value=f"[Open GeoGuessr party]({match['party_url']})", inline=False)
    if match.get("stream_url"):
        embed.add_field(name="Broadcast", value=f"[Watch the stream]({match['stream_url']})", inline=False)
    if rules_url:
        embed.add_field(name="Reglement", value=f"[Lees het volledige toernooireglement]({rules_url})", inline=False)
    embed.set_footer(text="The Google Sheet bracket is the official tournament record.")
    return embed


def tournament_bracket_embed(payload: dict[str, Any]) -> discord.Embed:
    config = payload.get("config") or {}
    matches = sorted(payload.get("matches") or [], key=lambda item: int(item.get("order") or 0))
    title = str(config.get("Tournament Name") or "GeoNederland Tournament")
    bracket_url = str(config.get("Public Bracket URL") or "")
    rules_url = str(config.get("Rules URL") or "")
    embed = discord.Embed(title=title, color=0x01397A, url=bracket_url or None)
    if rules_url:
        embed.description = f"[Lees het volledige toernooireglement]({rules_url})"
    current_round = None
    lines: list[str] = []
    fields: list[tuple[str, str]] = []
    for match in matches:
        round_name = str(match.get("round") or "Bracket")
        if current_round is not None and round_name != current_round:
            fields.append((current_round, "\n".join(lines) or "—"))
            lines = []
        current_round = round_name
        feature = " 📺" if match.get("highlighted") else ""
        score = f" · {match.get('series_score')}" if match.get("series_score") and match.get("series_score") != "0-0" else ""
        lines.append(
            f"`{match.get('match_id', '')}` **{match.get('player1', 'TBD')}** vs "
            f"**{match.get('player2', 'TBD')}**{score}{feature}\n"
            f"└ {match.get('status', 'Unknown')}"
        )
    if current_round is not None:
        fields.append((current_round, "\n".join(lines) or "—"))
    for name, value in fields:
        embed.add_field(name=name, value=value[:1024], inline=False)
    embed.set_footer(text="📺 Highlighted match · Results update from the official Sheet")
    return embed


def tournament_rules_embed(payload: dict[str, Any]) -> discord.Embed:
    config = payload.get("config") or {}
    title = str(config.get("Tournament Name") or "GeoNederland Tournament")
    rules_url = str(config.get("Rules URL") or "").strip()
    if not rules_url:
        return discord.Embed(
            title=f"{title} · Reglement",
            description="Er is voor dit toernooi nog geen openbare reglementlink ingesteld.",
            color=0xF47806,
        )
    return discord.Embed(
        title=f"{title} · Reglement",
        description=f"[Open het volledige toernooireglement]({rules_url})",
        color=0x01397A,
        url=rules_url,
    )


def tournament_registration_embed(player: dict[str, Any], action: str) -> discord.Embed:
    messages = {
        "register": "Registration saved",
        "checkin": "Check-in confirmed",
        "unregister": "Registration withdrawn",
    }
    embed = discord.Embed(
        title=messages.get(action, "Tournament registration"),
        description=f"**{player.get('player', 'Unknown')}** · {player.get('country', '—')}",
        color=0x35C27C if player.get("checked_in") else (0xF47806 if action == "unregister" else 0x01397A),
    )
    embed.add_field(name="Status", value=str(player.get("status") or "Registered"), inline=True)
    embed.add_field(name="GeoGuessr ID", value=f"`{player.get('geoguessr_user_id', '')}`", inline=True)
    embed.set_footer(text="GeoNederland Tournament · The Admin Sheet is the official player list")
    return embed
