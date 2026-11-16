const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "apps-script", "Tournament.gs"), "utf8");

// Sheet stand-in that counts how often its data rows are read (each read is a slow call in Apps Script).
function sheet(name, headers, rows, reads) {
  const values = [headers, ...rows.map((row) => headers.map((header) => row[header] ?? ""))];
  return {
    values,
    getName: () => name,
    getLastRow: () => values.length,
    getLastColumn: () => headers.length,
    getRange: (row, col, numRows = 1, numCols = 1) => ({
      getValues: () => {
        if (row >= 2) reads[name] = (reads[name] || 0) + 1;
        return values.slice(row - 1, row - 1 + numRows).map((line) => line.slice(col - 1, col - 1 + numCols));
      },
      getDisplayValues: () => values.slice(row - 1, row - 1 + numRows).map((line) => line.slice(col - 1, col - 1 + numCols).map(String)),
      setValue: (value) => { values[row - 1][col - 1] = value; },
      setValues: (block) => block.forEach((line, i) => line.forEach((value, j) => { values[row - 1 + i][col - 1 + j] = value; })),
    }),
  };
}

// Five tournaments with two players and a final each.
function load() {
  const context = vm.createContext({console});
  vm.runInContext(source, context);
  const H = vm.runInContext("TOURNAMENT", context);
  const reads = {};
  const ids = ["t1", "t2", "t3", "t4", "t5"];
  const sheets = {
    [H.SHEETS.CONFIG]: sheet(H.SHEETS.CONFIG, H.HEADERS.CONFIG, [{Setting: "Active Tournament ID", Value: "t1"}], reads),
    [H.SHEETS.TOURNAMENTS]: sheet(H.SHEETS.TOURNAMENTS, H.HEADERS.TOURNAMENTS,
      ids.map((id) => ({"Tournament ID": id, "Tournament Name": id, Status: "Live", "Liquipedia Bracket ID": "AbCdEfGhIj"})), reads),
    [H.SHEETS.PLAYERS]: sheet(H.SHEETS.PLAYERS, H.HEADERS.PLAYERS, ids.flatMap((id) => [
      {Player: id + "-a", Status: "Checked In", "GeoGuessr User ID": id + "aaaaaaa", "Tournament ID": id},
      {Player: id + "-b", Status: "Checked In", "GeoGuessr User ID": id + "bbbbbbb", "Tournament ID": id},
    ]), reads),
    [H.SHEETS.MATCHES]: sheet(H.SHEETS.MATCHES, H.HEADERS.MATCHES, ids.map((id) => (
      {"Match ID": id + "-R1-M1", Round: "Final", "Player 1": id + "-a", "Player 2": id + "-b", Winner: id + "-a", "Series Score": new Date(2026, 0, 2), "Tournament ID": id}
    )), reads),
    [H.SHEETS.GAMES]: sheet(H.SHEETS.GAMES, H.HEADERS.GAMES, [], reads),
    [H.SHEETS.LOG]: sheet(H.SHEETS.LOG, H.HEADERS.LOG, [], reads),
  };
  let localeCalls = 0;
  context.SpreadsheetApp = {getActiveSpreadsheet: () => ({
    getSheetByName: (name) => sheets[name],
    getSpreadsheetLocale: () => { localeCalls++; return "nl_NL"; },
  })};
  context.tournamentAuthorize_ = () => {};
  context.tournamentJson_ = (value) => value;
  context.tournamentAvatarMap_ = () => ({});
  const reset = () => { for (const key of Object.keys(reads)) delete reads[key]; localeCalls = 0; };
  return {context, H, reads, reset, locale: () => localeCalls};
}

const get = (context, parameters) => context.doGet({parameter: {secret: "x", ...parameters}});
const plain = (value) => JSON.parse(JSON.stringify(value));

test("read speed: the index reads each sheet once, whatever the number of tournaments", () => {
  const {context, H, reads, reset} = load();
  const before = plain(context.tournamentWebsiteIndex_(true));
  assert.ok(reads[H.SHEETS.PLAYERS] >= 5, "without the memo every tournament re-reads Players");
  reset();
  const index = get(context, {action: "public_index", include_hidden: "1"});
  assert.equal(index.ok, true);
  assert.deepEqual(plain(index.tournaments), before, "same answer as before");
  assert.equal(index.tournaments[0].winner, "t1-a");
  for (const name of [H.SHEETS.TOURNAMENTS, H.SHEETS.PLAYERS, H.SHEETS.MATCHES]) assert.equal(reads[name], 1, name);
});

test("read speed: detail and broadcast read each sheet once, and the locale once", () => {
  const {context, H, reads, reset, locale} = load();
  const before = plain(context.tournamentWebsiteDetail_("t2", true));
  reset();
  const detail = get(context, {action: "broadcast_tournament", tournament_id: "t2"});
  assert.equal(detail.ok, true);
  assert.deepEqual(plain(detail.tournament), before, "same answer as before");
  assert.equal(detail.tournament.matches[0].series_score, "2-1", "a score read back as a date still turns into 2-1");
  assert.deepEqual(plain(detail.geoguessr_ids), {"t2-a": "t2aaaaaaa", "t2-b": "t2bbbbbbb"});
  for (const name of [H.SHEETS.TOURNAMENTS, H.SHEETS.PLAYERS, H.SHEETS.MATCHES]) assert.equal(reads[name], 1, name);
  assert.equal(locale(), 1);
});

test("read speed: the memo ends with the request, so later edits are seen", () => {
  const {context, H} = load();
  assert.equal(get(context, {action: "public_tournament", tournament_id: "t3", include_hidden: "1"}).tournament.participant_count, 2);
  const players = context.SpreadsheetApp.getActiveSpreadsheet().getSheetByName(H.SHEETS.PLAYERS);
  players.values.push(H.HEADERS.PLAYERS.map((header) => ({Player: "t3-c", Status: "Checked In", "Tournament ID": "t3"})[header] ?? ""));
  assert.equal(get(context, {action: "public_tournament", tournament_id: "t3", include_hidden: "1"}).tournament.participant_count, 3);
  assert.equal(vm.runInContext("TOURNAMENT_READ_MEMO_", context), null);
});

test("generated match rows fill every Matches column, Expected At included", () => {
  const {context, H} = load();
  const row = context.tournamentMatchRow_({id: "t1-R1-M1", round: "Final", order: 1, player1: "a", player2: "b", presets: [], tournamentId: "t1"});
  assert.equal(row.length, H.HEADERS.MATCHES.length);
  assert.equal(row[H.HEADERS.MATCHES.indexOf("Expected At")], "");
});
