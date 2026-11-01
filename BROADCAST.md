# Livestream graphics (vMix · GT Title · CasparCG · UE5 · After Effects)

De Render-service die de Discord-bot draait, levert ook live broadcast-graphics.
Alle data komt uit dezelfde bronnen als de bot en de website: de toernooi-Admin
sheet (via de publieke, gefilterde `public_tournament`-export) en de Lowlands
League sheet. Partylinks, Discord-ID's en andere privégegevens komen nooit in
een feed.

```
Admin sheet ──► Apps Script web app ──► Render (/broadcast) ──► vMix  (Browser input of GT Title + Data Source)
League sheet ─────────────────────────┘                      ├─► CasparCG ([HTML] producer)
                                                             ├─► Unreal Engine 5 (HTTP/JSON of Web Browser widget)
                                                             └─► After Effects (JSON/CSV voor data-driven renders)
```

Overzichtspagina met alle links: `https://<render-service>/broadcast/`

## Wat er is

### 1. Kant-en-klare HTML-overlays (1920×1080, transparant)

| Overlay | URL | Gebruik |
| --- | --- | --- |
| Scorebug | `/broadcast/overlay/scorebug` | Bovenin tijdens de wedstrijd: spelers, vlaggen, seeds, seriescore, pips per gewonnen game |
| Matchup | `/broadcast/overlay/matchup` | Full-screen versus-kaart met GeoGuessr-avatars, voor de wedstrijd |
| Bracket | `/broadcast/overlay/bracket` | Volledige bracket; `?rounds=Semifinal,Final` of `?from=2` voor een deel |
| Schedule | `/broadcast/overlay/schedule` | Lopende en komende wedstrijden met Amsterdamse tijden |
| Standings | `/broadcast/overlay/standings` | Lowlands League top 16; `?limit=8`, `?mode=nmpz`, `?title=`, `?sub=` |
| Lower third | `/broadcast/overlay/lowerthird` | Naam + functie uit het regiepaneel; `?mode=casters` toont beide casters |
| Ticker | `/broadcast/overlay/ticker` | Crawl onderin: tickertekst, recente uitslagen, komende wedstrijden |
| Regiepaneel | `/broadcast/overlay/control` | Bediening voor de regisseur (zie hieronder) |

Algemene parameters: `?tournament=<id>` (ander toernooi dan het actieve),
`?match=<id>` (vaste wedstrijd), `?poll=5` (verversen in seconden),
`?accent=f47806` (accentkleur), `?autoplay=0` (wachten op CasparCG `play()`),
`?preview=1` (dambordachtergrond om de layout in een gewone browser te checken).

### 2. Datafeeds voor GT Title, UE5 en After Effects

Iedere feed bestaat als `.json` (array van objecten), `.csv` en `.xml`. Alle
waarden zijn platte strings, zodat ze direct aan tekst- en afbeeldingsvelden
gekoppeld kunnen worden.

| Feed | Rijen |
| --- | --- |
| `/broadcast/feed/match.json` | Precies één rij: de uitgelichte wedstrijd |
| `/broadcast/feed/matches.json` | Alle wedstrijden van het toernooi |
| `/broadcast/feed/bracket.json` | Alle wedstrijden met `round_index` en `slot` |
| `/broadcast/feed/schedule.json` | Lopende en komende wedstrijden (`?limit=8`) |
| `/broadcast/feed/participants.json` | Deelnemers met seed, land, vlag, avatar, eindplaats |
| `/broadcast/feed/tournament.json` | Toernooinaam, status, huidige ronde, casters, tickertekst |
| `/broadcast/feed/standings.json` | Lowlands League stand (`?limit=16`) |
| `/broadcast/feed/control.json` | Huidige instellingen van het regiepaneel |

Velden van een wedstrijdrij: `tournament`, `match_id`, `round`, `best_of`,
`first_to`, `format`, `status`, `live`, `scheduled` (`19:30`), `scheduled_day`
(`za 12 dec`), `series_score`, `winner`, en per speler (`p1_…` en `p2_…`):
`name`, `name_upper`, `seed`, `country`, `flag` (PNG-URL), `avatar` (PNG-URL),
`score`, `winner` (`1` als deze speler gewonnen heeft).

**Welke wedstrijd is "uitgelicht"?** In volgorde: de wedstrijd die in het
regiepaneel is gekozen; anders een in de sheet uitgelichte (`/wedstrijduitlichten`)
wedstrijd die live is; anders de volgende uitgelichte; anders de eerstvolgende
open wedstrijd van de bracket.

## Installatie op Render

Zet in het Render-dashboard bij de service:

| Variabele | Waarde |
| --- | --- |
| `BROADCAST_CONTROL_SECRET` | Willekeurige geheime string (≥ 32 tekens) voor het regiepaneel |
| `BROADCAST_TOURNAMENT_ID` | Optioneel: vast toernooi-ID; leeg = het actieve toernooi |
| `BROADCAST_CACHE_SECONDS` | Optioneel, standaard `8`: zo vaak wordt de Apps Script-export opgehaald |

`TOURNAMENT_API_URL` en `TOURNAMENT_API_SECRET` staan er al voor de bot.

## Regiepaneel

Open `/broadcast/overlay/control` op de regie-laptop en vul het control secret in
(wordt alleen in die browser onthouden). Je kunt:

- een ander toernooi of een specifieke wedstrijd op de scorebug zetten;
- **live de gamestand bijhouden** (+/−) terwijl een Bo3/Bo5 bezig is. De sheet
  krijgt de seriescore pas bij de uitslag; zodra de wedstrijd daar op
  `Complete` staat, geldt weer de officiële score uit de sheet;
