const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "apps-script", "Tournament.gs"), "utf8");

// Sheet stand-in that also supports writing (appendRow, setValue, setValues).
function sheet(name, headers, rows) {
  const values = [headers, ...rows.map((row) => headers.map((header) => row[header] ?? ""))];
  return {
    values,
    getName: () => name,
    getLastRow: () => values.length,
    getLastColumn: () => headers.length,
    appendRow: (row) => values.push([...row]),
    getRange: (row, col, numRows = 1, numCols = 1) => ({
      getValues: () => values.slice(row - 1, row - 1 + numRows).map((line) => line.slice(col - 1, col - 1 + numCols)),
      getDisplayValues: () => values.slice(row - 1, row - 1 + numRows).map((line) => line.slice(col - 1, col - 1 + numCols).map(String)),
      setValue: (value) => { values[row - 1][col - 1] = value; },
      setNumberFormat: () => {},
      setValues: (block) => block.forEach((line, i) => line.forEach((value, j) => { values[row - 1 + i][col - 1 + j] = value; })),
    }),
  };
}

function load() {
  const context = vm.createContext({console});
  vm.runInContext(source, context);
  const H = vm.runInContext("TOURNAMENT", context);
  const sheets = {
    [H.SHEETS.CONFIG]: sheet(H.SHEETS.CONFIG, H.HEADERS.CONFIG, [{Setting: "Active Tournament ID", Value: "cup"}]),
    [H.SHEETS.TOURNAMENTS]: sheet(H.SHEETS.TOURNAMENTS, H.HEADERS.TOURNAMENTS, [{"Tournament ID": "cup", "Tournament Name": "Cup"}]),
    [H.SHEETS.PLAYERS]: sheet(H.SHEETS.PLAYERS, H.HEADERS.PLAYERS, [
      {Player: "Anna", "GeoGuessr User ID": "https://www.geoguessr.com/user/annaGeoId01", "Tournament ID": "cup"},
      {Player: "Bas", "GeoGuessr User ID": "basGeoId01", "Tournament ID": "cup"},
      {Player: "Cor", "GeoGuessr User ID": "not valid!", "Tournament ID": "cup"},
      {Player: "Dirk", "GeoGuessr User ID": "dirkOther1", "Tournament ID": "other"},
    ]),
    [H.SHEETS.MATCHES]: sheet(H.SHEETS.MATCHES, H.HEADERS.MATCHES, [
      {"Match ID": "cup-R1-M1", "Player 1": "Anna", "Player 2": "Bas", Status: "Live", "Tournament ID": "cup"},
      {"Match ID": "cup-R1-M2", "Player 1": "Cor", "Player 2": "Eva", Status: "Complete", "Tournament ID": "cup"},
    ]),
    [H.SHEETS.GAMES]: sheet(H.SHEETS.GAMES, H.HEADERS.GAMES, []),
    [H.SHEETS.LOG]: sheet(H.SHEETS.LOG, H.HEADERS.LOG, []),
  };
  context.SpreadsheetApp = {getActiveSpreadsheet: () => ({getSheetByName: (name) => sheets[name]})};
  // No public spreadsheet to sync in these tests.
  context.tournamentActiveId_ = () => "cup";
  context.tournamentActive_ = () => ({"Tournament ID": "cup", "Public Spreadsheet ID": ""});
  return {context, sheets, H};
}

test("broadcast ids: GeoGuessr IDs of this tournament only, invalid ones skipped", () => {
  const {context} = load();
  assert.deepEqual({...context.tournamentBroadcastIds_("cup")}, {Anna: "annaGeoId01", Bas: "basGeoId01"});
});

