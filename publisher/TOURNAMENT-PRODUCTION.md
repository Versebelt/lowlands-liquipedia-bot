# Tournament publishing to real Liquipedia pages — design

Status: proposal only. Nothing in this repository publishes tournaments outside
`User:DialloBOT/test` yet, and implementing this design needs explicit approval.

## Goal

Publish a finished (or running) GeoNederland tournament from the Admin sheet to
its own Liquipedia page, without ever touching a page or section the bot does not
own, and without manual copy-paste.

## Building blocks

1. **Mapping file** `publisher/tournament-pages.json`, reviewed in Git:

   ```json
   {
     "nk27-oq1": {
       "page": "GeoNederland/NK/2027/Open_Qualifier_1",
       "bracket_id_source": "production"
     }
   }
   ```

   The workflow only accepts tournament IDs listed here, and only publishes to the
   page mapped to that ID. `LIQUIPEDIA_ALLOWED_TITLES` stays as a second, independent
   allowlist in the environment.

2. **Section markers** instead of whole-page ownership. Editors keep the prose,
   infobox and prize pool; the bot replaces only the text between

   ```
   <!-- GEONEDERLAND_BOT_START participants -->
   ...
   <!-- GEONEDERLAND_BOT_END participants -->
   <!-- GEONEDERLAND_BOT_START bracket -->
   ...
   <!-- GEONEDERLAND_BOT_END bracket -->
   ```

   A missing, duplicated or nested marker is a safety stop. The first adoption of
   a page is a manual edit by a person who adds the markers.

3. **Separate bracket IDs for test and production.** The Tournaments tab gets a
   second column `Liquipedia Production Bracket ID` (10 letters/digits, generated
   once, never reused). The test page keeps using `Liquipedia Bracket ID`, so test
   runs never create LPDB match records that collide with the real page.

4. **Protected GitHub environment** `liquipedia-production`, with required
   reviewers, holding the bot password. The test workflow keeps its own
   environment without reviewers.

## Flow

1. An admin runs the workflow with a tournament ID (later: a sheet menu item that
   dispatches it).
2. The exporter fetches `public_tournament`, validates it (bracket size, slots
   from match IDs, 10-character production ID, escaping) and renders only the
   managed sections.
3. The publisher fetches the current page, checks the markers, splices the new
   sections in, and compares the result with the current text after trimming
   trailing whitespace. If nothing changed it stops with `NoChange`.
4. The environment reviewer approves the run; the edit is made with
   `baserevid`/`basetimestamp`, so a concurrent human edit causes a conflict
   instead of being overwritten.
5. The generated wikicode and the result are uploaded as run artifacts.

## Auto-publish (later)

Only after several manual runs succeed: a scheduled run (for example every 15
minutes during a tournament day) for tournaments whose status is `Live`, using
the same protected environment. Keep it off by default per tournament with an
`auto_publish` flag in the mapping file, and rate-limit to one edit per page per
run to respect Liquipedia's bot rules.

## Open questions for the owner

- Final page titles and naming scheme on Liquipedia GeoGuessr.
- Whether BYE rendering (`{{LiteralOpponent|BYE}}` with `|winner=`) looks right
  on the test page; adjust before production if not.
- Who besides the owner may approve production runs.