- casters en tickertekst invullen;
- een lower third tonen en verbergen.

De instellingen staan in het geheugen van de Render-service. Na een herstart of
deploy zijn ze leeg (de sheetdata blijft gewoon werken): vul ze vlak voor de
uitzending in en deploy niet tijdens een stream.

## vMix

### Optie A — HTML-overlays als Browser input (snelst, aanbevolen om mee te starten)

1. **Add Input → Web Browser**, URL bijvoorbeeld
   `https://<render-service>/broadcast/overlay/scorebug`, resolutie 1920×1080.
2. De achtergrond is transparant; zet de input op een **Overlay-kanaal** (1–4) en
   gebruik de overlay-knoppen of shortcuts om hem in/uit te faden.
3. Maak per graphic een aparte input (scorebug, matchup, bracket, …) zodat je
   ze los kunt schakelen.
4. Herlaad een input via rechtermuisklik → *Refresh* als je de layout aanpast.

### Optie B — GT Title met vMix Data Sources (eigen huisstijl in GT Designer)

1. Ontwerp de title in **GT Designer** (bijv. `Scorebug.gtzip`) met tekstvelden
   zoals `P1Name`, `P1Score`, `P2Name`, `P2Score`, `Round` en afbeeldingsvelden
   `P1Flag`, `P2Flag`. Animaties (in/uit) maak je in GT Designer zelf
   (*Storyboard*: `TransitionIn` / `TransitionOut`).
2. vMix: **Settings → Data Sources → Add → JSON**, URL
   `https://<render-service>/broadcast/feed/match.json`, *Auto Refresh* op 2–5
   seconden. Voor tabellen (schedule, standings, bracket) maak je per feed een
   eigen data source; elke JSON-rij wordt een rij in vMix.
3. Open de title-input → **Data Source** en koppel elk veld aan een kolom
   (`P1Name` → `p1_name_upper`, `P1Flag` → `p1_flag`, enz.). Voor lijsten
   (schedule, standings) koppel je elke regel van de title aan rij 1, 2, 3 …
4. Afbeeldingsvelden accepteren de URL's in `p1_flag` / `p1_avatar` direct.

Je kunt A en B mengen: bijvoorbeeld de bracket als HTML-overlay en de scorebug
als GT Title.

### After Effects

After Effects is geen live-renderer, maar is ideaal voor wat vooraf kan:

- **Stingers en intro's**: render als QuickTime ProRes 4444 *met alpha* en
  gebruik ze in vMix als *Stinger transition* of als video-input op een
  overlay-kanaal.
- **Geanimeerde elementen voor GT**: render loops/achtergronden met alpha en
  zet ze als video- of image-sequence-laag in GT Designer.
- **Spelerskaarten per deelnemer (data-driven)**: download
  `/broadcast/feed/participants.json` (of `.csv`), importeer die in After
  Effects (*File → Import*) en koppel tekstlagen via expressions, bijvoorbeeld
  `footage("participants.json").sourceData[index].player`. Voor batch-renders
  van alle spelers werken *Essential Graphics* + *Templater* of *nexrender* met
  dezelfde JSON. Avatars en vlaggen staan als URL in de feed; download ze vooraf
  in een map en verwijs daarnaar.

## CasparCG (2.3 of nieuwer)

Elke overlay is ook een geldige CasparCG HTML-template (`play()`, `stop()`,
`next()`, `update()`):

```
PLAY 1-20 [HTML] "https://<render-service>/broadcast/overlay/scorebug?autoplay=0"
CALL 1-20 "play()"
CALL 1-20 "stop()"
```

Lower third met eigen tekst vanuit de CasparCG Client:
`CALL 1-30 "update('{\"title\":\"Anna de Vries\",\"subtitle\":\"Caster\"}')"`.
Stuur de CasparCG-output naar vMix via **NDI** (alpha blijft behouden) of via
DeckLink key/fill.

## Unreal Engine 5

- **Eenvoudig**: een *Web Browser*-widget in UMG met de overlay-URL, of de
  overlay als vMix-input boven de UE5-output.
- **Native**: poll `/broadcast/feed/match.json` met het *HTTP*-module of de
  *VaRest*-plugin (elke 2–5 seconden) en zet de waarden in je 3D-tekst/UMG
  (bijv. een virtuele studio met 3D-bracket). Stuur de output naar vMix met
  NDI (bijv. Off World Live) inclusief alpha.

## Betrouwbaarheid tijdens een uitzending

- De Apps Script-export wordt maximaal één keer per `BROADCAST_CACHE_SECONDS`
  opgehaald, hoeveel inputs er ook pollen. Een uitslag staat dus binnen ±10
  seconden op beeld.
- Als Google of Apps Script even niet antwoordt, blijft de **laatste goede data
  op beeld** (de feed geeft dan header `X-Broadcast-Stale: 1`; overlays tonen
  rechtsboven een klein geel puntje). Graphics worden nooit leeg door een storing.
- Render Free slaapt na 15 minuten zonder verkeer; de bestaande keepalive en de
  pollende overlays houden de service wakker. Open de overlays een half uur voor
  de uitzending, controleer `/health` en het regiepaneel, en deploy niet tijdens
  de stream. Voor grote uitzendingen is een betaald Render-plan (geen cold
  starts) het overwegen waard.
- Vlaggen komen van `flagcdn.com`, avatars van GeoGuessr en het lettertype van
  Google Fonts: de streaming-pc heeft dus internet nodig (dat heeft hij voor de
  stream toch al). Afbeeldingen die niet laden worden verborgen in plaats van als
  kapot icoon getoond.