test("game results are recorded once per game and replaced when sent again", () => {
  const {context, sheets, H} = load();
  const games = sheets[H.SHEETS.GAMES];
  const send = (extra) => context.tournamentHandleAction_({action: "game", match_id: "cup-R1-M1", game: 1, mode: "NM",
    winner: "Anna", player1_hp: 1850, player2_hp: 0, game_id: "abcdef12-3456", ...extra});
  send({});
  send({player1_hp: 1900});
  assert.equal(games.values.length, 2, "header plus one game row");
  const row = Object.fromEntries(H.HEADERS.GAMES.map((header, i) => [header, games.values[1][i]]));
  assert.equal(row["Player 1 Score"], 1900);
  assert.equal(row.Status, "Confirmed (broadcast)");
  assert.equal(row["Result URL"], "https://www.geoguessr.com/duels/abcdef12-3456/summary");
  assert.throws(() => send({winner: "Zed"}), /Winner must match/);
  assert.throws(() => send({game: 0}), /Game must be/);
});

test("live series score: only valid scores, never on a closed match", () => {
  const {context, sheets, H} = load();
  context.tournamentHandleAction_({action: "score", match_id: "cup-R1-M1", score: "1-0"});
  const matches = sheets[H.SHEETS.MATCHES];
  assert.equal(matches.values[1][H.HEADERS.MATCHES.indexOf("Series Score")], "1-0");
  assert.throws(() => context.tournamentHandleAction_({action: "score", match_id: "cup-R1-M1", score: "abc"}), /Score must/);
  assert.throws(() => context.tournamentHandleAction_({action: "score", match_id: "cup-R1-M2", score: "1-0"}), /already closed/);
});

test("a score that Sheets turned into a date still reads as the score", () => {
  const {context, sheets, H} = load();
  // vm context has its own Date; build the date inside it, like getValues() would return it.
  const date = vm.runInContext("new Date(2026, 0, 1)", context);
  sheets[H.SHEETS.MATCHES].values[1][H.HEADERS.MATCHES.indexOf("Series Score")] = date;
  context.SpreadsheetApp.getActiveSpreadsheet = () => ({getSheetByName: (name) => sheets[name], getSpreadsheetLocale: () => "nl_NL"});
  assert.equal(context.tournamentScoreText_(date), "1-1");
  context.tournamentHandleAction_({action: "score", match_id: "cup-R1-M1", score: "2-1", expected_score: "1-1"});
  assert.equal(sheets[H.SHEETS.MATCHES].values[1][H.HEADERS.MATCHES.indexOf("Series Score")], "2-1");
  context.SpreadsheetApp.getActiveSpreadsheet = () => ({getSheetByName: (name) => sheets[name], getSpreadsheetLocale: () => "en_US"});
  assert.equal(context.tournamentScoreText_(vm.runInContext("new Date(2026, 1, 1)", context)), "2-1");
});

test("expected_score: a stale or conflicting write is refused instead of overwriting", () => {
  const {context, sheets, H} = load();
  const score = () => sheets[H.SHEETS.MATCHES].values[1][H.HEADERS.MATCHES.indexOf("Series Score")];
  // Empty sheet value counts as 0-0.
  context.tournamentHandleAction_({action: "score", match_id: "cup-R1-M1", score: "1-0", expected_score: "0-0"});
  context.tournamentHandleAction_({action: "score", match_id: "cup-R1-M1", score: "2-0", expected_score: "1 - 0"});
  assert.equal(score(), "2-0");
  // An old retry (expects 0-0) may not set the score back.
  assert.throws(() => context.tournamentHandleAction_({action: "score", match_id: "cup-R1-M1", score: "1-0", expected_score: "0-0"}),
    /Conflict: Series Score in the sheet is 2-0, expected 0-0/);
  assert.equal(score(), "2-0");
  // Without expected_score (Discord, old app) it behaves as before.
  context.tournamentHandleAction_({action: "score", match_id: "cup-R1-M1", score: "2-1"});
  assert.equal(score(), "2-1");
  assert.throws(() => context.tournamentHandleAction_({action: "resolve", match_id: "cup-R1-M1", winner: "Anna", score: "3-1", expected_score: "2-0"}), /Conflict/);
});
