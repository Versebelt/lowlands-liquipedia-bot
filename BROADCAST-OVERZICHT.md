# Livestream graphics — overzicht van wat er is gebouwd

Dit document beschrijft wat er is toegevoegd om de GeoGuessr-livestream van
broadcast-graphics te voorzien. De handleiding voor het gebruik per tool (vMix,
GT Title, CasparCG, Unreal Engine 5, After Effects) staat in
[BROADCAST.md](BROADCAST.md).

## In het kort

De bestaande Render-service (de Discord-bot) heeft er een extra onderdeel bij:
`/broadcast/`. Dat levert drie dingen:

1. **Kant-en-klare graphics**: transparante HTML-pagina's van 1920×1080 die je
   in vMix als *Web Browser* input op een overlay-kanaal zet, of in CasparCG
   afspeelt.
2. **Datafeeds** in JSON, CSV en XML, waarmee je eigen ontwerpen in vMix GT
   Title, Unreal Engine 5 of After Effects automatisch met live data vult.
3. **Een regiepaneel** waarmee de regisseur tijdens de uitzending de gamestand,
   casters, ticker en lower third bedient.

Alle data komt uit dezelfde bronnen als de Discord-bot en de website: de
toernooi-Admin sheet (via de bestaande Apps Script web app) en de Lowlands
League sheet. Er hoeft niets dubbel ingevoerd te worden: een uitslag die via
Discord of de sheet wordt bevestigd, staat binnen ongeveer 10 seconden op beeld.

```
Admin sheet ──► Apps Script web app ──► Render (/broadcast) ──► vMix (Browser input of GT Title + Data Source)
League sheet ─────────────────────────┘                      ├─► CasparCG ([HTML] producer)
                                                             ├─► Unreal Engine 5 (HTTP/JSON)
                                                             └─► After Effects (JSON/CSV)
```

## 1. Graphics (HTML-overlays)

Allemaal 1920×1080 met een transparante achtergrond, in de GeoNederland-kleuren
(navy, oranje, geel) met het lettertype Barlow Condensed. Ze faden en schuiven
netjes in en uit en verversen zichzelf automatisch.

| Graphic | Adres | Wat je ziet |
| --- | --- | --- |
| Scorebug | `/broadcast/overlay/scorebug` | Balk bovenin: beide spelers met vlag en seed, stand in de serie, een streepje per gewonnen game, ronde en "Best of 3/5", toernooinaam eronder. De winnaar krijgt een gele lijn. |
| Matchup | `/broadcast/overlay/matchup` | Versus-kaart over het hele scherm met de GeoGuessr-avatars, namen, vlaggen, seeds, ronde, tijdstip of "Live" en de seriestand. |
| Bracket | `/broadcast/overlay/bracket` | De volledige bracket per ronde, met uitslagen, winnaars in geel, verliezers gedimd en de uitgelichte/live wedstrijd gemarkeerd. Grote brackets worden automatisch verkleind zodat ze in beeld passen. |
| Schedule | `/broadcast/overlay/schedule` | Lopende en komende wedstrijden met Amsterdamse tijden; de live wedstrijd staat bovenaan. |
| Standings | `/broadcast/overlay/standings` | Top 16 van de Lowlands League in twee kolommen, top 3 uitgelicht. Ook per spelmodus (Moving, NM, NMPZ). |
| Lower third | `/broadcast/overlay/lowerthird` | Naam en functie linksonder, bediend vanuit het regiepaneel; of beide casters links en rechts. |
| Ticker | `/broadcast/overlay/ticker` | Lopende tekstbalk onderin: eigen bericht, recente uitslagen en komende wedstrijden. |

Instelbaar via het adres, bijvoorbeeld `?match=QF3` (vaste wedstrijd),
`?tournament=nk27-oq1` (ander toernooi), `?rounds=Semifinal,Final` (deel van de
bracket), `?limit=8`, `?mode=nmpz`, `?accent=f47806` (accentkleur) en
`?preview=1` (dambordachtergrond om de layout in een gewone browser te bekijken).

Elke graphic werkt ook als CasparCG-template (`play()`, `stop()`, `next()`,
`update()`).

## 2. Datafeeds

Voor wie de graphics zelf wil ontwerpen in vMix GT Designer, Unreal Engine of
After Effects. Elke feed is beschikbaar als `.json`, `.csv` en `.xml`; alle
waarden zijn platte tekst, zodat je ze direct aan tekst- en afbeeldingsvelden
koppelt.

| Feed | Inhoud |
| --- | --- |
| `match` | Eén rij: de wedstrijd die nu centraal staat (voor de scorebug) |
| `matches` | Alle wedstrijden van het toernooi |
| `bracket` | Alle wedstrijden met rondenummer en positie, voor een eigen bracket-layout |
| `schedule` | Lopende en komende wedstrijden |
| `participants` | Deelnemers met seed, land, vlag, avatar en eindplaats |
| `tournament` | Toernooinaam, status, huidige ronde, aantal gespeelde wedstrijden, casters, tickertekst |
| `standings` | Lowlands League-stand |
| `control` | Wat er in het regiepaneel is ingesteld |

