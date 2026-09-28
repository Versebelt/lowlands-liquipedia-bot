"""24/7 Discord application for Lowlands League."""

from __future__ import annotations

import asyncio
import logging
import os

import discord
from aiohttp import web
from discord import app_commands

from .sheets import DEFAULT_SPREADSHEET_ID, PublicSheet, SheetError, display_number

PUBLIC_URL = f"https://docs.google.com/spreadsheets/d/{DEFAULT_SPREADSHEET_ID}"
BLUE = 0x1E9DDB
ORANGE = 0xE75325


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


class LowlandsClient(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        intents.members = True
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.sheet = PublicSheet(os.environ.get("LOWLANDS_SPREADSHEET_ID", DEFAULT_SPREADSHEET_ID))
        self.guild_id = int(required_env("DISCORD_GUILD_ID"))

    async def setup_hook(self) -> None:
        guild = discord.Object(id=self.guild_id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

    async def on_ready(self) -> None:
        logging.info("Connected as %s (%s)", self.user, self.user.id if self.user else "unknown")
        await self.change_presence(activity=discord.Game(name="Lowlands League Season 2"))

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None or message.guild.id != self.guild_id:
            return
        if not message.content.startswith("!"):
            return
        await handle_prefix_command(message)


client = LowlandsClient()


def standings_embed(rows: list[dict[str, str]]) -> discord.Embed:
    description = "\n".join(
        f"`{row['rank']:>2}` **{row['player']}** — {display_number(row['points'])} pts"
        for row in rows[:16]
    )
    embed = discord.Embed(
        title="Lowlands League standings",
        description=description or "No standings available.",
        color=BLUE,
        url=PUBLIC_URL,
    )
    embed.set_footer(text="Top 16 qualify for the playoffs")
    return embed


def player_embed(row: dict[str, str]) -> discord.Embed:
    embed = discord.Embed(title=row["player"], color=ORANGE, url=PUBLIC_URL)
    embed.add_field(name="Position", value=f"#{row['rank']}")
    embed.add_field(name="League points", value=display_number(row["points"]))
    embed.add_field(name="Weeks played", value=row["weeks"] or "—")
    if row["country"]:
        embed.set_footer(text=row["country"])
    return embed


def week_embed(number: int, rows: list[dict[str, str]]) -> discord.Embed:
    lines = []
    for row in rows:
        details = " — ".join(
            value for value in (row["map"], row["mode"], row["status"]) if value
        )
        label = f"Seed {row['number']}: {details}"
        lines.append(f"[{label}]({row['url']})" if row["url"] else label)
    embed = discord.Embed(
        title=f"Week {number}",
        description="\n".join(lines),
        color=BLUE,
        url=PUBLIC_URL,
    )
    deadline = next((row["deadline"] for row in rows if row["deadline"]), "")
    if deadline:
        embed.set_footer(text=f"Deadline: {deadline}")
    return embed


async def handle_prefix_command(message: discord.Message) -> None:
    command, _, argument = message.content[1:].strip().partition(" ")
    command = command.casefold()
    argument = argument.strip()

    try:
        if command == "ping":
            await message.reply(
                f"Online — {round(client.latency * 1000)} ms",
                mention_author=False,
            )
        elif command == "standings":
            async with message.channel.typing():
                rows = await asyncio.to_thread(client.sheet.standings)
            await message.reply(embed=standings_embed(rows), mention_author=False)
        elif command == "player":
            if not argument:
                await message.reply("Usage: `!player <name>`", mention_author=False)
                return
            async with message.channel.typing():
                row = await asyncio.to_thread(client.sheet.player, argument)
            if not row:
                await message.reply(
                    "No unique player match was found.", mention_author=False
                )
                return
            await message.reply(embed=player_embed(row), mention_author=False)
        elif command == "week":
            if not argument.isdigit() or not 1 <= int(argument) <= 10:
                await message.reply("Usage: `!week <1-10>`", mention_author=False)
                return
            number = int(argument)
            async with message.channel.typing():
                rows = await asyncio.to_thread(client.sheet.week, number)
            if not rows:
                await message.reply(
                    f"No challenges are available for Week {number}.",
                    mention_author=False,
                )
                return
            await message.reply(embed=week_embed(number, rows), mention_author=False)
    except SheetError:
        logging.exception("Sheet prefix command failed")
        await message.reply(
            "The public results could not be loaded right now. Please try again shortly.",
            mention_author=False,
        )


async def sheet_failure(interaction: discord.Interaction, error: Exception) -> None:
    logging.exception("Sheet command failed", exc_info=error)
    message = "The public results could not be loaded right now. Please try again shortly."
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


@client.tree.command(name="ping", description="Check whether the Lowlands League bot is online")
async def ping(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(f"Online — {round(client.latency * 1000)} ms", ephemeral=True)


@client.tree.command(name="standings", description="Show the current Lowlands League standings")
async def standings(interaction: discord.Interaction) -> None:
    await interaction.response.defer()
    try:
        rows = await asyncio.to_thread(client.sheet.standings)
        await interaction.followup.send(embed=standings_embed(rows))
    except SheetError as exc:
        await sheet_failure(interaction, exc)


@client.tree.command(name="player", description="Look up a player in the current standings")
@app_commands.describe(name="Player name from the Lowlands League")
async def player(interaction: discord.Interaction, name: str) -> None:
    await interaction.response.defer()
    try:
        row = await asyncio.to_thread(client.sheet.player, name)
        if not row:
            await interaction.followup.send("No unique player match was found.", ephemeral=True)
            return
        await interaction.followup.send(embed=player_embed(row))
    except SheetError as exc:
        await sheet_failure(interaction, exc)


@client.tree.command(name="week", description="Show the challenges for a league week")
@app_commands.describe(number="Week number from 1 to 10")
async def week(interaction: discord.Interaction, number: app_commands.Range[int, 1, 10]) -> None:
    await interaction.response.defer()
    try:
        rows = await asyncio.to_thread(client.sheet.week, number)
        if not rows:
            await interaction.followup.send(f"No challenges are available for Week {number}.", ephemeral=True)
            return
        await interaction.followup.send(embed=week_embed(number, rows))
    except SheetError as exc:
        await sheet_failure(interaction, exc)


async def health(_: web.Request) -> web.Response:
    return web.json_response({"ok": client.is_ready(), "latency_ms": round(client.latency * 1000)})


async def run() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
    app = web.Application()
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", "8080"))).start()
    try:
        await client.start(required_env("DISCORD_BOT_TOKEN"))
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(run())
