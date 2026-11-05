const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "apps-script", "Tournament.gs"), "utf8");

// Minimal SpreadsheetApp stand-in: each sheet is a header row plus value rows.
function sheet(name, headers, rows) {
  const values = [headers, ...rows.map((row) => headers.map((header) => row[header] ?? ""))];
  return {
    getName: () => name,
    getLastRow: () => values.length,
    getLastColumn: () => headers.length,
    getRange: (row, col, numRows, numCols) => {
      const block = values.slice(row - 1, row - 1 + numRows).map((line) => line.slice(col - 1, col - 1 + numCols));
      return {
        getValues: () => block, getDisplayValues: () => block.map((line) => line.map(String)),
        setValue: (value) => { values[row - 1][col - 1] = value; },
        setNumberFormat: () => {},
      };
    },
  };
}

function load({tournaments = [], players = [], matches = []} = {}) {
  const context = vm.createContext({console});
  vm.runInContext(source, context);
  const H = vm.runInContext("TOURNAMENT", context);
  const sheets = {
    [H.SHEETS.CONFIG]: sheet(H.SHEETS.CONFIG, H.HEADERS.CONFIG, [{Setting: "Default Best Of", Value: 3}]),
    [H.SHEETS.TOURNAMENTS]: sheet(H.SHEETS.TOURNAMENTS, H.HEADERS.TOURNAMENTS, tournaments),
    [H.SHEETS.PLAYERS]: sheet(H.SHEETS.PLAYERS, H.HEADERS.PLAYERS, players),
    [H.SHEETS.MATCHES]: sheet(H.SHEETS.MATCHES, H.HEADERS.MATCHES, matches),
  };
  context.SpreadsheetApp = {getActiveSpreadsheet: () => ({getSheetByName: (name) => sheets[name]})};
  context.H = H;
  return context;
}

const seededPlayers = (count) => Array.from({length: count}, (_, index) => ({Seed: index + 1, Player: "P" + (index + 1)}));
const seedOf = (name) => Number(String(name).slice(1));

// Plays every match the way the Discord flow does: the better seed wins, the
// winner and loser follow their links, and BYE walkovers resolve themselves.
function play(context, rows) {
  const H = context.H.HEADERS.MATCHES, col = (name) => H.indexOf(name);
  const find = (id) => rows.find((row) => row[col("Match ID")] === id);
  const place = (id, slot, name) => {
    const target = find(id);
    if (target) target[Number(slot) === 2 ? col("Player 2") : col("Player 1")] = name;
  };
  const losses = {};
  for (;;) {
    const match = rows.find((row) => !row[col("Winner")] && ![row[col("Player 1")], row[col("Player 2")]].some((name) => ["TBD", "BYE"].includes(name)));
    if (!match) break;
    const [p1, p2] = [match[col("Player 1")], match[col("Player 2")]];
    const winner = seedOf(p1) < seedOf(p2) ? p1 : p2, loser = winner === p1 ? p2 : p1;
    match[col("Winner")] = winner;
    match[col("Series Score")] = "2-1";
    losses[loser] = (losses[loser] || 0) + 1;
    place(match[col("Next Match ID")], match[col("Next Slot")], winner);
    place(match[col("Loser Match ID")], match[col("Loser Slot")], loser);
    context.tournamentAdvanceByes_(rows);
  }
  const publicMatches = rows.map((values) => context.tournamentMatchValuesToPublic_(values));
  return {losses, publicMatches, open: rows.filter((row) => !row[col("Winner")])};
}

test("full double elimination: everyone but the champion loses twice", () => {
  const context = load();
  const tournament = {"Tournament ID": "ko", Type: "Double Elimination"};
  const {rows} = context.tournamentBuildBracket_(tournament, seededPlayers(8), "checked-in");
  const rounds = rows.map((row) => row[1]);
  assert.equal(rows.length, 14);
  assert.deepEqual([...new Set(rounds)], ["Upper Round 1", "Upper Round 2", "Upper Final", "Lower Round 1", "Lower Round 2", "Lower Round 3", "Lower Final", "Grand Final"]);
  const {losses, publicMatches, open} = play(context, rows);
  assert.equal(open.length, 0);
  assert.deepEqual(Object.keys(losses).sort(), ["P2", "P3", "P4", "P5", "P6", "P7", "P8"]);
  Object.values(losses).forEach((count) => assert.equal(count, 2));
  const placements = Array.from(context.tournamentPlacementsFor_("double-elimination", publicMatches));
  assert.deepEqual(placements.slice(0, 3), ["P1", "P2", "P3"]);
  assert.equal(placements.length, 8);
});

