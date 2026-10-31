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
      return {getValues: () => block, getDisplayValues: () => block.map((line) => line.map(String))};
    },
  };
}

function load(tournaments, players, matches) {
  const context = vm.createContext({console});
  vm.runInContext(source, context);
  const H = vm.runInContext("TOURNAMENT", context);
  const sheets = {
    [H.SHEETS.TOURNAMENTS]: sheet(H.SHEETS.TOURNAMENTS, H.HEADERS.TOURNAMENTS, tournaments),
    [H.SHEETS.PLAYERS]: sheet(H.SHEETS.PLAYERS, H.HEADERS.PLAYERS, players),
    [H.SHEETS.MATCHES]: sheet(H.SHEETS.MATCHES, H.HEADERS.MATCHES, matches),
  };
  context.SpreadsheetApp = {getActiveSpreadsheet: () => ({getSheetByName: (name) => sheets[name]})};
  return context;
}

const match = (id, p1, p2, winner) => ({"Match ID": id, "Player 1": p1, "Player 2": p2, Winner: winner, "Tournament ID": id.split("-R")[0]});
const oq1Matches = [
  match("oq1-R1-M1", "Anna", "BYE", "Anna"), match("oq1-R1-M2", "Bas", "Cor", "Bas"),
  match("oq1-R1-M3", "Dirk", "Eva", "Eva"), match("oq1-R1-M4", "Fien", "Gijs", "Fien"),
  match("oq1-R2-M1", "Anna", "Bas", "Bas"), match("oq1-R2-M2", "Eva", "Fien", "Eva"),
  match("oq1-R3-M1", "Bas", "Eva", "Eva"),
];
const player = (name, discord, geo, tournament) => ({Player: name, "Discord User ID": discord, "GeoGuessr User ID": geo, "Tournament ID": tournament});
const tournaments = [
  {"Tournament ID": "oq1", "Tournament Name": "Open Qualifier 1", Event: "NK-2027", "Event Phase": "oq1", "Event Qualifies": 4},
  {"Tournament ID": "oq2", "Tournament Name": "Open Qualifier 2", Event: "nk-2027", "Event Phase": "oq2", "Event Qualifies": 4},
  {"Tournament ID": "cup", "Tournament Name": "Losse cup", Event: "", "Event Qualifies": 0},
];
const players = [
  player("Eva", "111", "evaGeoId01", "oq1"), player("Bas", "222", "basGeoId01", "oq1"),
  player("Anna", "333", "annaGeoId1", "oq1"), player("Fien", "444", "fienGeoId1", "oq1"),
  player("Cor", "555", "corGeoId01", "oq1"),
];

test("placements follow the bracket and skip BYE", () => {
  const context = load(tournaments, players, oq1Matches);
  assert.deepEqual(Array.from(context.tournamentPlacements_("oq1")), ["Eva", "Bas", "Anna", "Fien", "Cor", "Dirk", "Gijs"]);
});

test("an unfinished bracket has no placements", () => {
  const unplayedFinal = [...oq1Matches.slice(0, 6), match("oq1-R3-M1", "Bas", "Eva", "")];
  assert.deepEqual(Array.from(load(tournaments, players, unplayedFinal).tournamentPlacements_("oq1")), []);
  // Without a single final match the bracket is incomplete, not finished.
  assert.deepEqual(Array.from(load(tournaments, players, oq1Matches.slice(0, 6)).tournamentPlacements_("oq1")), []);
});

test("qualified players cannot register for another qualifier of the same event", () => {
  const context = load(tournaments, players, oq1Matches);
  const oq2 = tournaments[1];
  assert.throws(() => context.tournamentAssertNotQualified_(oq2, "111", ""), /al geplaatst via Open Qualifier 1/);
  assert.throws(() => context.tournamentAssertNotQualified_(oq2, "999", "FIENGEOID1"), /al geplaatst/);
  assert.doesNotThrow(() => context.tournamentAssertNotQualified_(oq2, "555", "corGeoId01"));
});

test("other events and the qualifying tournament itself are not blocked", () => {
  const context = load(tournaments, players, oq1Matches);
  assert.doesNotThrow(() => context.tournamentAssertNotQualified_(tournaments[2], "111", "evaGeoId01"));
  assert.doesNotThrow(() => context.tournamentAssertNotQualified_(tournaments[0], "111", "evaGeoId01"));
});
