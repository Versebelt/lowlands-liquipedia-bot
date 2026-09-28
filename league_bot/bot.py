"""24/7 Discord application for Lowlands League."""

from __future__ import annotations

import asyncio
import logging
import os

import discord
from aiohttp import web
from discord import app_commands

from .admin_config import AdminConfig, CONFIG_CHANNEL_NAME, decode_topic, encode_topic
from .sheets import DEFAULT_SPREADSHEET_ID, PublicSheet, SheetError, display_number

PUBLIC_URL = f"https://docs.google.com/spreadsheets/d/{DEFAULT_SPREADSHEET_ID}"
BLUE = 0x1E9DDB
ORANGE = 0xE75325
YELLOW = 0xEFAC1F
CHARCOAL = 0x111111
COMMANDS = (
    ("/ping", "!ping", "Show the bot latency"),
    ("/standings", "!standings", "Show the playoff top 16"),
    ("/player name", "!player <name>", "Show a player's position and league points"),
    ("/week number", "!week <1-10>", "Show a week's seeds and deadline"),
    ("/stats name", "!stats <name>", "Show a detailed player card and weekly trend"),
    ("/compare player_one player_two", "!compare <name 1> | <name 2>", "Compare two players head-to-head"),
    ("/cutoff", "!cutoff", "Show the current playoff qualification line"),
    ("/mode mode", "!mode <Moving|NM|NMPZ>", "Show a mode-specific top five"),
    ("/commands", "!commands", "Show this command overview"),
)
ADMIN_COMMANDS = (
    ("/adminconfig", "!adminconfig", "Show the active reminder configuration"),
    ("/setupreminders #channel @role", "!setupreminders #channel @role", "Configure channel and role together"),
    ("/setannouncement #channel", "!setannouncement #channel", "Set the announcement channel"),
    ("/setreminderrole @role", "!setreminderrole @role", "Set the Friday reminder role"),
    ("/reminders enabled", "!reminders <on|off>", "Enable or disable automatic reminders"),
    ("/testreminder", "!testreminder", "Send a mention-free test to the configured channel"),
)


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def pretty_stat(value: str, fallback: str = "—") -> str:
    value = str(value or "").strip()
    if not value:
        return fallback
    return value[:-2] if value.endswith(",0") else value


def stat_value(value: str) -> float:
    value = str(value or "").strip().replace(" ", "")
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return 0.0


def sparkline(values: list[str]) -> str:
    parsed = [stat_value(value) for value in values if value]
    if not parsed:
        return "—"
    blocks = "▁▂▃▄▅▆▇█"
    low, high = min(parsed), max(parsed)
    if low == high:
        return blocks[3] * len(parsed)
    return "".join(blocks[round((value - low) / (high - low) * 7)] for value in parsed)


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


def commands_embed() -> discord.Embed:
    lines = [f"`{slash}` · `{prefix}`\n{description}" for slash, prefix, description in COMMANDS]
    embed = discord.Embed(
        title="Lowlands League commands",
        description="\n\n".join(lines),
        color=BLUE,
        url=PUBLIC_URL,
    )
    embed.set_footer(text="Slash and ! commands use the same live sheet data")
    return embed


def admin_config_embed(config: AdminConfig) -> discord.Embed:
    channel = f"<#{config.announcement_channel_id}>" if config.announcement_channel_id else "Not configured"
    role = f"<@&{config.reminder_role_id}>" if config.reminder_role_id else "Not configured"
    embed = discord.Embed(
        title="Lowlands League admin configuration",
        description="These settings are shared by the live bot and every GitHub reminder run.",
        color=BLUE if config.reminders_enabled else ORANGE,
    )
    embed.add_field(name="Announcement channel", value=channel, inline=False)
    embed.add_field(name="Friday reminder role", value=role, inline=False)
    embed.add_field(name="Automatic reminders", value="Enabled" if config.reminders_enabled else "Disabled")
    embed.add_field(
        name="Schedule",
        value=(
            f"Monday {config.monday_time}\nFriday {config.friday_time}\n"
            f"Sunday {config.sunday_time}\n{config.timezone}"
        ),
    )
    embed.set_footer(text="Only server administrators can change these settings")
    return embed


