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

## Player registration

Players register through Discord with `/register` or
`!register <player name> | <GeoGuessr profile URL> | <NL|BE|LU>`. The bot sends
their Discord identity to the web app, which creates or updates their row in
`Tournament Players`. Duplicate Discord accounts, GeoGuessr accounts and player
names are rejected.

`/checkin` marks the player as present. Only checked-in players are eligible for
bracket generation. `/unregister` keeps the audit trail but changes the player to
`Withdrawn` instead of deleting the row.

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