test("knockout stage: double elimination that stops at four players", () => {
  const context = load();
  const tournament = {"Tournament ID": "nk27-ko", Type: "Double Elimination", "Advance Count": 4};
  const {rows} = context.tournamentBuildBracket_(tournament, seededPlayers(8), "checked-in");
  assert.equal(rows.length, 10);
  assert.ok(!rows.some((row) => row[1] === "Grand Final"));
  const {losses, publicMatches, open} = play(context, rows);
  assert.equal(open.length, 0);
  const placements = Array.from(context.tournamentPlacementsFor_("double-elimination", publicMatches));
  // Two unbeaten players from the upper bracket, two survivors of the lower bracket.
  assert.deepEqual(placements.slice(0, 4), ["P1", "P2", "P3", "P4"]);
  placements.slice(0, 4).forEach((name) => assert.ok((losses[name] || 0) < 2, name));
  placements.slice(4).forEach((name) => assert.equal(losses[name], 2, name));
});

test("double elimination with BYEs never leaves a player stuck", () => {
  const context = load();
  const {rows} = context.tournamentBuildBracket_({"Tournament ID": "ko", Type: "Double Elimination"}, seededPlayers(6), "checked-in");
  const {losses, publicMatches, open} = play(context, rows);
  assert.equal(open.length, 0);
  Object.values(losses).forEach((count) => assert.equal(count, 2));
  assert.deepEqual(Array.from(context.tournamentPlacementsFor_("double-elimination", publicMatches)).slice(0, 2), ["P1", "P2"]);
});

test("a result sends the loser down, and a BYE there is a walkover", () => {
  const built = load();
  const tournament = {"Tournament ID": "ko", Type: "Double Elimination"};
  const {rows} = built.tournamentBuildBracket_(tournament, seededPlayers(6), "checked-in");
  const headers = built.H.HEADERS.MATCHES, asObject = (values) => Object.fromEntries(headers.map((header, index) => [header, values[index]]));
  const context = load({tournaments: [tournament], matches: rows.map(asObject)});
  context.tournamentConfig_ = () => ({"Active Tournament ID": "ko"});
  // Upper round 1: P1 and P2 have a BYE, so the BYE already waits in lower round 1.
  assert.deepEqual([context.tournamentFindMatch_("ko-L1-M1")["Player 1"], context.tournamentFindMatch_("ko-L1-M1")["Player 2"]], ["BYE", "TBD"]);
  context.tournamentResolve_(context.tournamentFindMatch_("ko-U1-M2"), "admin", "P4", "2-0");
  assert.equal(context.tournamentFindMatch_("ko-U2-M1")["Player 2"], "P4");
  const lower = context.tournamentFindMatch_("ko-L1-M1");
  assert.deepEqual([lower["Player 2"], lower.Winner, lower.Status], ["P5", "P5", "Complete"]);
  assert.equal(context.tournamentFindMatch_("ko-L2-M1")["Player 1"], "P5");
});

test("unfinished double elimination has no placements", () => {
  const context = load();
  const {rows} = context.tournamentBuildBracket_({"Tournament ID": "ko", Type: "Double Elimination"}, seededPlayers(8), "checked-in");
  const publicMatches = rows.map((values) => context.tournamentMatchValuesToPublic_(values));
  assert.deepEqual(Array.from(context.tournamentPlacementsFor_("double-elimination", publicMatches)), []);
});

test("group stage: 20 players in 4 round-robin groups of 5", () => {
  const context = load();
  const tournament = {"Tournament ID": "nk27-groups", Type: "Round Robin", Groups: 4};
  const {rows} = context.tournamentBuildBracket_(tournament, seededPlayers(20), "checked-in");
  assert.equal(rows.length, 40);
  const groups = {};
  rows.forEach((row) => {
    groups[row[1]] = groups[row[1]] || new Set();
    groups[row[1]].add(row[3]); groups[row[1]].add(row[4]);
    assert.match(row[0], /^nk27-groups-G[A-D]-S\d-M\d$/);
  });
  assert.deepEqual(Object.keys(groups), ["Group A", "Group B", "Group C", "Group D"]);
  Object.values(groups).forEach((members) => assert.equal(members.size, 5));
  // Seeds 1-4 each lead a different group (snake seeding).
  ["P1", "P2", "P3", "P4"].forEach((name, index) => assert.ok(groups["Group " + "ABCD"[index]].has(name)));
  const pairs = rows.map((row) => [row[3], row[4]].sort().join("-"));
  assert.equal(new Set(pairs).size, 40);
  const {publicMatches, open} = play(context, rows);
  assert.equal(open.length, 0);
  const standings = Array.from(context.tournamentGroupStandings_(publicMatches));
  assert.equal(standings[0].standings[0].player, "P1");
  assert.equal(standings[0].standings[0].wins, 4);
  assert.equal(standings[0].standings[0].maps_won, 8);
  const placements = Array.from(context.tournamentPlacementsFor_("round-robin", publicMatches));
  assert.deepEqual(placements.slice(0, 4), ["P1", "P2", "P3", "P4"]);
  assert.equal(placements.length, 20);
});

