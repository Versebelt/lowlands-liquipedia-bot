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
