const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "apps-script", "Tournament.gs"), "utf8");
const context = vm.createContext({console});
vm.runInContext(source, context);

function checkWindow(tournament, now) {
  context.input = {tournament, now};
  return vm.runInContext(
    "tournamentCheckInWindow_(input.tournament, new Date(input.now))",
    context,
  );
}

const configured = {
  "Check-in Opens At": "2026-12-14T17:00:00Z",
  "Check-in Closes At": "2026-12-14T17:55:00Z",
  "Start At": "2026-12-14T18:00:00Z",
};

test("check-in is rejected before the opening time", () => {
  assert.equal(checkWindow(configured, "2026-12-14T16:59:59Z").state, "too_early");
});

test("check-in opens exactly on the opening boundary", () => {
  assert.equal(checkWindow(configured, "2026-12-14T17:00:00Z").state, "open");
});

test("check-in remains open inside the configured window", () => {
  assert.equal(checkWindow(configured, "2026-12-14T17:30:00Z").state, "open");
});

test("check-in closes exactly on the closing boundary", () => {
  assert.equal(checkWindow(configured, "2026-12-14T17:55:00Z").state, "closed");
});

test("blank window preserves legacy behaviour", () => {
  assert.equal(checkWindow({"Start At": "2026-12-14T18:00:00Z"}, "2026-11-01T00:00:00Z").state, "unconfigured");
});

test("start time is the fallback closing time", () => {
  const tournament = {
    "Check-in Opens At": "2026-12-14T17:00:00Z",
    "Check-in Closes At": "",
    "Start At": "2026-12-14T18:00:00Z",
  };
  assert.equal(checkWindow(tournament, "2026-12-14T18:00:00Z").state, "closed");
});

test("closing time must be after opening time", () => {
  assert.throws(
    () => checkWindow({
      "Check-in Opens At": "2026-12-14T17:00:00Z",
      "Check-in Closes At": "2026-12-14T17:00:00Z",
    }, "2026-12-14T17:00:00Z"),
    /sluitingstijd moet na de openingstijd liggen/,
  );
});

function automationDecision(tournament, now, hasMatches = false) {
  context.automationInput = {tournament, now, hasMatches};
  return vm.runInContext(
    "tournamentAutomationDecision_(automationInput.tournament, new Date(automationInput.now), automationInput.hasMatches)",
    context,
  );
}

test("bracket automation can be disabled per tournament", () => {
  assert.equal(automationDecision(configured, "2026-12-14T18:00:00Z").state, "disabled");
});

test("bracket automation waits until check-in closes", () => {
  const tournament = {...configured, "Auto-generate Official Bracket": true};
  assert.equal(automationDecision(tournament, "2026-12-14T17:54:59Z").state, "waiting");
  assert.equal(automationDecision(tournament, "2026-12-14T17:55:00Z").state, "generate");
});

test("bracket automation runs only once", () => {
  const tournament = {
    ...configured,
    "Auto-generate Official Bracket": true,
    "Official Bracket Generated At": "2026-12-14T17:56:00Z",
  };
  assert.equal(automationDecision(tournament, "2026-12-14T18:00:00Z").state, "generated");
});

test("bracket automation refuses to overwrite existing matches", () => {
  const tournament = {...configured, "Auto-generate Official Bracket": true};
  const decision = automationDecision(tournament, "2026-12-14T18:00:00Z", true);
  assert.equal(decision.state, "error");
  assert.match(decision.error, /automatisch overschrijven is geblokkeerd/);
});

test("checked-in seed gaps are compressed without changing relative order", () => {
  context.seedPlayers = [
    {Player: "Seed six", Seed: 6},
    {Player: "Seed one", Seed: 1},
    {Player: "Seed three", Seed: 3},
  ];
  const players = vm.runInContext("tournamentPrepareBracketPlayers_(seedPlayers, 'checked-in')", context);
  assert.deepEqual(
    Array.from(players, (player) => [player.Player, player.__bracketSeed]),
    [["Seed one", 1], ["Seed three", 2], ["Seed six", 3]],
  );
});
