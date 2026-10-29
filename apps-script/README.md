# GeoNederland Tournament Control

This is a separate Apps Script project for the tournament system. Do not add it
to either Lowlands League Season 2 spreadsheet.

## Sheets

- Admin: `GeoNederland Tournament Control - Admin`
- Public: `GeoNederland Tournament - Public Bracket`

The Admin sheet owns all state. The Public sheet contains only the bracket and
schedule generated from that state.

## Installation

1. Open the new Admin spreadsheet.
2. Choose **Extensions → Apps Script**.
3. Replace the starter source with `Code.gs` and save.
4. Reload the Admin spreadsheet and run **Tournament Control → Set up / repair Admin sheet**.
5. Run **Tournament Control → Set up / repair Public bracket**.
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

## Practice tournament

Add exactly eight rows to `Tournament Players`, including seed, Discord username
(or an exact user ID) and a checked `Checked In` box. Then run **Generate 8-player practice
bracket**. The generated bracket uses 1–8, 4–5, 2–7 and 3–6 quarterfinal pairings.

Party and result links arrive through Discord. Result links remain pending until
an administrator confirms the winner. This is intentional for the rehearsal;
automatic parsing will be added after capturing a real GeoGuessr Party result.
