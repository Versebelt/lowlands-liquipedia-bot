# GeoNederland Tournament Control

This is a separate Apps Script project for the tournament system. Do not add it
to either Lowlands League Season 2 spreadsheet.

## Sheets

- Admin: `GeoNederland Tournament Control - Admin`
- Public: `GeoNederland Tournament - Public Bracket`

The Admin sheet is a permanent tournament hub. Every event has a stable
`Tournament ID`; player registrations, matches, games, party links, results and
logs are tagged with that ID and are never reset for the next event. The
`Tournaments` tab links each event to its own read-only Public bracket Sheet.

## Installation

1. Open the new Admin spreadsheet.
2. Choose **Extensions → Apps Script**.
3. Replace the starter source with `Tournament.gs` and save.
4. Reload the Admin spreadsheet and run **Tournament Control → Set up / repair Admin sheet**.
5. Use **Tournament Control → Create new tournament** for every practice event,
   qualifier, MBO event or LCQ. This automatically creates its Public Sheet.
6. Set a random secret of at least 32 characters through **Set Discord API secret**.
7. Deploy the script as a web app, executing as the owner and accessible to anyone with the URL.
8. Put the `/exec` URL and the same secret in Render as `TOURNAMENT_API_URL` and `TOURNAMENT_API_SECRET`.

The secret is required for every request. The public bracket spreadsheet ID is
already present in the initial Admin spreadsheet created for this project.

## Staging and production deploys

`.github/workflows/deploy-apps-script.yml` has two isolated targets:

- pushes to `broadcast-koppeling` deploy to the GitHub Environment `staging`;
- pushes to `main` target the GitHub Environment `production`;
- a manual run can explicitly select either target.

Create both environments under **Settings → Environments**. Configure
`production` with at least one required reviewer. This makes a merge to `main`
run the tests immediately but pause before touching the live Apps Script project.
Staging must use its own Admin spreadsheet, Apps Script project, web-app
deployment and API secret. Never point staging at the production spreadsheet.

Both environments need the same secret names, but with values belonging to that
environment:

- `DEPLOY_ENVIRONMENT`: exactly `staging` or `production`, matching the Environment;
- `CLASPRC_JSON`: the contents of `~/.clasprc.json` after `clasp login`;
- `APPS_SCRIPT_ID`: the script ID of that environment's Tournament Control project;
- `APPS_SCRIPT_DEPLOYMENT_ID`: that environment's web-app deployment ID;
- `TOURNAMENT_API_URL` and `TOURNAMENT_API_SECRET`: that environment's `/exec`
  URL and secret, used for the post-deploy health check.

`DEPLOY_ENVIRONMENT` is an intentional guard against GitHub falling back to
repository-level secrets when an Environment is empty or misconfigured. Without
the guard the job fails before it can deploy a script. Without the next three
deployment secrets the workflow skips the deploy with a warning. After a deploy
that adds sheet columns, run **Set up / repair Admin sheet** once in the matching
environment.

## Player registration

Players register through Discord with `/register` or
`!register <player name> | <GeoGuessr profile URL> | <NL|BE|LU>`. The bot sends
their Discord identity to the web app, which creates or updates their row in
`Tournament Players`. Duplicate Discord accounts, GeoGuessr accounts and player
names are rejected.

`/checkin` marks the player as present during the active tournament's configured
`Check-in Opens At` / `Check-in Closes At` window. Blank fields keep the legacy
always-open behaviour. Only checked-in players are eligible for
bracket generation. `/unregister` keeps the audit trail but changes the player to
`Withdrawn` instead of deleting the row.

Set `Auto-generate Official Bracket` in the `Tournaments` tab to let the five-minute
Apps Script trigger create the official bracket once check-in closes. Existing
official matches are never overwritten automatically. The menu action `Generate
preview bracket — all registered` renders a clearly labelled `Proefbracket` tab in
the public spreadsheet without creating match records or affecting Discord,
website results, or Liquipedia. Every included player needs a unique seed; when
no-shows create gaps, the official bracket preserves the order and compresses the
remaining seeds automatically.

## Manual seeding and bracket generation

Enter a manual number in the `Seed` column for every checked-in player. Seeds
must be unique and consecutive from `1` through the number of eligible players.
Use **Tournament Control → Validate player seeding** to check the list, followed
by **Generate bracket**. Missing, duplicate, invalid or skipped seeds block
generation with a clear error instead of silently changing the placements.

Alternatively, use **Randomize player seeding** to assign unique random seeds
`1` through the number of checked-in players. The action asks for confirmation
before replacing any existing seeds and affects only the active tournament.

Before any bracket has been generated, every Public Sheet shows a complete empty
32-player bracket. Once generated, it switches to the actual configured bracket
size and places players according to the manual seeds.

Party and result links arrive through Discord. Result links remain pending until
an administrator confirms the winner. This is intentional for the rehearsal;
automatic parsing will be added after capturing a real GeoGuessr Party result.