test("single elimination still builds the same bracket", () => {
  const context = load();
  const {rows, bracketSize} = context.tournamentBuildBracket_({"Tournament ID": "oq", Type: "Single Elimination"}, seededPlayers(6), "checked-in");
  assert.equal(bracketSize, 8);
  assert.deepEqual(Array.from(rows, (row) => row[0]), ["oq-R1-M1", "oq-R1-M2", "oq-R1-M3", "oq-R1-M4", "oq-R2-M1", "oq-R2-M2", "oq-R3-M1"]);
  // Seeds 1 and 2 get a BYE and are already in round 2.
  assert.deepEqual([rows[4][3], rows[5][3]], ["P1", "P2"]);
  rows.forEach((row) => assert.equal(row[context.H.HEADERS.MATCHES.indexOf("Loser Match ID")], ""));
});

const match = (id, p1, p2, winner) => ({"Match ID": id, "Player 1": p1, "Player 2": p2, Winner: winner, "Tournament ID": id.split("-R")[0]});
const oq1Matches = [
  match("oq1-R1-M1", "Anna", "Hans", "Anna"), match("oq1-R1-M2", "Bas", "Cor", "Bas"),
  match("oq1-R1-M3", "Dirk", "Eva", "Eva"), match("oq1-R1-M4", "Fien", "Gijs", "Fien"),
  match("oq1-R2-M1", "Anna", "Bas", "Bas"), match("oq1-R2-M2", "Eva", "Fien", "Eva"),
  match("oq1-R3-M1", "Bas", "Eva", "Eva"),
];
const player = (name, discord, geo) => ({Player: name, "Discord User ID": discord, "GeoGuessr User ID": geo, "Tournament ID": "oq1"});
const oq1Players = [
  player("Eva", "111", "evaGeoId01"), player("Bas", "222", "basGeoId01"), player("Anna", "333", "annaGeoId1"),
  player("Fien", "444", "fienGeoId1"), player("Cor", "555", "corGeoId01"), player("Dirk", "666", "dirkGeoId1"),
];
const lcq = {"Tournament ID": "lcq", "Tournament Name": "Last Chance Qualifier", Event: "nk-2027", "Event Qualifies": 1, "Entry From": "oq1:5-8, 777, inviteGeoId"};

test("Entry From admits only the listed places and invitations", () => {
  const context = load({tournaments: [{"Tournament ID": "oq1", "Tournament Name": "OQ1", Event: "nk-2027", "Event Qualifies": 4}, lcq], players: oq1Players, matches: oq1Matches});
  // Places 5-8 of OQ1 are the first-round losers: Cor, Dirk, Gijs and Hans.
  assert.doesNotThrow(() => context.tournamentAssertEntryAllowed_(lcq, "555", ""));
  assert.doesNotThrow(() => context.tournamentAssertEntryAllowed_(lcq, "", "DIRKGEOID1"));
  assert.doesNotThrow(() => context.tournamentAssertEntryAllowed_(lcq, "777", ""));
  assert.doesNotThrow(() => context.tournamentAssertEntryAllowed_(lcq, "", "inviteGeoId"));
  assert.throws(() => context.tournamentAssertEntryAllowed_(lcq, "111", "evaGeoId01"), /Meedoen aan Last Chance Qualifier/);
  assert.throws(() => context.tournamentAssertEntryAllowed_(lcq, "999", "someoneElse"), /geplaatst hebt of uitgenodigd/);
  assert.doesNotThrow(() => context.tournamentAssertEntryAllowed_({"Tournament ID": "open"}, "999", ""));
});

test("only qualifiers block players who already have a place", () => {
  const tournaments = [
    {"Tournament ID": "oq1", "Tournament Name": "OQ1", Event: "nk-2027", "Event Qualifies": 4},
    {"Tournament ID": "groups", "Tournament Name": "Groepsfase", Event: "nk-2027", "Event Qualifies": 0},
  ];
  const context = load({tournaments: [...tournaments, lcq], players: oq1Players, matches: oq1Matches});
  assert.throws(() => context.tournamentAssertNotQualified_(lcq, "111", ""), /al geplaatst/);
  assert.doesNotThrow(() => context.tournamentAssertNotQualified_(tournaments[1], "111", "evaGeoId01"));
});

test("the Type column picks the format", () => {
  const context = load();
  assert.equal(context.tournamentBracketFormat_({Type: "Practice"}), "single-elimination");
  assert.equal(context.tournamentBracketFormat_({Type: "Double Elimination"}), "double-elimination");
  assert.equal(context.tournamentBracketFormat_({Type: "Round Robin"}), "round-robin");
  assert.equal(context.tournamentBracketFormat_(null), "single-elimination");
});