async def config_channel(guild: discord.Guild, create: bool = False) -> discord.TextChannel | None:
    channel = discord.utils.get(guild.text_channels, name=CONFIG_CHANNEL_NAME)
    if channel or not create:
        return channel
    me = guild.me
    overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False)}
    if me:
        overwrites[me] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True, manage_channels=True
        )
    return await guild.create_text_channel(
        CONFIG_CHANNEL_NAME,
        topic=encode_topic(AdminConfig()),
        overwrites=overwrites,
        reason="Persistent Lowlands League bot configuration",
    )


async def read_admin_config(guild: discord.Guild) -> AdminConfig:
    channel = await config_channel(guild)
    return decode_topic(channel.topic) if channel else AdminConfig()


async def write_admin_config(guild: discord.Guild, config: AdminConfig) -> None:
    channel = await config_channel(guild, create=True)
    if channel is None:
        raise RuntimeError("Could not create the configuration channel")
    await channel.edit(topic=encode_topic(config), reason="Lowlands League admin command")


def is_admin(member: discord.Member | discord.User) -> bool:
    return isinstance(member, discord.Member) and member.guild_permissions.administrator


async def send_test_reminder(guild: discord.Guild, config: AdminConfig) -> discord.TextChannel:
    if not config.announcement_channel_id:
        raise ValueError("Set an announcement channel first.")
    channel = guild.get_channel(int(config.announcement_channel_id))
    if not isinstance(channel, discord.TextChannel):
        raise ValueError("The configured announcement channel no longer exists.")
    await channel.send(
        "**Lowlands League reminder system test**\n"
        "The central admin configuration is working. No players or roles were mentioned.",
        allowed_mentions=discord.AllowedMentions.none(),
    )
    return channel


def stats_embed(row: dict[str, object]) -> discord.Embed:
    weekly = [str(value) for value in row["weekly"]]
    played = [pretty_stat(value) for value in weekly if value]
    embed = discord.Embed(
        title=f"#{row['rank']}  {row['player']}",
        description=(
            f"**Weekly form**  `{sparkline(weekly)}`\n"
            + (" · ".join(played) if played else "No weekly scores yet")
        ),
        color=ORANGE,
        url=PUBLIC_URL,
    )
    embed.add_field(name="League points", value=pretty_stat(str(row["points"])))
    embed.add_field(name="Average / week", value=pretty_stat(str(row["average"])))
    embed.add_field(name="Best mode", value=pretty_stat(str(row["best_mode"])))
    embed.add_field(name="Best week", value=pretty_stat(str(row["best_week"])))
    embed.add_field(name="Worst week", value=pretty_stat(str(row["worst_week"])))
    embed.add_field(name="Consistency", value=pretty_stat(str(row["consistency"])))
    embed.add_field(name="Cutoff gap", value=pretty_stat(str(row["cutoff_gap"])))
    embed.add_field(name="Top-16 streak", value=pretty_stat(str(row["streak"])))
    embed.add_field(name="Last three", value=pretty_stat(str(row["last_three"])), inline=False)
    embed.set_footer(text=f"{row['country']} · {row['status']}")
    return embed


def compare_embed(left: dict[str, object], right: dict[str, object]) -> discord.Embed:
    def card(row: dict[str, object]) -> str:
        return (
            f"Position: **#{row['rank']}**\n"
            f"Points: **{pretty_stat(str(row['points']))}**\n"
            f"Average: **{pretty_stat(str(row['average']))}**\n"
            f"Best mode: **{row['best_mode']}**\n"
            f"Form: `{sparkline([str(value) for value in row['weekly']])}`"
        )

    embed = discord.Embed(
        title=f"{left['player']}  vs  {right['player']}",
        description="Head-to-head based on the latest public statistics.",
        color=YELLOW,
        url=PUBLIC_URL,
    )
    embed.add_field(name=str(left["player"]), value=card(left), inline=True)
    embed.add_field(name=str(right["player"]), value=card(right), inline=True)
    return embed


