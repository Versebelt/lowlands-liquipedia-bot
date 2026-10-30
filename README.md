# Lowlands League automation

Automation for Lowlands League Season 2: Liquipedia publishing, scheduled
Discord reminders, and the interactive Discord bot hosted on Render.

## Liquipedia publishing scope

The publisher accepts only these exact pages:

```text
User:DialloBOT/test
Lowlands League/Season 2
Lowlands League/Season 2/Week 1 through Week 10
```

Every generated page carries a managed-page marker. Existing production pages
can be adopted once through the explicitly confirmed spreadsheet menu action.
After adoption, publication stops if that marker is removed, preventing an
unexpected full-page overwrite. Identical content produces `NoChange` instead
of a new revision.

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

## Production activation

1. Reload the Admin spreadsheet so the updated menu is visible.
2. Choose **Lowlands League → Adopt & publish production pages (first run)**.
3. Type `ADOPT` and inspect every result in **Liquipedia Log**.
4. Once all pages are marked and correct, choose
   **Install daily production sync (22:00)**.

The daily run publishes the overview plus configured weeks up to the current
week. Future weeks are not created early. The test-page scheduler is removed
when the production scheduler is installed.

The workflow does not retry HTTP 429 responses and does not publish unchanged
content. Every run uploads a short-lived result artifact. Apps Script correlates
that artifact with its `Liquipedia Log` sheet and records the final result,
revision id, failed step, or error message.

## Discord seed reminders

Apps Script determines the current week and dispatches
`.github/workflows/discord-reminders.yml` at these times. A five-minute scheduler
checks the Europe/Amsterdam clock instead of relying on Apps Script's approximate
`nearMinute()` scheduling:

- Monday 09:00 Europe/Amsterdam: the new week is open.
- Friday 20:00: reminder mentioning the generic league role.
- Sunday 10:00: final reminder mentioning only active players who still miss
  one or more enabled seeds according to the latest imported sheet data.
- Monday 00:10: automated recap of the week that just closed.

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
dispatches and their eventual GitHub result in the `Discord Log` tab. Scheduled
entries also record the intended time, dispatch delay, and workflow completion
time. A per-week delivery key prevents duplicates when triggers overlap or retry.
Failed deliveries and delays over five minutes appear in the Admin spreadsheet's
`Checks` tab.

## Permanent Discord bot

The Render service runs `python -m league_bot.bot`, keeps a Discord Gateway
connection open, and registers guild-scoped slash commands immediately:

- `/ping` checks connectivity and latency.
- `/standings` shows the current playoff top 16.
- `/player name` shows one player's rank, points, and weeks played.
- `/linkplayer name` links a Discord account to its league player; `/whoami`
  then opens a private personal dashboard.
- `/movers`, `/battle`, `/nations`, and `/recap` show weekly movement, the
  closest cutoff fight, the Benelux nations table, and the latest week recap.
- `/predict player_one player_two` produces a form-based matchup prediction.
- `/achievements` and `/milestones` show live season awards and records.
- `/week number` shows the seeds, modes, statuses, and deadline for a week.

The same public commands also work with a message prefix: `!ping`,
`!standings`, `!player <name>`, and `!week <1-10>`. Prefix commands require the
**Message Content Intent** to be enabled for the application in the Discord
Developer Portal. Slash commands remain available when that intent is disabled.

Additional visual commands are available in both forms:

- `/stats name` or `!stats <name>` shows a detailed player card and form graph.
- `/compare player_one player_two` or `!compare <name 1> | <name 2>` compares players.
- `/cutoff` or `!cutoff` shows the live playoff qualification line.
- `/mode mode` or `!mode <Moving|NM|NMPZ>` shows a mode-specific top five.
- `/commands` or `!commands` shows the complete in-Discord command guide.

The service reads only the public spreadsheet and caches results for two minutes.
General competition cards link to `GEONEDERLAND_LEAGUE_URL` (by default
`https://geonederland.gg/leagues.html`); detailed week and statistics links
continue to open the exact public Sheet tab as their underlying data source.

### Keeping interactive commands online on Render Free

`.github/workflows/keep-render-awake.yml` requests the public `/health` endpoint
every five minutes. Render Free otherwise spins the web service down after fifteen
minutes without inbound traffic, which disconnects the Discord Gateway and makes
all slash and prefix commands unavailable. The workflow also validates the JSON
health response and visibly fails in GitHub Actions if the service cannot recover.

One continuously running Free service uses at most 744 instance hours in a
31-day month, below Render's workspace allowance of 750 Free instance hours.
Render can still restart Free services for maintenance; the bot reconnects
automatically and the next healthcheck detects failures.

### Central Discord admin configuration

Server administrators can manage reminders without editing GitHub secrets:

