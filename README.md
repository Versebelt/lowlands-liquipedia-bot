# Lowlands League Liquipedia publisher

Cloud publisher for Lowlands League Season 2. Google Apps Script generates the
wikicode and starts a GitHub Actions workflow. The workflow publishes through
Liquipedia's bot API with a descriptive user agent and a 15-second request
interval.

## Initial safety scope

The workflow initially accepts exactly one page:

```text
User:DialloBOT/test
```

Production tournament pages must only be added after the test page succeeds.

## Repository secrets

In **Settings → Secrets and variables → Actions**, create these repository
secrets:

| Secret | Value |
| --- | --- |
| `LIQUIPEDIA_BOT_USERNAME` | Bot-password login, for example `DialloBOT@DialloBOT` |
| `LIQUIPEDIA_BOT_PASSWORD` | Generated bot password only |
| `LIQUIPEDIA_CONTACT` | Contact email address or Liquipedia profile URL |

Never commit these values to the repository.

## Google Apps Script properties

Create these Script Properties in the Admin spreadsheet project:

| Property | Value |
| --- | --- |
| `GITHUB_REPOSITORY` | `Versebelt/lowlands-liquipedia-bot` |
| `GITHUB_WORKFLOW_FILE` | `publish-liquipedia.yml` |
| `GITHUB_WORKFLOW_REF` | `main` |
| `GITHUB_ACTIONS_TOKEN` | Fine-grained GitHub token with Actions: write access to this repository |

The GitHub token belongs in Apps Script properties, never in spreadsheet cells
or source code.

## First test

1. Add the repository files and secrets.
2. Update the Admin spreadsheet's `Code.gs`.
3. Reload the spreadsheet.
4. Choose **Lowlands League → Queue overview test via GitHub**.
5. Open the repository's **Actions** tab and inspect the run.
6. Verify the result at `https://liquipedia.net/geoguessr/User:DialloBOT/test`.

The workflow does not retry HTTP 429 responses and does not publish unchanged
content. Every run uploads a short-lived result artifact. Apps Script correlates
that artifact with its `Liquipedia Log` sheet and records the final result,
revision id, failed step, or error message.

## Discord seed reminders

Apps Script determines the current week and dispatches
`.github/workflows/discord-reminders.yml` at these times:

- Monday 09:00 Europe/Amsterdam: the new week is open.
- Friday 20:00: reminder mentioning the generic league role.
- Sunday 10:00: final reminder mentioning only active players who still miss
  one or more enabled seeds according to the latest imported sheet data.

The `Discord` column on the Admin spreadsheet's `Players` tab may contain a
Discord username, global display name, or server nickname. Matching is exact
and case-insensitive. The bot refuses to send if a name is missing or matches
more than one server member.

Configure these GitHub Actions repository secrets:

- `DISCORD_BOT_TOKEN`: token from the Discord Developer Portal.
- `DISCORD_GUILD_ID`: numeric ID of the Lowlands League server.
- `DISCORD_CHANNEL_ID`: numeric ID of the announcements channel.
- `DISCORD_GENERIC_ROLE_ID`: numeric ID of the general reminder role.

Enable the bot's **Server Members Intent**, then invite it with permission to
view and send messages in the announcement channel. Discord's
`allowed_mentions` is restricted to the exact resolved users or configured
role; arbitrary mentions and `@everyone` are never enabled. Apps Script records
dispatches and their eventual GitHub result in the `Discord Log` tab.

## Permanent Discord bot

The Docker service in `league_bot` keeps a Discord Gateway connection open and
registers guild-scoped slash commands immediately:

- `/ping` checks connectivity and latency.
- `/standings` shows the current playoff top 16.
- `/player name` shows one player's rank, points, and weeks played.
- `/week number` shows the seeds, modes, statuses, and deadline for a week.

The service reads only the public spreadsheet and caches results for two minutes.
Copy `.env.example` to `.env`, set `DISCORD_BOT_TOKEN` and `DISCORD_GUILD_ID`,
then start it with `docker compose up -d --build`. The container runs as a
non-root user, restarts automatically, and exposes its health endpoint only on
localhost at `http://127.0.0.1:8080/health`.

For an IPv6-only Google Compute Engine deployment, use `deploy/startup.sh` as
the VM startup script. It installs the bot directly into a Python virtual
environment so the process can use the host's IPv6 connection without Docker
bridge configuration. Runtime secrets belong in `/opt/lowlands-bot/bot.env`
with mode `0600`; they are never stored in VM metadata or Git.