Set `Rules URL` on the active row of `Tournaments`. The public bracket and the
Discord commands `/reglement`, `/rules`, `!reglement` and `!rules` all use this
same link.

Player 1 is the upper player in the bracket and the left player in Discord.
Player 1 hosts the GeoGuessr party and is the only participant allowed to submit
the party link. Player 2 joins through that link; administrators and casters use
the stored link when they need to spectate the match.

## Multiple tournaments and archives

- **Create new tournament** makes a registry row and a separate Public Sheet.
- **Switch active tournament** changes which tournament Discord commands and
  Admin actions operate on.
- **Archive active tournament** closes registration without deleting any data.
- The central tables retain every historical row and can be filtered by
  `Tournament ID`.

`Event`, `Event Phase` and `Event Qualifies` link tournaments to a multi-stage
event such as the NK. Example for the first NK 2027 qualifier: `Event` =
`nk-2027`, `Event Phase` = `oq1` (the phase ID from `content/nk-2027.json` on
the website) and `Event Qualifies` = `4`. The website then shows this tournament
on the NK hub automatically. Once its final has a winner, the top
`Event Qualifies` players count as qualified: they can no longer register for
or check in to another tournament of the same event (matched on Discord user ID
or GeoGuessr user ID). Players who registered elsewhere before qualifying are
not removed automatically, but their check-in is refused. This block applies
only to tournaments that are qualifiers themselves (`Event Qualifies` of 1 or
more), so qualified players can still enter later phases such as the group
stage.

`Entry From` limits who may register and check in. List final places of other
tournaments as `tournament-id:from-to` and invitations as a bare Discord or
GeoGuessr user ID, separated by commas. Leave it empty for open registration.
Places are taken as they are: a player who has since qualified elsewhere is not
replaced by the next player ("unique entries, no replacement").

## Formats

The `Type` column chooses the bracket format:

- `Single Elimination` (and `Practice`): the classic bracket described below.
- `Double Elimination`: an upper and a lower bracket; a first loss drops a player
  to the lower bracket, a second loss eliminates. Without `Advance Count` it ends
  in a grand final (no bracket reset). With `Advance Count` (2, 4, 8 …) it stops
  once that many players remain, half unbeaten from the upper bracket and half
  from the lower bracket. Match IDs are `<id>-U1-M1`, `<id>-L1-M1` and
  `<id>-GF-M1`.
- `Round Robin`: `Groups` groups in which everyone plays everyone once. Seeds are
  spread snake-wise (seeds 1 to 4 each head a different group). Match IDs are
  `<id>-GA-S1-M1` (group A, matchday 1). Standings: match wins, then map
  difference, then maps won; remaining ties are for the organisers to settle.

Results work the same in every format: confirm the winner and score, and the
winner (and in double elimination the loser) moves to the next match
automatically. A player who meets a BYE there advances without playing. Final
placements for every format feed `Event Qualifies`, `Entry From` and the NK page
on the website. The Liquipedia export only supports single elimination and
refuses the other formats.

### NK 2027 set-up

| Tournament | Type | Event Phase | Event Qualifies | Other |
| --- | --- | --- | --- | --- |
| Open Qualifier 1–4 | Single Elimination | `oq1`–`oq4` | 4 | |
| ROCvA-F | Single Elimination | `rocvaf` | 0 | |
| Last Chance Qualifier | Single Elimination | `lcq` | 1 | `Entry From`: places `5-8` of each open qualifier, plus the two ROCvA-F players as user IDs |
| Group stage | Round Robin | `groups` | 0 | `Groups` = 4, `Entry From`: places `1-4` of each open qualifier, `1` of the LCQ and the invitations |
| Knockout stage | Double Elimination | `knockout` | 0 | `Advance Count` = 4, `Entry From`: group-stage places `5-12` (all runners-up and thirds) |
| Quarterfinals | Single Elimination | `quarterfinals` | 0 | `Entry From`: group-stage places `1-4` and knockout places `1-4` |

Every row uses `Event` = `nk-2027`. The ROCvA-F players are listed by user ID
because only eligible players may take those places.

Brackets support 2, 4, 8, 16, 32 and 64 players. **Create new tournament** offers
8, 16, 32 and 64 as registration limits; the actual bracket uses the smallest
suitable power of two unless `Bracket Size` is explicitly overridden. Players
drawn against a BYE advance automatically when the bracket is generated.

Type `Scheduled At` as a date cell (`yyyy-mm-dd hh:mm`) or as text in that
format; both are read as Europe/Amsterdam time, so set the spreadsheet time zone
to Europe/Amsterdam under **File -> Settings**. The public Schedule tab shows
Amsterdam time.

A match status never moves backwards: once a party link is submitted, Ready,
release and highlight no longer change the status, and closed matches reject
party links and results.

Liquipedia bracket IDs are exactly ten letters or digits. **Set up / repair Admin
sheet** replaces any older ID that does not match. Large brackets are rendered as two mirrored halves that converge on
the final in the centre. Brackets with up to eight players use the compact
left-to-right layout; brackets with 16 or more players always work from both
outer edges towards the centre.
