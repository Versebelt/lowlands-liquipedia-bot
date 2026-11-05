const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "apps-script", "Tournament.gs"), "utf8");

function sheet(name, headers, rows) {
  const values = [headers, ...rows.map((row) => headers.map((header) => row[header] ?? ""))];
  return {
    values,
    getName: () => name,
    getLastRow: () => values.length,
    getLastColumn: () => headers.length,
    getRange: (row, col, numRows = 1, numCols = 1) => ({
      getValues: () => values.slice(row - 1, row - 1 + numRows).map((line) => line.slice(col - 1, col - 1 + numCols)),
      getDisplayValues: () => values.slice(row - 1, row - 1 + numRows).map((line) => line.slice(col - 1, col - 1 + numCols).map(String)),
      setValue: (value) => { values[row - 1][col - 1] = value; },
      setValues: (block) => block.forEach((line, i) => line.forEach((value, j) => { values[row - 1 + i][col - 1 + j] = value; })),
    }),
  };
}

// Two tournaments: a public cup and a hidden practice run, each with one player and one match.
function load() {
  const context = vm.createContext({console});
  vm.runInContext(source, context);
  const H = vm.runInContext("TOURNAMENT", context);
  const bracketId = "AbCdEfGhIj";
  const sheets = {
    [H.SHEETS.CONFIG]: sheet(H.SHEETS.CONFIG, H.HEADERS.CONFIG, [{Setting: "Active Tournament ID", Value: "oefen"}]),
    [H.SHEETS.TOURNAMENTS]: sheet(H.SHEETS.TOURNAMENTS, H.HEADERS.TOURNAMENTS, [
      {"Tournament ID": "cup", "Tournament Name": "Cup", Status: "Registration", "Liquipedia Bracket ID": bracketId},
      {"Tournament ID": "oefen", "Tournament Name": "Oefentoernooi", Status: "Live", Visibility: "Hidden", "Liquipedia Bracket ID": bracketId},
    ]),
    [H.SHEETS.PLAYERS]: sheet(H.SHEETS.PLAYERS, H.HEADERS.PLAYERS, [
      {Player: "Anna", Status: "Registered", "Tournament ID": "cup"},
      {Player: "Bas", Status: "Checked In", "Tournament ID": "oefen"},
    ]),
    [H.SHEETS.MATCHES]: sheet(H.SHEETS.MATCHES, H.HEADERS.MATCHES, [
      {"Match ID": "oefen-R1-M1", Round: "Final", "Player 1": "Bas", "Player 2": "Cor", Status: "Live", "Tournament ID": "oefen"},
    ]),
    [H.SHEETS.GAMES]: sheet(H.SHEETS.GAMES, H.HEADERS.GAMES, []),
    [H.SHEETS.LOG]: sheet(H.SHEETS.LOG, H.HEADERS.LOG, []),
  };
  context.SpreadsheetApp = {getActiveSpreadsheet: () => ({getSheetByName: (name) => sheets[name]})};
  context.tournamentAuthorize_ = () => {};
  context.tournamentJson_ = (value) => value;
  context.tournamentAvatarMap_ = () => ({});
  context.tournamentPlacements_ = () => [];
  return {context, sheets, H};
}

const get = (context, parameters) => context.doGet({parameter: {secret: "x", ...parameters}});

test("visibility: the website index leaves a Hidden tournament out", () => {
  const {context} = load();
  const index = get(context, {action: "public_index"});
  assert.equal(index.ok, true);
  assert.deepEqual(index.tournaments.map((t) => t.id), ["cup"]);
  assert.equal(index.tournaments[0].hidden, undefined);
});

test("visibility: a Hidden tournament answers like one that does not exist", () => {
  const {context} = load();
  const detail = get(context, {action: "public_tournament", tournament_id: "oefen"});
  assert.equal(detail.ok, false);
  assert.match(detail.error, /Tournament not found/);
  assert.equal(get(context, {action: "public_tournament", tournament_id: "cup"}).ok, true);
});

test("visibility: the broadcast app sees Hidden tournaments, marked hidden", () => {
  const {context} = load();
  const index = get(context, {action: "public_index", include_hidden: "1"});
  assert.deepEqual(index.tournaments.map((t) => [t.id, t.hidden === true]), [["cup", false], ["oefen", true]]);
  const detail = get(context, {action: "public_tournament", tournament_id: "oefen", include_hidden: "1"});
  assert.equal(detail.ok, true);
  assert.equal(detail.tournament.hidden, true);
  assert.equal(detail.tournament.matches[0].match_id, "oefen-R1-M1");
  const broadcast = get(context, {action: "broadcast_tournament", tournament_id: "oefen"});
  assert.equal(broadcast.ok, true);
});

test("visibility: empty or Public counts as public; only exactly Hidden hides", () => {
  const {context} = load();
  assert.equal(context.tournamentHidden_({Visibility: ""}), false);
  assert.equal(context.tournamentHidden_({Visibility: "Public"}), false);
  assert.equal(context.tournamentHidden_({Visibility: " hidden "}), true);
  assert.equal(context.tournamentHidden_({}), false);
});