def cutoff_embed(rows: list[dict[str, str]]) -> discord.Embed:
    qualified = rows[15] if len(rows) >= 16 else None
    chasing = rows[16] if len(rows) >= 17 else None
    description = "The top 16 qualify. Seeds 9–16 enter Round 1, seeds 5–8 enter Round 2, and seeds 1–4 enter the quarterfinals."
    embed = discord.Embed(title="Playoff cutoff", description=description, color=YELLOW, url=PUBLIC_URL)
    if qualified:
        embed.add_field(
            name="#16 · Currently qualified",
            value=f"**{qualified['player']}**\n{display_number(qualified['points'])} pts",
        )
    if chasing:
        gap = max(0, int(stat_value(qualified["points"]) - stat_value(chasing["points"]))) if qualified else 0
        embed.add_field(
            name="#17 · First outside",
            value=f"**{chasing['player']}**\n{display_number(chasing['points'])} pts\nGap: {gap} pts",
        )
    return embed


def mode_embed(mode: str, rows: list[dict[str, str]]) -> discord.Embed:
    key = mode.casefold()
    label = "Moving" if key == "moving" else key.upper()
    lines = [
        f"`{index}` **{row['player']}** — {display_number(row[key])} pts"
        for index, row in enumerate(rows[:5], start=1)
    ]
    return discord.Embed(
        title=f"{label} leaderboard",
        description="\n".join(lines) or "No mode scores available.",
        color=BLUE,
        url=PUBLIC_URL,
    )


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
        elif command in {"commands", "help"}:
            await message.reply(embed=commands_embed(), mention_author=False)
        elif command == "stats":
            if not argument:
                await message.reply("Usage: `!stats <name>`", mention_author=False)
                return
            row = await asyncio.to_thread(client.sheet.player_stats, argument)
            if not row:
                await message.reply("No unique player match was found.", mention_author=False)
                return
            await message.reply(embed=stats_embed(row), mention_author=False)
        elif command == "compare":
            names = [name.strip() for name in argument.split("|", 1)]
            if len(names) != 2 or not all(names):
                await message.reply(
                    "Usage: `!compare <player 1> | <player 2>`", mention_author=False
                )
                return
            left, right = await asyncio.gather(
                asyncio.to_thread(client.sheet.player_stats, names[0]),
                asyncio.to_thread(client.sheet.player_stats, names[1]),
            )
            if not left or not right:
                await message.reply(
                    "One or both player names were not a unique match.",
                    mention_author=False,
                )
                return
            await message.reply(embed=compare_embed(left, right), mention_author=False)
        elif command == "cutoff":
            rows = await asyncio.to_thread(client.sheet.standings)
            await message.reply(embed=cutoff_embed(rows), mention_author=False)
        elif command == "mode":
            mode = argument.casefold()
            if mode not in {"moving", "nm", "nmpz"}:
                await message.reply(
                    "Usage: `!mode <Moving|NM|NMPZ>`", mention_author=False
                )
                return
            rows = await asyncio.to_thread(client.sheet.mode_leaderboard, mode)
            await message.reply(embed=mode_embed(mode, rows), mention_author=False)
        elif command in {"adminconfig", "setupreminders", "setannouncement", "setreminderrole", "reminders", "testreminder"}:
            if not is_admin(message.author):
                await message.reply("This command is only available to server administrators.", mention_author=False)
                return
            config = await read_admin_config(message.guild)
            if command == "adminconfig":
                await message.reply(embed=admin_config_embed(config), mention_author=False)
            elif command == "setupreminders":
                if not message.channel_mentions or not message.role_mentions:
                    await message.reply("Usage: `!setupreminders #channel @role`", mention_author=False)
                    return
                config.announcement_channel_id = str(message.channel_mentions[0].id)
                config.reminder_role_id = str(message.role_mentions[0].id)
                await write_admin_config(message.guild, config)
                await message.reply(
                    f"Central reminder configuration saved: {message.channel_mentions[0].mention} · {message.role_mentions[0].mention}.",
                    mention_author=False,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            elif command == "setannouncement":
                if not message.channel_mentions:
                    await message.reply("Usage: `!setannouncement #channel`", mention_author=False)
                    return
                config.announcement_channel_id = str(message.channel_mentions[0].id)
                await write_admin_config(message.guild, config)
                await message.reply(f"Announcement channel set to {message.channel_mentions[0].mention}.", mention_author=False)
            elif command == "setreminderrole":
                if not message.role_mentions:
                    await message.reply("Usage: `!setreminderrole @role`", mention_author=False)
                    return
                config.reminder_role_id = str(message.role_mentions[0].id)
                await write_admin_config(message.guild, config)
                await message.reply(f"Friday reminder role set to {message.role_mentions[0].mention}.", mention_author=False)
            elif command == "reminders":
                state = argument.casefold()
                if state not in {"on", "off"}:
                    await message.reply("Usage: `!reminders <on|off>`", mention_author=False)
                    return
                config.reminders_enabled = state == "on"
                await write_admin_config(message.guild, config)
                await message.reply(f"Automatic reminders are now **{'enabled' if config.reminders_enabled else 'disabled'}**.", mention_author=False)
            else:
                channel = await send_test_reminder(message.guild, config)
                await message.reply(f"Mention-free test sent to {channel.mention}.", mention_author=False)
    except SheetError:
        logging.exception("Sheet prefix command failed")
        await message.reply(
            "The public results could not be loaded right now. Please try again shortly.",
            mention_author=False,
        )
    except (discord.Forbidden, discord.HTTPException, ValueError, RuntimeError) as exc:
        logging.exception("Admin prefix command failed")
        await message.reply(f"Admin configuration failed: {exc}", mention_author=False)


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


@client.tree.command(name="commands", description="Show all Lowlands League bot commands")
async def command_list(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(embed=commands_embed(), ephemeral=True)


@client.tree.command(name="stats", description="Show a detailed Lowlands League player card")
@app_commands.describe(name="Player name from the Lowlands League")
async def stats(interaction: discord.Interaction, name: str) -> None:
    await interaction.response.defer()
    try:
        row = await asyncio.to_thread(client.sheet.player_stats, name)
        if not row:
            await interaction.followup.send("No unique player match was found.", ephemeral=True)
            return
        await interaction.followup.send(embed=stats_embed(row))
    except SheetError as exc:
        await sheet_failure(interaction, exc)


@client.tree.command(name="compare", description="Compare two Lowlands League players")
@app_commands.describe(player_one="First player", player_two="Second player")
async def compare(interaction: discord.Interaction, player_one: str, player_two: str) -> None:
    await interaction.response.defer()
    try:
        left, right = await asyncio.gather(
            asyncio.to_thread(client.sheet.player_stats, player_one),
            asyncio.to_thread(client.sheet.player_stats, player_two),
        )
        if not left or not right:
            await interaction.followup.send(
                "One or both player names were not a unique match.", ephemeral=True
            )
            return
        await interaction.followup.send(embed=compare_embed(left, right))
    except SheetError as exc:
        await sheet_failure(interaction, exc)


@client.tree.command(name="cutoff", description="Show the current playoff qualification line")
async def cutoff(interaction: discord.Interaction) -> None:
    await interaction.response.defer()
    try:
        rows = await asyncio.to_thread(client.sheet.standings)
        await interaction.followup.send(embed=cutoff_embed(rows))
    except SheetError as exc:
        await sheet_failure(interaction, exc)


@client.tree.command(name="mode", description="Show a mode-specific leaderboard")
@app_commands.describe(mode="Scoring mode")
@app_commands.choices(
    mode=[
        app_commands.Choice(name="Moving", value="moving"),
        app_commands.Choice(name="No Move", value="nm"),
        app_commands.Choice(name="NMPZ", value="nmpz"),
    ]
)
async def mode(interaction: discord.Interaction, mode: app_commands.Choice[str]) -> None:
    await interaction.response.defer()
    try:
        rows = await asyncio.to_thread(client.sheet.mode_leaderboard, mode.value)
        await interaction.followup.send(embed=mode_embed(mode.value, rows))
    except SheetError as exc:
        await sheet_failure(interaction, exc)


async def admin_failure(interaction: discord.Interaction, error: Exception) -> None:
    logging.exception("Admin configuration command failed", exc_info=error)
    message = f"Admin configuration failed: {error}"
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


@client.tree.command(name="adminconfig", description="Show the central reminder configuration")
@app_commands.default_permissions(administrator=True)
async def adminconfig(interaction: discord.Interaction) -> None:
    if interaction.guild is None or not is_admin(interaction.user):
        return
    config = await read_admin_config(interaction.guild)
    await interaction.response.send_message(embed=admin_config_embed(config), ephemeral=True)


@client.tree.command(name="setannouncement", description="Set the channel used for league announcements")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(channel="Announcement channel for all automatic reminders")
async def setannouncement(interaction: discord.Interaction, channel: discord.TextChannel) -> None:
    if interaction.guild is None or not is_admin(interaction.user):
        return
    try:
        config = await read_admin_config(interaction.guild)
        config.announcement_channel_id = str(channel.id)
        await write_admin_config(interaction.guild, config)
        await interaction.response.send_message(f"Announcement channel set to {channel.mention}.", ephemeral=True)
    except (discord.Forbidden, discord.HTTPException, RuntimeError) as exc:
        await admin_failure(interaction, exc)


@client.tree.command(name="setupreminders", description="Configure the reminder channel and role together")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(channel="Announcement channel", role="Role mentioned by Friday reminders")
async def setupreminders(interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role) -> None:
    if interaction.guild is None or not is_admin(interaction.user):
        return
    try:
        config = await read_admin_config(interaction.guild)
        config.announcement_channel_id = str(channel.id)
        config.reminder_role_id = str(role.id)
        await write_admin_config(interaction.guild, config)
        await interaction.response.send_message(
            f"Central reminder configuration saved: {channel.mention} · {role.mention}.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except (discord.Forbidden, discord.HTTPException, RuntimeError) as exc:
        await admin_failure(interaction, exc)


@client.tree.command(name="setreminderrole", description="Set the role mentioned by Friday reminders")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(role="Role to mention in the Friday reminder")
async def setreminderrole(interaction: discord.Interaction, role: discord.Role) -> None:
    if interaction.guild is None or not is_admin(interaction.user):
        return
    try:
        config = await read_admin_config(interaction.guild)
        config.reminder_role_id = str(role.id)
        await write_admin_config(interaction.guild, config)
        await interaction.response.send_message(f"Friday reminder role set to {role.mention}.", ephemeral=True)
    except (discord.Forbidden, discord.HTTPException, RuntimeError) as exc:
        await admin_failure(interaction, exc)


@client.tree.command(name="reminders", description="Enable or disable automatic league reminders")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(enabled="Whether automatic reminders may be sent")
async def reminders_toggle(interaction: discord.Interaction, enabled: bool) -> None:
    if interaction.guild is None or not is_admin(interaction.user):
        return
    try:
        config = await read_admin_config(interaction.guild)
        config.reminders_enabled = enabled
        await write_admin_config(interaction.guild, config)
        await interaction.response.send_message(
            f"Automatic reminders are now **{'enabled' if enabled else 'disabled'}**.", ephemeral=True
        )
    except (discord.Forbidden, discord.HTTPException, RuntimeError) as exc:
        await admin_failure(interaction, exc)


@client.tree.command(name="testreminder", description="Send a mention-free test to the announcement channel")
@app_commands.default_permissions(administrator=True)
async def testreminder(interaction: discord.Interaction) -> None:
    if interaction.guild is None or not is_admin(interaction.user):
        return
    await interaction.response.defer(ephemeral=True)
    try:
        config = await read_admin_config(interaction.guild)
        channel = await send_test_reminder(interaction.guild, config)
        await interaction.followup.send(f"Mention-free test sent to {channel.mention}.", ephemeral=True)
    except (discord.Forbidden, discord.HTTPException, ValueError) as exc:
        await admin_failure(interaction, exc)


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