- `/setupreminders #channel @role` configures both required destinations atomically.
- `/adminconfig` shows the active channel, role, status, and schedule.
- `/setannouncement #channel` and `/setreminderrole @role` change one setting.
- `/reminders true|false` pauses or resumes all automatic reminders.
- `/testreminder` sends a mention-free test to the configured channel.

Equivalent `!` commands are available. Settings are stored in the topic of a
private `lowlands-bot-config` Discord channel, so they survive Render restarts
and deployments without another database. The bot requires **Manage Channels**
the first time it creates or later edits this private configuration channel.
GitHub reminder runs read this central configuration before every send and fall
back to the existing repository secrets until `/setupreminders` has been run.

Render configuration lives in `render.yaml`. For local development, copy
`.env.example` to `.env`, install `requirements.txt`, and run
`python -m league_bot.bot`.

## Tournament control

The tournament module is deliberately separate from the Season 2 league Sheets.
Install `apps-script/Tournament.gs` in the permanent GeoNederland Tournament
Admin spreadsheet. Its `Tournaments` registry stores every event and creates a
separate read-only Public bracket Sheet for each practice tournament, qualifier,
MBO tournament or LCQ. Player, match, game, party-link, result and log rows remain
in the Admin hub and are separated by `Tournament ID`; starting a new event never
resets an older one.

Deploy the Tournament Admin Apps Script as a web app that executes as the owner and
is accessible to anyone with the deployment URL. Authentication is still required:
create a 32+ character secret through **Tournament Control → Set Discord API secret**
and configure these Render environment variables with matching values:

- `TOURNAMENT_API_URL`: the Apps Script `/exec` deployment URL.
- `TOURNAMENT_API_SECRET`: the secret stored in Apps Script Properties.

Player commands:

- `/inschrijven`, `/register`, `!inschrijven` or `!register`: tournament registration.
- `/inchecken`, `/checkin`, `!inchecken` or `!checkin`: confirm attendance.
- `/uitschrijven`, `/unregister`, `!uitschrijven` or `!unregister`: withdraw while preserving the audit trail.
- `/mijnwedstrijd`, `/mymatch`, `!mijnwedstrijd` or `!mymatch`: readiness, presets, party and result submission.
- `/schema`, `/bracket`, `!schema` or `!bracket`: current public bracket summary.
- `/reglement`, `/rules`, `!reglement` or `!rules`: open the regulations for the active tournament.

Admin commands:

- `/wedstrijduitlichten`, `/wedstrijdvrijgeven`, and `/uitslagbevestigen`.
- English aliases remain `/highlightmatch`, `/releasematch`, and `/resolvematch`.
- Prefix equivalents use `!highlightmatch`, `!releasematch`, and `!resolvematch`.

Result links enter `Pending review` in the first practice version. An administrator
confirms the winner with `resolvematch`; automatic GeoGuessr result parsing can be
added after a real Party result response has been captured during the rehearsal.

The bracket generator supports tournament limits of 8, 16, 32 and 64 players and
uses the smallest suitable power-of-two bracket unless an administrator overrides
`Bracket Size`. Larger brackets render as mirrored left and right halves converging
on the final in the centre.

Set `Rules URL` on the active row in the Admin Sheet's `Tournaments` tab. That
single link is shown in the public bracket, Discord bracket, personal match card,
and the dedicated rules commands.

Player 1 is always the upper player in the public bracket and the left player in
Discord reading order. Player 1 creates the GeoGuessr party and submits its link
after both players are ready. Player 2 joins through that link. Administrators
and casters can use the stored party link for spectating. The API rejects party
links submitted by Player 2; either participant may still submit a result link.

### Tournament Liquipedia test export

`.github/workflows/publish-tournament-test.yml` reads one tournament from the
authenticated Tournament Apps Script API, validates that it is a 2, 4, 8, 16,
32 or 64-player single-elimination bracket and generates native GeoGuessr
Liquipedia wikicode. Participants use `ParticipantTable`; results use
`Bracket/2` through `Bracket/64`, `Match` and `SoloOpponent`. Scores, flags,
scheduled times and completed states come from the Tournament Admin data.

The first stage can publish only to `User:DialloBOT/test`. It cannot edit a
production tournament page. Run it manually from **Actions → Publish tournament
test to Liquipedia**, enter the exact `Tournament ID`, then inspect both the page
and the uploaded `tournament-wikicode.txt` artifact.

In addition to the existing Liquipedia bot secrets, configure these GitHub
Actions repository secrets:

- `TOURNAMENT_API_URL`: the Apps Script `/exec` deployment URL.
- `TOURNAMENT_API_SECRET`: the same 32+ character secret used by the Discord bot.

Production tournament pages deliberately remain disabled until the test output
has been approved. Enabling them later requires a separate production marker,
an explicit page-title allowlist and managed-section adoption; never add a broad
page prefix or arbitrary page-title input.