Een wedstrijdrij bevat onder meer: ronde, Best of, "first to", status, tijdstip
(`19:30`) en dag (`za 12 dec`) in Amsterdamse tijd, seriestand, winnaar, en per
speler naam (ook in hoofdletters), seed, land, vlag-URL, avatar-URL, score en of
die speler gewonnen heeft.

**Welke wedstrijd staat centraal?** Automatisch, in deze volgorde:

1. de wedstrijd die in het regiepaneel is gekozen;
2. een in de sheet uitgelichte wedstrijd (`/wedstrijduitlichten`) die live is;
3. de volgende uitgelichte wedstrijd;
4. de eerstvolgende open wedstrijd in de bracket.

## 3. Regiepaneel

Adres: `/broadcast/overlay/control`. Beveiligd met een geheime sleutel
(`BROADCAST_CONTROL_SECRET`) die de regisseur één keer invult; de browser
onthoudt hem.

- **Toernooi kiezen**: het actieve toernooi of een specifiek toernooi-ID.
- **Wedstrijd kiezen** voor de scorebug, of automatisch laten kiezen.
- **Gamestand live bijhouden** met +/− knoppen. De sheet krijgt de seriestand
  pas bij de definitieve uitslag; met het paneel loopt de scorebug tijdens een
  Bo3/Bo5 per game mee. Zodra de wedstrijd in de sheet op `Complete` staat,
  geldt automatisch weer de officiële uitslag. "Score uit sheet" zet de
  handmatige stand terug.
- **Casters en tickertekst** invullen.
- **Lower third** met titel en ondertitel tonen of verbergen.
- **Live preview** van de scorebug onderaan de pagina.

## 4. Overzichtspagina

`/broadcast/` toont alle graphics en feeds met hun volledige adressen, zodat je
ze makkelijk in vMix, CasparCG of UE5 kunt plakken.

## Betrouwbaarheid en veiligheid

- **Geen privégegevens op beeld**: alleen de bestaande publieke, gefilterde
  toernooi-export wordt gebruikt. Partylinks, Discord-ID's en andere interne
  gegevens komen nooit in een feed. Spelersnamen worden altijd als platte tekst
  weergegeven, nooit als HTML.
- **Weinig belasting**: hoeveel vMix-inputs er ook verversen, de Apps Script
  web app wordt hooguit één keer per 8 seconden opgevraagd.
- **Nooit lege graphics**: als Google of Apps Script even niet antwoordt, blijft
  de laatste goede data op beeld. Een klein geel puntje rechtsboven in de
  graphic laat dat zien.
- **Geen kapotte plaatjes**: een vlag of avatar die niet laadt, wordt verborgen;
  bij de matchup verschijnt dan een "?" als placeholder.
- **Regiepaneel beveiligd**: wijzigen kan alleen met de geheime sleutel; alle
  invoer wordt gecontroleerd en ingekort.
- **Let op**: de instellingen van het regiepaneel staan in het geheugen van de
  Render-service en zijn na een herstart of deploy leeg. De sheetdata blijft
  gewoon werken. Vul het paneel dus vlak voor de uitzending in en deploy niet
  tijdens een stream.

## Wat er in de repository is veranderd

| Bestand | Wat |
| --- | --- |
| `league_bot/broadcast.py` | Nieuw: feeds, keuze van de uitgelichte wedstrijd, caching, regiepaneel en webadressen |
| `league_bot/broadcast_static/` | Nieuw: de zeven graphics, het regiepaneel, de overzichtspagina en gedeelde CSS/JavaScript |
| `league_bot/bot.py` | Koppelt `/broadcast/` aan de bestaande webserver van de bot (2 regels) |
| `tests/test_broadcast.py` | Nieuw: 20 tests voor feeds, wedstrijdkeuze, beveiliging, caching en storingsgedrag |
| `BROADCAST.md` | Nieuw: handleiding per tool |
| `BROADCAST-OVERZICHT.md` | Dit document |
| `README.md` | Korte verwijzing naar de broadcast-documentatie |
| `render.yaml`, `.env.example` | Nieuwe instellingen `BROADCAST_CONTROL_SECRET` en `BROADCAST_TOURNAMENT_ID` |

Er is niets veranderd aan de Apps Script-code, de sheets, de Discord-commando's
of de Liquipedia-publicatie.

## Getest

- Alle Python-tests (74, waarvan 20 nieuw) en Node-tests (26) slagen.
- Elke graphic en het regiepaneel zijn in Chromium gerenderd met nepdata en
  visueel gecontroleerd.
- **Nog niet getest**: met echte toernooidata, en in vMix, CasparCG of UE5 zelf.
  Doe dat vóór de eerste uitzending.

## Nog te doen

1. **GitHub-toegang herstellen** zodat de wijzigingen gepusht kunnen worden
   (via https://claude.ai/connect-github; de Claude GitHub App moet op de
   repository staan).
2. **Op Render instellen**: `BROADCAST_CONTROL_SECRET` (willekeurig, minstens
   32 tekens) en eventueel `BROADCAST_TOURNAMENT_ID`.
3. **Testen in vMix**: de scorebug als Web Browser input toevoegen en met een
   oefentoernooi controleren.
4. Eventueel: eigen ontwerpen maken in GT Designer of After Effects op basis van
   de feeds (zie [BROADCAST.md](BROADCAST.md)).
