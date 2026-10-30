/**
 * GeoNederland Tournament Control
 * Install ONLY in the dedicated Tournament Admin spreadsheet.
 * The Lowlands League Season 2 spreadsheets are not used by this project.
 */

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("Tournament Control")
    .addItem("Set up / repair Admin sheet", "setupTournamentSystem")
    .addSeparator()
    .addItem("Create new tournament", "createTournament")
    .addItem("Switch active tournament", "switchActiveTournament")
    .addItem("Archive active tournament", "archiveActiveTournament")
    .addSeparator()
    .addItem("Randomize player seeding", "randomizeTournamentSeeding")
    .addItem("Validate player seeding", "validateTournamentSeeding")
    .addItem("Generate bracket", "generateTournamentBracket")
    .addItem("Sync Public bracket", "syncTournamentPublicSpreadsheet")
    .addSeparator()
    .addItem("Set Discord API secret", "setTournamentApiSecret")
    .addToUi();
}

/* ========================================================================== */
/* Tournament control — Google Sheets is the source of truth; Discord writes  */
/* through the authenticated web-app endpoints below.                         */
/* ========================================================================== */

const TOURNAMENT = {
  SHEETS: {
    CONFIG: "Tournament",
    TOURNAMENTS: "Tournaments",
    PLAYERS: "Tournament Players",
    MATCHES: "Tournament Matches",
    GAMES: "Tournament Games",
    LOG: "Tournament Log",
  },
  HEADERS: {
    CONFIG: ["Setting", "Value", "Notes"],
    TOURNAMENTS: [
      "Tournament ID", "Tournament Name", "Type", "Status", "Maximum Players", "Bracket Size",
      "Default Best Of", "Preset 1", "Preset 2", "Preset 3", "Public Spreadsheet ID",
      "Public Bracket URL", "Stream URL", "Created At", "Archived At", "Rules URL",
      "Registration URL", "Start At", "End At", "Liquipedia Bracket ID",
    ],
    PLAYERS: [
      "Seed", "Player", "GeoGuessr User ID", "Discord", "Discord User ID", "Country",
      "Status", "Checked In", "Registered At", "Checked In At", "Updated At", "Notes", "Tournament ID",
    ],
    MATCHES: [
      "Match ID", "Round", "Bracket Order", "Player 1", "Player 2",
      "Best Of", "Preset 1", "Preset 2", "Preset 3", "Highlighted",
      "Player 1 Ready", "Player 2 Ready", "Admin Released", "Status",
      "Party URL", "Series Score", "Winner", "Next Match ID", "Next Slot",
      "Scheduled At", "Stream URL", "Discord Message ID", "Updated At", "Tournament ID",
    ],
    GAMES: [
      "Submitted At", "Match ID", "Game", "Mode", "Result URL", "Submitted By",
      "Player 1 Score", "Player 2 Score", "Winner", "Status", "Notes", "Tournament ID",
    ],
    LOG: ["Timestamp", "Actor", "Action", "Match ID", "Details", "Tournament ID"],
  },
};

function setupTournamentSystem() {
  const ss = SpreadsheetApp.getActiveSpreadsheet(), s = TOURNAMENT.SHEETS;
  tournamentInitSheet_(ss, s.CONFIG, TOURNAMENT.HEADERS.CONFIG);
  tournamentInitSheet_(ss, s.TOURNAMENTS, TOURNAMENT.HEADERS.TOURNAMENTS);
  tournamentInitSheet_(ss, s.PLAYERS, TOURNAMENT.HEADERS.PLAYERS);
  tournamentInitSheet_(ss, s.MATCHES, TOURNAMENT.HEADERS.MATCHES);
  tournamentInitSheet_(ss, s.GAMES, TOURNAMENT.HEADERS.GAMES);
  tournamentInitSheet_(ss, s.LOG, TOURNAMENT.HEADERS.LOG);

  const config = ss.getSheetByName(s.CONFIG);
  if (config.getLastRow() < 2) {
    config.getRange(2, 1, 14, 3).setValues([
      ["Active Tournament ID", "practice-1", "Selects which tournament Discord and the menu operate on"],
      ["Tournament Name", "GeoNederland Practice Tournament", "Shown in Discord"],
      ["Tournament Status", "Setup", "Setup / Check-in / Live / Complete"],
      ["Registration Status", "Open", "Open / Closed"],
      ["Registration Deadline", "", "Optional deadline shown in Discord"],
      ["Maximum Players", 32, "New registrations stop at this number"],
      ["Bracket Type", "Single Elimination", "Practice MVP"],
      ["Default Best Of", 3, "Must be an odd number"],
      ["Preset 1", "", "Usually Moving"],
      ["Preset 2", "", "Usually No Move"],
      ["Preset 3", "", "Usually NMPZ"],
      ["Public Spreadsheet ID", "", "ID of the separate read-only public bracket Sheet"],
      ["Public Bracket URL", "", "Filled automatically during public setup"],
      ["Stream URL", "", "Optional Twitch or YouTube link"],
    ]);
  }

  tournamentValidation_(ss);
  tournamentFormat_(ss);
  tournamentLog_("sheet", "setup", "", "Tournament system created or repaired");
  SpreadsheetApp.flush();
  tournamentEnsureConfig_("Registration Status", "Open", "Open / Closed");
  tournamentEnsureConfig_("Registration Deadline", "", "Optional deadline shown in Discord");
  tournamentEnsureConfig_("Maximum Players", 32, "New registrations stop at this number");
  tournamentEnsureConfig_("Rules URL", "", "Public link to the current tournament regulations");
  tournamentEnsureConfig_("Active Tournament ID", "practice-1", "Selects which tournament Discord and the menu operate on");
  tournamentEnsureInitialTournament_();
  tournamentEnsureLiquipediaBracketIds_();
  tournamentCleanGhostTournamentIds_();
  tournamentMigrateLegacyTournamentIds_();
  ss.toast("Tournament system ready.", "GeoNederland Tournament", 6);
}

function setupTournamentPublicSpreadsheet() {
  setupTournamentSystem();
  const tournament = tournamentActive_(), id = tournamentSpreadsheetId_(tournament["Public Spreadsheet ID"]);
  if (!id) throw Error("The active tournament does not have a Public Spreadsheet ID.");
  if (id === SpreadsheetApp.getActiveSpreadsheet().getId()) throw Error("Admin and Public must be separate spreadsheets.");
  const publicSs = SpreadsheetApp.openById(id), bracket = publicSs.getSheetByName("Bracket") || publicSs.insertSheet("Bracket"), schedule = publicSs.getSheetByName("Schedule") || publicSs.insertSheet("Schedule");
  bracket.setHiddenGridlines(true); schedule.setHiddenGridlines(true);
  tournamentUpdateActive_({"Public Bracket URL": "https://docs.google.com/spreadsheets/d/" + id + "/edit"});
  syncTournamentPublicSpreadsheet();
  SpreadsheetApp.getActiveSpreadsheet().toast("Public bracket ready.", "GeoNederland Tournament", 6);
}

function syncTournamentPublicSpreadsheet() {
  const config = tournamentConfig_(), tournament = tournamentActive_(), id = tournamentSpreadsheetId_(tournament["Public Spreadsheet ID"]);
  if (!id) throw Error("The active tournament does not have a Public Spreadsheet ID.");
  const publicSs = SpreadsheetApp.openById(id), bracket = publicSs.getSheetByName("Bracket") || publicSs.insertSheet("Bracket"), schedule = publicSs.getSheetByName("Schedule") || publicSs.insertSheet("Schedule"), matches = tournamentPublicMatches_();
  const view = Object.assign({}, config, tournament);
  tournamentRenderPublicBracket_(bracket, view, matches);
  tournamentRenderPublicSchedule_(schedule, view, matches);
  SpreadsheetApp.flush();
}

function createTournament() {
  setupTournamentSystem();
  const ui = SpreadsheetApp.getUi();
  const namePrompt = ui.prompt("Create tournament", "Tournament name, for example NK 2027 Open Qualifier 1", ui.ButtonSet.OK_CANCEL);
  if (namePrompt.getSelectedButton() !== ui.Button.OK) return;
  const name = String(namePrompt.getResponseText() || "").trim();
  if (name.length < 3) throw Error("Enter a tournament name of at least 3 characters.");
  const idPrompt = ui.prompt("Tournament ID", "Short unique ID, for example nk27-oq1", ui.ButtonSet.OK_CANCEL);
  if (idPrompt.getSelectedButton() !== ui.Button.OK) return;
  const id = String(idPrompt.getResponseText() || "").trim().toLowerCase().replace(/[^a-z0-9-]+/g, "-").replace(/^-|-$/g, "");
  if (!id) throw Error("Enter a valid Tournament ID.");
  if (tournamentById_(id)) throw Error("Tournament ID already exists: " + id);
  const maxPrompt = ui.prompt("Maximum players", "Choose 8, 16, 32 or 64.", ui.ButtonSet.OK_CANCEL);
  if (maxPrompt.getSelectedButton() !== ui.Button.OK) return;
  const maximum = Number(maxPrompt.getResponseText());
  if (![8, 16, 32, 64].includes(maximum)) throw Error("Maximum players must be 8, 16, 32 or 64.");
  const publicSs = SpreadsheetApp.create(name + " - Public Bracket");
  const first = publicSs.getSheets()[0]; first.setName("Bracket"); publicSs.insertSheet("Schedule");
  const row = [id, name, "Single Elimination", "Registration", maximum, "", 3, "", "", "",
    publicSs.getId(), publicSs.getUrl(), "", new Date(), "", "", "", "", "", tournamentNewLiquipediaBracketId_()];
  SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TOURNAMENT.SHEETS.TOURNAMENTS).appendRow(row);
  tournamentSetConfig_("Active Tournament ID", id);
  tournamentSetConfig_("Tournament Name", name);
  tournamentSetConfig_("Tournament Status", "Registration");
  tournamentSetConfig_("Registration Status", "Open");
  tournamentSetConfig_("Maximum Players", maximum);
  syncTournamentPublicSpreadsheet();
  tournamentLog_("sheet", "create_tournament", "", name + " · " + publicSs.getUrl());
  ui.alert("Tournament created", name + " is now active.\n\nPublic bracket:\n" + publicSs.getUrl(), ui.ButtonSet.OK);
}

function switchActiveTournament() {
  setupTournamentSystem();
  const ui = SpreadsheetApp.getUi(), tournaments = tournamentRows_(SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TOURNAMENT.SHEETS.TOURNAMENTS));
  const list = tournaments.map((row) => row["Tournament ID"] + " — " + row["Tournament Name"] + " (" + row.Status + ")").join("\n");
  const prompt = ui.prompt("Switch active tournament", list + "\n\nEnter Tournament ID:", ui.ButtonSet.OK_CANCEL);
  if (prompt.getSelectedButton() !== ui.Button.OK) return;
  const id = String(prompt.getResponseText() || "").trim();
  const tournament = tournamentById_(id);
  if (!tournament) throw Error("Unknown Tournament ID: " + id);
  tournamentSetConfig_("Active Tournament ID", id);
  tournamentSetConfig_("Tournament Name", tournament["Tournament Name"]);
  tournamentSetConfig_("Tournament Status", tournament.Status);
  tournamentSetConfig_("Maximum Players", tournament["Maximum Players"]);
  tournamentSetConfig_("Rules URL", tournament["Rules URL"] || "");
  SpreadsheetApp.getActiveSpreadsheet().toast(tournament["Tournament Name"] + " is now active.", "GeoNederland Tournament", 6);
}

function archiveActiveTournament() {
  const tournament = tournamentActive_(), ui = SpreadsheetApp.getUi();
  const answer = ui.alert("Archive tournament?", "Archive " + tournament["Tournament Name"] + "? All rows and public output remain available.", ui.ButtonSet.YES_NO);
  if (answer !== ui.Button.YES) return;
  tournamentUpdateActive_({Status: "Archived", "Archived At": new Date()});
  tournamentSetConfig_("Tournament Status", "Archived");
  tournamentSetConfig_("Registration Status", "Closed");
  syncTournamentPublicSpreadsheet();
  tournamentLog_("sheet", "archive_tournament", "", tournament["Tournament Name"]);
}

function tournamentRenderPublicBracket_(sheet, config, matches) {
  const sorted = matches
    .filter((match) => String(match.match_id || "").trim() || String(match.round || "").trim())
    .slice()
    .sort((a, b) => a.order - b.order);
  if (!sorted.length) {
    [["Round of 32", 16], ["Round of 16", 8], ["Quarterfinal", 4], ["Semifinal", 2], ["Final", 1]].forEach(([round, count]) => {
      for (let index = 0; index < count; index++) sorted.push({
        round, order: sorted.length + 1, match_id: "TBD", player1: "TBD", player2: "TBD",
        series_score: "0-0", status: "Waiting for players", highlighted: false, winner: "",
      });
    });
  }
  const roundNames = [];
  sorted.forEach((match) => { if (!roundNames.includes(match.round)) roundNames.push(match.round); });
  const rounds = roundNames.map((name) => sorted.filter((match) => match.round === name));
  // Up to eight players reads best from left to right. From sixteen players
  // onwards, split the bracket into two halves that converge on a centre final.
  if (rounds.length > 1 && rounds[0].length > 4) {
    tournamentRenderMirroredBracket_(sheet, config, rounds, roundNames);
    return;
  }
  const finalMatch = rounds.length ? rounds[rounds.length - 1][0] : null;
  rounds.push([{
    round: "Champion", match_id: "", player1: finalMatch && finalMatch.winner || "TBD",
    player2: "", series_score: "", status: finalMatch && finalMatch.status === "Complete" ? "Tournament winner" : "To be decided",
    highlighted: false, winner: finalMatch && finalMatch.winner || "",
  }]);

  const firstRoundCount = Math.max(1, rounds[0].length), totalColumns = Math.max(3, rounds.length * 4 - 1);
  const totalRows = Math.max(16, 8 + firstRoundCount * 8);
  sheet.getRange(1, 1, sheet.getMaxRows(), sheet.getMaxColumns()).breakApart();
  sheet.clear(); sheet.setHiddenGridlines(true); sheet.setFrozenRows(3);
  sheet.getRange(1, 1, totalRows, totalColumns).setBackground("#f3f0e9").setFontFamily("Arial").setFontColor("#102335");
  sheet.getRange(1, 1, 1, totalColumns).merge().setValue(String(config["Tournament Name"] || "GeoNederland Tournament"))
    .setBackground("#00182f").setFontColor("#ffffff").setFontSize(20).setFontWeight("bold").setHorizontalAlignment("left");
  sheet.getRange(2, 1, 1, totalColumns).merge().setValue("OFFICIAL BRACKET  ·  " + String(config["Tournament Status"] || "Setup").toUpperCase())
    .setBackground("#01397a").setFontColor("#ffffff").setFontWeight("bold").setHorizontalAlignment("left");
  tournamentDrawRulesLink_(sheet, totalColumns, config);

  let centers = rounds[0].map((_, index) => 7 + index * 8);
  rounds.forEach((roundMatches, roundIndex) => {
    const startColumn = 1 + roundIndex * 4;
    const title = roundNames[roundIndex] || "Champion";
    sheet.getRange(4, startColumn, 1, 3).merge().setValue(String(title).toUpperCase())
      .setBackground(roundIndex === rounds.length - 1 ? "#f47806" : "#00182f")
      .setFontColor("#ffffff").setFontWeight("bold").setHorizontalAlignment("center");
    [180, 70, 70].forEach((width, offset) => sheet.setColumnWidth(startColumn + offset, width));
    if (roundIndex < rounds.length - 1) sheet.setColumnWidth(startColumn + 3, 34);

    roundMatches.forEach((match, matchIndex) => {
      const center = centers[matchIndex], top = center - 1;
      tournamentDrawBracketMatch_(sheet, startColumn, top, match, roundIndex === rounds.length - 1, roundIndex < rounds.length - 1 ? "right" : "");
    });

    if (roundIndex < rounds.length - 1) {
      const nextCenters = [];
      for (let index = 0; index < centers.length; index += 2) {
        const upper = centers[index], lower = centers[index + 1] === undefined ? upper : centers[index + 1];
        const parent = Math.round((upper + lower) / 2);
        nextCenters.push(parent);
        const connector = sheet.getRange(Math.min(upper, lower), startColumn + 3, Math.max(1, Math.abs(lower - upper)), 1);
        connector.setBorder(null, null, null, true, null, null, "#01397a", SpreadsheetApp.BorderStyle.SOLID_MEDIUM);
        sheet.getRange(upper, startColumn + 3).setBorder(true, null, null, null, null, null, "#01397a", SpreadsheetApp.BorderStyle.SOLID_MEDIUM);
        sheet.getRange(lower, startColumn + 3).setBorder(true, null, null, null, null, null, "#01397a", SpreadsheetApp.BorderStyle.SOLID_MEDIUM);
      }
      centers = nextCenters;
    }
  });

  sheet.setRowHeight(1, 42); sheet.setRowHeight(2, 28); sheet.setRowHeight(4, 28);
  sheet.setConditionalFormatRules([]);
}

function tournamentRenderMirroredBracket_(sheet, config, rounds, roundNames) {
  const sideRounds = rounds.length - 1, groupWidth = 4, centerColumn = sideRounds * groupWidth + 1;
  const totalColumns = centerColumn * 2 + 1, firstSideCount = Math.max(1, Math.ceil(rounds[0].length / 2));
  const totalRows = Math.max(24, 10 + firstSideCount * 8);
  if (sheet.getMaxColumns() < totalColumns) sheet.insertColumnsAfter(sheet.getMaxColumns(), totalColumns - sheet.getMaxColumns());
  if (sheet.getMaxRows() < totalRows) sheet.insertRowsAfter(sheet.getMaxRows(), totalRows - sheet.getMaxRows());
  sheet.getRange(1, 1, sheet.getMaxRows(), sheet.getMaxColumns()).breakApart();
  sheet.clear(); sheet.setHiddenGridlines(true); sheet.setFrozenRows(3);
  sheet.getRange(1, 1, totalRows, totalColumns).setBackground("#f3f0e9").setFontFamily("Arial").setFontColor("#102335");
  sheet.getRange(1, 1, 1, totalColumns).merge().setValue(String(config["Tournament Name"] || "GeoNederland Tournament"))
    .setBackground("#00182f").setFontColor("#ffffff").setFontSize(20).setFontWeight("bold").setHorizontalAlignment("left");
  sheet.getRange(2, 1, 1, totalColumns).merge().setValue("OFFICIAL BRACKET  ·  " + String(config.Status || config["Tournament Status"] || "Setup").toUpperCase())
    .setBackground("#01397a").setFontColor("#ffffff").setFontWeight("bold").setHorizontalAlignment("left");
  tournamentDrawRulesLink_(sheet, totalColumns, config);

  const leftRounds = rounds.slice(0, -1).map((matches) => matches.slice(0, Math.ceil(matches.length / 2)));
  const rightRounds = rounds.slice(0, -1).map((matches) => matches.slice(Math.ceil(matches.length / 2)));
  tournamentDrawBracketSide_(sheet, leftRounds, roundNames, false, centerColumn);
  tournamentDrawBracketSide_(sheet, rightRounds, roundNames, true, centerColumn);

  const firstCenters = Array.from({length: firstSideCount}, (_, index) => 7 + index * 8);
  let reducedCenters = firstCenters.slice();
  while (reducedCenters.length > 1) {
    const next = [];
    for (let index = 0; index < reducedCenters.length; index += 2) next.push(Math.round((reducedCenters[index] + (reducedCenters[index + 1] === undefined ? reducedCenters[index] : reducedCenters[index + 1])) / 2));
    reducedCenters = next;
  }
  const finalCenter = reducedCenters[0];
  const finalMatch = rounds[rounds.length - 1][0] || {round: "Final", player1: "TBD", player2: "TBD", status: "Waiting for players"};
  sheet.getRange(4, centerColumn, 1, 3).merge().setValue("FINAL").setBackground("#f47806").setFontColor("#ffffff").setFontWeight("bold").setHorizontalAlignment("center");
  tournamentDrawBracketMatch_(sheet, centerColumn, finalCenter - 1, finalMatch, false, "both");
  sheet.getRange(finalCenter, centerColumn - 1)
    .setBorder(true, null, null, null, null, null, "#01397a", SpreadsheetApp.BorderStyle.SOLID_MEDIUM);
  sheet.getRange(finalCenter, centerColumn + 3)
    .setBorder(true, null, null, null, null, null, "#01397a", SpreadsheetApp.BorderStyle.SOLID_MEDIUM);
  const champion = {round: "Champion", match_id: "", player1: finalMatch.winner || "TBD", player2: "", status: finalMatch.status === "Complete" ? "Tournament winner" : "To be decided", winner: finalMatch.winner || ""};
  tournamentDrawBracketMatch_(sheet, centerColumn, finalCenter + 5, champion, true);
  sheet.getRange(finalCenter + 3, centerColumn + 1, 3, 1).setBorder(null, true, null, null, null, null, "#f47806", SpreadsheetApp.BorderStyle.SOLID_MEDIUM);
  [180, 70, 70].forEach((width, offset) => sheet.setColumnWidth(centerColumn + offset, width));
  sheet.setRowHeight(1, 42); sheet.setRowHeight(2, 28); sheet.setRowHeight(4, 28);
  sheet.setConditionalFormatRules([]);
}

function tournamentDrawBracketSide_(sheet, sideRounds, roundNames, mirrored, centerColumn) {
  let centers = sideRounds[0].map((_, index) => 7 + index * 8);
  sideRounds.forEach((matches, roundIndex) => {
    const startColumn = mirrored ? centerColumn + 4 + (sideRounds.length - 1 - roundIndex) * 4 : 1 + roundIndex * 4;
    sheet.getRange(4, startColumn, 1, 3).merge().setValue(String(roundNames[roundIndex] || "Round").toUpperCase())
      .setBackground("#00182f").setFontColor("#ffffff").setFontWeight("bold").setHorizontalAlignment("center");
    [180, 70, 70].forEach((width, offset) => sheet.setColumnWidth(startColumn + offset, width));
    const connectorColumn = mirrored ? startColumn - 1 : startColumn + 3;
    sheet.setColumnWidth(connectorColumn, 34);
    matches.forEach((match, matchIndex) => tournamentDrawBracketMatch_(sheet, startColumn, centers[matchIndex] - 1, match, false, mirrored ? "left" : "right"));
    if (roundIndex === sideRounds.length - 1) return;
    const nextCenters = [];
    for (let index = 0; index < centers.length; index += 2) {
      const upper = centers[index], lower = centers[index + 1] === undefined ? upper : centers[index + 1], parent = Math.round((upper + lower) / 2);
      nextCenters.push(parent);
      sheet.getRange(Math.min(upper, lower), connectorColumn, Math.max(1, Math.abs(lower - upper)), 1)
        .setBorder(null, mirrored, null, !mirrored, null, null, "#01397a", SpreadsheetApp.BorderStyle.SOLID_MEDIUM);
      [upper, lower].forEach((row) => sheet.getRange(row, connectorColumn).setBorder(true, null, null, null, null, null, "#01397a", SpreadsheetApp.BorderStyle.SOLID_MEDIUM));
    }
    centers = nextCenters;
  });
}

function tournamentDrawBracketMatch_(sheet, startColumn, topRow, match, champion, openSide) {
  const navy = "#00182f", blue = "#01397a", orange = "#f47806", paper = "#fffefb", green = "#35c27c";
  const scores = String(match.series_score || "").match(/(\d+)\s*[-–]\s*(\d+)/);
  const playerOneScore = scores ? scores[1] : "", playerTwoScore = scores ? scores[2] : "";
  const header = champion ? "CHAMPION" : String(match.match_id || match.round || "MATCH");
  sheet.getRange(topRow, startColumn, 1, 3).merge().setValue(header)
    .setBackground(champion ? orange : blue).setFontColor("#ffffff").setFontWeight("bold").setHorizontalAlignment("left");
  const playerOne = sheet.getRange(topRow + 1, startColumn, 1, 2).merge().setValue(String(match.player1 || "TBD"));
  const playerOneScoreCell = sheet.getRange(topRow + 1, startColumn + 2).setValue(playerOneScore);
  const playerTwo = sheet.getRange(topRow + 2, startColumn, 1, 2).merge().setValue(String(match.player2 || ""));
  const playerTwoScoreCell = sheet.getRange(topRow + 2, startColumn + 2).setValue(playerTwoScore);
  sheet.getRange(topRow + 1, startColumn, 2, 3).setBackground(paper).setFontWeight("bold")
    .setBorder(true, true, true, true, true, true, navy, SpreadsheetApp.BorderStyle.SOLID);
  if (openSide === "right" || openSide === "both") {
    sheet.getRange(topRow + 1, startColumn + 2, 2, 1)
      .setBorder(null, null, null, false, null, null);
  }
  if (openSide === "left" || openSide === "both") {
    sheet.getRange(topRow + 1, startColumn, 2, 1)
      .setBorder(null, false, null, null, null, null);
  }
  playerOneScoreCell.setHorizontalAlignment("center"); playerTwoScoreCell.setHorizontalAlignment("center");
  if (match.winner && String(match.winner) === String(match.player1)) playerOne.setBackground(green);
  if (match.winner && String(match.winner) === String(match.player2)) playerTwo.setBackground(green);
  if (champion && match.player1 && match.player1 !== "TBD") playerOne.setBackground(green).setFontSize(14);
  const status = [match.status, match.highlighted ? "Broadcast" : ""].filter(Boolean).join(" · ");
  sheet.getRange(topRow + 3, startColumn, 1, 3).merge().setValue(status)
    .setBackground(navy).setFontColor("#ffffff").setFontSize(9).setHorizontalAlignment("left");
}

function tournamentDrawRulesLink_(sheet, totalColumns, config) {
  const url = String(config["Rules URL"] || "").trim(), range = sheet.getRange(3, 1, 1, totalColumns).merge();
  range.setBackground("#f47806").setFontColor("#ffffff").setFontWeight("bold").setHorizontalAlignment("left");
  if (!url) {
    range.setValue("TOURNAMENT RULES · Link not configured");
    return;
  }
  range.setRichTextValue(
    SpreadsheetApp.newRichTextValue().setText("TOURNAMENT RULES · OPEN REGULATIONS").setLinkUrl(url).build(),
  );
}

function tournamentRenderPublicSchedule_(sheet, config, matches) {
  sheet.clear(); sheet.setHiddenGridlines(true); sheet.setFrozenRows(3);
  sheet.getRange("A1:G1").merge().setValue("Tournament schedule").setBackground("#00182f").setFontColor("#ffffff").setFontSize(18).setFontWeight("bold");
  sheet.getRange("A2:G2").merge().setValue(String(config["Tournament Name"] || "GeoNederland Tournament")).setBackground("#f47806").setFontColor("#ffffff").setFontWeight("bold");
  const headers = ["Scheduled", "Match", "Round", "Players", "Status", "Featured", "Stream"];
  sheet.getRange(3, 1, 1, headers.length).setValues([headers]).setBackground("#00182f").setFontColor("#ffffff").setFontWeight("bold");
  const rows = matches.filter((m) => m.scheduled_at).sort((a, b) => String(a.scheduled_at).localeCompare(String(b.scheduled_at))).map((m) => [m.scheduled_at, m.match_id, m.round, m.player1 + " vs " + m.player2, m.status, m.highlighted ? "Yes" : "", m.stream_url || config["Stream URL"] || ""]);
  if (rows.length) sheet.getRange(4, 1, rows.length, headers.length).setValues(rows);
  [170, 110, 130, 280, 170, 100, 260].forEach((width, index) => sheet.setColumnWidth(index + 1, width));
}

function tournamentSpreadsheetId_(value) {
  const match = String(value || "").match(/[a-zA-Z0-9-_]{20,}/);
  return match ? match[0] : "";
}

function tournamentSetConfig_(setting, value) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TOURNAMENT.SHEETS.CONFIG), rows = tournamentRows_(sheet), existing = rows.find((row) => String(row.Setting) === setting);
  if (existing) sheet.getRange(existing.__row, 2).setValue(value);
  else sheet.appendRow([setting, value, ""]);
}

function tournamentEnsureConfig_(setting, value, notes) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TOURNAMENT.SHEETS.CONFIG);
  if (!tournamentRows_(sheet).some((row) => String(row.Setting) === setting)) sheet.appendRow([setting, value, notes || ""]);
}

function tournamentEnsureInitialTournament_() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TOURNAMENT.SHEETS.TOURNAMENTS);
  if (tournamentRows_(sheet).length) return;
  const config = tournamentConfig_(), id = String(config["Active Tournament ID"] || "practice-1");
  sheet.appendRow([
    id, config["Tournament Name"] || "GeoNederland Practice Tournament", "Practice", config["Tournament Status"] || "Setup",
    Number(config["Maximum Players"] || 8), 8, Number(config["Default Best Of"] || 3), config["Preset 1"] || "",
    config["Preset 2"] || "", config["Preset 3"] || "", config["Public Spreadsheet ID"] || "",
    config["Public Bracket URL"] || "", config["Stream URL"] || "", new Date(), "", config["Rules URL"] || "",
    "", "", "", tournamentNewLiquipediaBracketId_(),
  ]);
}

// Liquipedia requires bracket IDs of exactly ten letters or digits.
function tournamentValidLiquipediaBracketId_(value) {
  return /^[A-Za-z0-9]{10}$/.test(String(value || "").trim());
}

function tournamentNewLiquipediaBracketId_() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TOURNAMENT.SHEETS.TOURNAMENTS);
  const used = new Set(tournamentRows_(sheet).map((row) => String(row["Liquipedia Bracket ID"] || "")));
  const characters = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  let id = "";
  do id = Array.from({length: 10}, () => characters[Math.floor(Math.random() * characters.length)]).join("");
  while (used.has(id));
  return id;
}

function tournamentEnsureLiquipediaBracketIds_() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TOURNAMENT.SHEETS.TOURNAMENTS);
  const column = TOURNAMENT.HEADERS.TOURNAMENTS.indexOf("Liquipedia Bracket ID") + 1;
  tournamentRows_(sheet).forEach((row) => {
    if (!tournamentValidLiquipediaBracketId_(row["Liquipedia Bracket ID"])) {
      sheet.getRange(row.__row, column).setValue(tournamentNewLiquipediaBracketId_());
    }
  });
}

function tournamentMigrateLegacyTournamentIds_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet(), id = tournamentActiveId_();
  [TOURNAMENT.SHEETS.PLAYERS, TOURNAMENT.SHEETS.MATCHES, TOURNAMENT.SHEETS.GAMES, TOURNAMENT.SHEETS.LOG].forEach((name) => {
    const sheet = ss.getSheetByName(name), headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getDisplayValues()[0];
    const column = headers.indexOf("Tournament ID") + 1;
    if (!column || sheet.getLastRow() < 2) return;
    const range = sheet.getRange(2, column, sheet.getLastRow() - 1, 1), values = range.getValues();
    let changed = false;
    values.forEach((row) => { if (!row[0]) { row[0] = id; changed = true; } });
    if (changed) range.setValues(values);
  });
}

function tournamentCleanGhostTournamentIds_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const identityHeaders = {
    [TOURNAMENT.SHEETS.PLAYERS]: "Player",
    [TOURNAMENT.SHEETS.MATCHES]: "Match ID",
    [TOURNAMENT.SHEETS.GAMES]: "Match ID",
    [TOURNAMENT.SHEETS.LOG]: "Timestamp",
  };
  Object.entries(identityHeaders).forEach(([name, identityHeader]) => {
    const sheet = ss.getSheetByName(name);
    if (!sheet || sheet.getLastRow() < 2) return;
    const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getDisplayValues()[0];
    const identityColumn = headers.indexOf(identityHeader), tournamentColumn = headers.indexOf("Tournament ID");
    if (identityColumn < 0 || tournamentColumn < 0) return;
    const rowCount = sheet.getLastRow() - 1, values = sheet.getRange(2, 1, rowCount, sheet.getLastColumn()).getValues();
    const tournamentIds = values.map((row) => [row[tournamentColumn]]);
    let changed = false;
    values.forEach((row, index) => {
      const identity = row[identityColumn], hasIdentity = identity instanceof Date || String(identity || "").trim() !== "";
      if (!hasIdentity && tournamentIds[index][0] !== "") {
        tournamentIds[index][0] = "";
        changed = true;
      }
    });
    if (changed) sheet.getRange(2, tournamentColumn + 1, rowCount, 1).setValues(tournamentIds);
  });
}

function tournamentById_(id) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TOURNAMENT.SHEETS.TOURNAMENTS);
  return tournamentRows_(sheet).find((row) => String(row["Tournament ID"]) === String(id || "")) || null;
}

function tournamentActiveId_() {
  return String(tournamentConfig_()["Active Tournament ID"] || "practice-1");
}

function tournamentActive_() {
  const tournament = tournamentById_(tournamentActiveId_());
  if (!tournament) throw Error("Active Tournament ID does not exist in the Tournaments tab.");
  return tournament;
}

function tournamentUpdateActive_(changes) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TOURNAMENT.SHEETS.TOURNAMENTS), row = tournamentActive_();
  Object.entries(changes).forEach(([header, value]) => {
    const column = TOURNAMENT.HEADERS.TOURNAMENTS.indexOf(header) + 1;
    if (!column) throw Error("Unknown tournament field: " + header);
    sheet.getRange(row.__row, column).setValue(value);
    row[header] = value;
  });
  return row;
}

function tournamentRowsForActive_(sheet) {
  const id = tournamentActiveId_();
  return tournamentRows_(sheet).filter((row) => String(row["Tournament ID"] || "") === id);
}

function setTournamentApiSecret() {
  const ui = SpreadsheetApp.getUi(), response = ui.prompt(
    "Tournament API secret",
    "Enter a long random secret. Add the same value to Render as TOURNAMENT_API_SECRET.",
    ui.ButtonSet.OK_CANCEL,
  );
  if (response.getSelectedButton() !== ui.Button.OK) return;
  const secret = String(response.getResponseText() || "").trim();
  if (secret.length < 32) throw Error("Use a secret of at least 32 characters.");
  PropertiesService.getScriptProperties().setProperty("TOURNAMENT_API_SECRET", secret);
  ui.alert("Tournament API secret saved in Script Properties.");
}

function generatePracticeTournament() {
  generateTournamentBracket();
}

function randomizeTournamentSeeding() {
  setupTournamentSystem();
  const players = tournamentCheckedInPlayers_();
  if (players.length < 2) throw Error("At least two checked-in players are required.");
  if (players.length > 64) throw Error("A bracket supports at most 64 checked-in players.");
  const ui = SpreadsheetApp.getUi(), answer = ui.alert(
    "Randomize player seeding?",
    "This replaces the current seeds for " + players.length + " checked-in players in the active tournament.",
    ui.ButtonSet.YES_NO,
  );
  if (answer !== ui.Button.YES) return;

  const seeds = Array.from({length: players.length}, (_, index) => index + 1);
  for (let index = seeds.length - 1; index > 0; index--) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [seeds[index], seeds[swapIndex]] = [seeds[swapIndex], seeds[index]];
  }
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TOURNAMENT.SHEETS.PLAYERS);
  players.forEach((player, index) => sheet.getRange(player.__row, 1).setValue(seeds[index]));
  tournamentLog_("sheet", "randomize_seeding", "", "Randomized " + players.length + " checked-in players");
  SpreadsheetApp.flush();
  SpreadsheetApp.getActiveSpreadsheet().toast(
    players.length + " players received random seeds 1–" + players.length + ".",
    "GeoNederland Tournament",
    6,
  );
}

function validateTournamentSeeding() {
  setupTournamentSystem();
  const players = tournamentValidateSeeding_(tournamentCheckedInPlayers_());
  SpreadsheetApp.getUi().alert(
    "Player seeding valid",
    players.length + " checked-in players have unique consecutive seeds 1–" + players.length + ".",
    SpreadsheetApp.getUi().ButtonSet.OK,
  );
  return players;
}

function tournamentCheckedInPlayers_() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TOURNAMENT.SHEETS.PLAYERS);
  return tournamentRowsForActive_(sheet).filter(
    (row) => tournamentBool_(row["Checked In"]) && String(row.Status || "").toLowerCase() !== "withdrawn",
  );
}

function tournamentValidateSeeding_(players) {
  if (players.length < 2) throw Error("At least two checked-in players are required.");
  if (players.length > 64) throw Error("A bracket supports at most 64 checked-in players.");
  const seen = {}, problems = [];
  players.forEach((player) => {
    const name = String(player.Player || "Unknown"), seed = Number(player.Seed);
    if (!Number.isInteger(seed) || seed < 1 || seed > 64) {
      problems.push(name + ": missing or invalid seed");
    } else if (seen[seed]) {
      problems.push(name + ": seed " + seed + " is already used by " + seen[seed]);
    } else {
      seen[seed] = name;
    }
  });
  const orderedSeeds = Object.keys(seen).map(Number).sort((a, b) => a - b);
  const missing = Array.from({length: players.length}, (_, index) => index + 1).filter((seed) => !seen[seed]);
  const outside = orderedSeeds.filter((seed) => seed > players.length);
  if (missing.length || outside.length) {
    problems.push(
      "Use consecutive seeds 1–" + players.length + ". Missing: " + (missing.join(", ") || "none") +
      "; outside range: " + (outside.join(", ") || "none"),
    );
  }
  if (problems.length) throw Error("Fix Tournament Players seeding:\n\n" + problems.join("\n"));
  return players.slice().sort((a, b) => Number(a.Seed) - Number(b.Seed));
}

function generateTournamentBracket() {
  setupTournamentSystem();
  const ss = SpreadsheetApp.getActiveSpreadsheet(), tournament = tournamentActive_();
  const players = tournamentValidateSeeding_(tournamentCheckedInPlayers_());
  const maximumPlayers = Math.min(64, Number(tournament["Maximum Players"] || 64));
  if (players.length > maximumPlayers) throw Error("This tournament supports at most " + maximumPlayers + " checked-in players.");
  const configuredSize = Number(tournament["Bracket Size"] || 0);
  const bracketSize = configuredSize >= players.length ? configuredSize : Math.pow(2, Math.ceil(Math.log(players.length) / Math.log(2)));
  if (![2, 4, 8, 16, 32, 64].includes(bracketSize)) throw Error("Bracket size must be 2, 4, 8, 16, 32 or 64.");
  const matchesSheet = ss.getSheetByName(TOURNAMENT.SHEETS.MATCHES);
  const oldMatches = tournamentRowsForActive_(matchesSheet);
  if (oldMatches.length) {
    const choice = SpreadsheetApp.getUi().alert(
      "Replace active bracket?",
      "Only matches for " + tournament["Tournament Name"] + " will be replaced. Other tournaments remain untouched.",
      SpreadsheetApp.getUi().ButtonSet.YES_NO,
    );
    if (choice !== SpreadsheetApp.getUi().Button.YES) return;
    for (let index = oldMatches.length - 1; index >= 0; index--) matchesSheet.deleteRow(oldMatches[index].__row);
  }

  const config = tournamentConfig_(), bestOf = Number(tournament["Default Best Of"] || config["Default Best Of"] || 3);
  const presets = [tournament["Preset 1"] || config["Preset 1"] || "", tournament["Preset 2"] || config["Preset 2"] || "", tournament["Preset 3"] || config["Preset 3"] || ""];
  const seeded = {};
  players.forEach((player) => seeded[Number(player.Seed)] = String(player.Player));
  const seedOrder = tournamentSeedOrder_(bracketSize), rounds = Math.log(bracketSize) / Math.log(2), rows = [];
  let order = 1, previousCount = bracketSize / 2;
  for (let matchIndex = 0; matchIndex < previousCount; matchIndex++) {
    const player1 = seeded[seedOrder[matchIndex * 2]] || "BYE", player2 = seeded[seedOrder[matchIndex * 2 + 1]] || "BYE";
    rows.push(tournamentMatchRow_({
      id: tournament["Tournament ID"] + "-R1-M" + (matchIndex + 1), round: tournamentRoundName_(rounds, 1), order: order++,
      player1, player2, bestOf, presets, next: rounds === 1 ? "" : tournament["Tournament ID"] + "-R2-M" + (Math.floor(matchIndex / 2) + 1),
      slot: matchIndex % 2 + 1, highlighted: rounds === 1, tournamentId: tournament["Tournament ID"],
    }));
  }
  for (let round = 2; round <= rounds; round++) {
    const count = bracketSize / Math.pow(2, round);
    for (let matchIndex = 0; matchIndex < count; matchIndex++) {
      const final = round === rounds;
      rows.push(tournamentMatchRow_({
        id: tournament["Tournament ID"] + "-R" + round + "-M" + (matchIndex + 1), round: tournamentRoundName_(rounds, round), order: order++,
        bestOf, presets, next: final ? "" : tournament["Tournament ID"] + "-R" + (round + 1) + "-M" + (Math.floor(matchIndex / 2) + 1),
        slot: matchIndex % 2 + 1, highlighted: final, tournamentId: tournament["Tournament ID"],
      }));
    }
  }
  matchesSheet.getRange(matchesSheet.getLastRow() + 1, 1, rows.length, TOURNAMENT.HEADERS.MATCHES.length).setValues(rows);
  tournamentFormat_(ss);
  tournamentLog_("sheet", "generate_bracket", "", "Generated " + bracketSize + "-player bracket");
  const publicId = tournamentSpreadsheetId_(tournament["Public Spreadsheet ID"]);
  if (publicId) syncTournamentPublicSpreadsheet();
  ss.toast(bracketSize + "-player bracket generated.", "GeoNederland Tournament", 6);
}

function tournamentSeedOrder_(size) {
  let order = [1, 2];
  while (order.length < size) {
    const nextSize = order.length * 2, next = [];
    order.forEach((seed) => { next.push(seed); next.push(nextSize + 1 - seed); });
    order = next;
  }
  return order;
}

function tournamentRoundName_(totalRounds, round) {
  const remaining = totalRounds - round;
  if (remaining === 0) return "Final";
  if (remaining === 1) return "Semifinal";
  if (remaining === 2) return "Quarterfinal";
  return "Round of " + Math.pow(2, remaining + 1);
}

function tournamentMatchRow_(input) {
  const status = input.player1 && input.player2 ? "Waiting for players" : "Waiting for opponent";
  return [
    input.id, input.round, input.order, input.player1 || "TBD", input.player2 || "TBD",
    input.bestOf || 3, input.presets[0] || "", input.presets[1] || "", input.presets[2] || "",
    Boolean(input.highlighted), false, false, false, status, "", "0-0", "",
    input.next || "", input.slot || "", "", "", "", new Date(), input.tournamentId || tournamentActiveId_(),
  ];
}

function tournamentInitSheet_(ss, name, headers) {
  const sheet = ss.getSheetByName(name) || ss.insertSheet(name);
  if (sheet.getMaxColumns() < headers.length) {
    sheet.insertColumnsAfter(sheet.getMaxColumns(), headers.length - sheet.getMaxColumns());
  }
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  return sheet;
}

function tournamentValidation_(ss) {
  const players = ss.getSheetByName(TOURNAMENT.SHEETS.PLAYERS), matches = ss.getSheetByName(TOURNAMENT.SHEETS.MATCHES);
  players.getRange("A2:A").setDataValidation(
    SpreadsheetApp.newDataValidation()
      .requireNumberBetween(1, 64)
      .setAllowInvalid(false)
      .setHelpText("Enter a unique manual seed from 1 to 64.")
      .build(),
  );
  players.getRange("G2:G").setDataValidation(SpreadsheetApp.newDataValidation().requireValueInList(["Registered", "Checked In", "Withdrawn", "Disqualified"], true).build());
  players.getRange("H2:H").insertCheckboxes();
  matches.getRange("J2:M").insertCheckboxes();
  matches.getRange("N2:N").setDataValidation(SpreadsheetApp.newDataValidation().requireValueInList([
    "Waiting for opponent", "Waiting for players", "Waiting for broadcast", "Ready to start", "Live", "Pending result", "Complete", "On hold", "Disqualified",
  ], true).build());
}

function tournamentFormat_(ss) {
  Object.values(TOURNAMENT.SHEETS).forEach((name) => {
    const sheet = ss.getSheetByName(name);
    if (!sheet) return;
    sheet.setFrozenRows(1);
    sheet.setHiddenGridlines(true);
    const lastColumn = sheet.getLastColumn();
    sheet.getRange(1, 1, 1, lastColumn).setBackground("#00182f").setFontColor("#ffffff").setFontWeight("bold");
    sheet.getRange(1, 1, Math.max(1, sheet.getLastRow()), lastColumn).setVerticalAlignment("middle");
    sheet.autoResizeColumns(1, lastColumn);
    for (let col = 1; col <= lastColumn; col++) sheet.setColumnWidth(col, Math.min(260, Math.max(90, sheet.getColumnWidth(col))));
  });
  const matches = ss.getSheetByName(TOURNAMENT.SHEETS.MATCHES);
  matches.setColumnWidth(4, 170); matches.setColumnWidth(5, 170);
  matches.setColumnWidth(7, 240); matches.setColumnWidth(8, 240); matches.setColumnWidth(9, 240);
  matches.setColumnWidth(14, 150); matches.setColumnWidth(15, 240); matches.setColumnWidth(21, 240);
}

function tournamentRows_(sheet) {
  if (!sheet || sheet.getLastRow() < 2) return [];
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getDisplayValues()[0];
  const identityHeaders = {
    [TOURNAMENT.SHEETS.CONFIG]: "Setting",
    [TOURNAMENT.SHEETS.TOURNAMENTS]: "Tournament ID",
    [TOURNAMENT.SHEETS.PLAYERS]: "Player",
    [TOURNAMENT.SHEETS.MATCHES]: "Match ID",
    [TOURNAMENT.SHEETS.GAMES]: "Match ID",
    [TOURNAMENT.SHEETS.LOG]: "Timestamp",
  };
  const identityHeader = identityHeaders[sheet.getName()] || headers[0];
  return sheet.getRange(2, 1, sheet.getLastRow() - 1, sheet.getLastColumn()).getValues().map((values, index) => {
    const row = {__row: index + 2};
    headers.forEach((header, col) => row[header] = values[col]);
    return row;
  }).filter((row) => {
    const identity = row[identityHeader];
    return identity instanceof Date || String(identity || "").trim() !== "";
  });
}

function tournamentConfig_() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TOURNAMENT.SHEETS.CONFIG), result = {};
  tournamentRows_(sheet).forEach((row) => { if (row.Setting) result[String(row.Setting)] = row.Value; });
  return result;
}

function tournamentBool_(value) {
  return value === true || ["true", "yes", "1", "ready"].includes(String(value || "").trim().toLowerCase());
}

function tournamentJson_(value) {
  return ContentService.createTextOutput(JSON.stringify(value)).setMimeType(ContentService.MimeType.JSON);
}

function tournamentAuthorize_(secret) {
  const expected = PropertiesService.getScriptProperties().getProperty("TOURNAMENT_API_SECRET") || "";
  if (!expected || String(secret || "") !== expected) throw Error("Unauthorized tournament API request.");
}

function doGet(e) {
  try {
    tournamentAuthorize_(e && e.parameter && e.parameter.secret);
    const action = String(e.parameter.action || "health");
    if (action === "health") return tournamentJson_({ok: true, service: "geonederland-tournament"});
    if (action === "bracket") return tournamentJson_({ok: true, config: Object.assign({}, tournamentConfig_(), tournamentActive_()), matches: tournamentPublicMatches_()});
    if (action === "match") return tournamentJson_({ok: true, match: tournamentMatchForUser_(e.parameter.discord_user_id, e.parameter.discord_name, e.parameter.discord_display_name)});
    if (action === "public_index") return tournamentJson_({ok: true, tournaments: tournamentWebsiteIndex_(), updated_at: tournamentWebsiteUpdatedAt_()});
    if (action === "public_tournament") return tournamentJson_({ok: true, tournament: tournamentWebsiteDetail_(e.parameter.tournament_id)});
    throw Error("Unknown action: " + action);
  } catch (error) {
    return tournamentJson_({ok: false, error: String(error.message || error)});
  }
}

function doPost(e) {
  try {
    const payload = JSON.parse((e && e.postData && e.postData.contents) || "{}");
    tournamentAuthorize_(payload.secret);
    const data = tournamentHandleAction_(payload);
    return tournamentJson_({ok: true, data});
  } catch (error) {
    return tournamentJson_({ok: false, error: String(error.message || error)});
  }
}

function tournamentPublicMatches_() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TOURNAMENT.SHEETS.MATCHES);
  return tournamentRowsForActive_(sheet).map(tournamentPublicMatch_);
}

function tournamentPublicMatch_(row) {
  return {
    match_id: String(row["Match ID"] || ""), round: String(row.Round || ""),
    order: Number(row["Bracket Order"] || 0), player1: String(row["Player 1"] || "TBD"),
    player2: String(row["Player 2"] || "TBD"), best_of: Number(row["Best Of"] || 3),
    presets: [row["Preset 1"], row["Preset 2"], row["Preset 3"]].map(String),
    highlighted: tournamentBool_(row.Highlighted), player1_ready: tournamentBool_(row["Player 1 Ready"]),
    player2_ready: tournamentBool_(row["Player 2 Ready"]), admin_released: tournamentBool_(row["Admin Released"]),
    status: String(row.Status || ""), party_url: String(row["Party URL"] || ""),
    series_score: String(row["Series Score"] || "0-0"), winner: String(row.Winner || ""),
    scheduled_at: tournamentDateIso_(row["Scheduled At"]), stream_url: String(row["Stream URL"] || ""),
  };
}

/* Strict public allowlist shared by the website and Liquipedia exporter. */
function tournamentWebsiteIndex_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  return tournamentRows_(ss.getSheetByName(TOURNAMENT.SHEETS.TOURNAMENTS)).map((row) => {
    const id = String(row["Tournament ID"] || "");
    const players = tournamentRowsFor_(ss.getSheetByName(TOURNAMENT.SHEETS.PLAYERS), id)
      .filter((player) => !["Withdrawn", "Disqualified"].includes(String(player.Status)));
    const matches = tournamentRowsFor_(ss.getSheetByName(TOURNAMENT.SHEETS.MATCHES), id);
    const final = matches.find((match) => String(match.Round) === "Final");
    return tournamentWebsiteSummary_(row, players.length, matches.length, final && final.Winner);
  });
}

function tournamentWebsiteDetail_(tournamentId) {
  const id = String(tournamentId || "").trim();
  if (!/^[a-z0-9-]{1,80}$/i.test(id)) throw Error("Invalid tournament ID.");
  const tournament = tournamentById_(id);
  if (!tournament) throw Error("Tournament not found.");
  if (!tournamentValidLiquipediaBracketId_(tournament["Liquipedia Bracket ID"])) {
    const column = TOURNAMENT.HEADERS.TOURNAMENTS.indexOf("Liquipedia Bracket ID") + 1;
    tournament["Liquipedia Bracket ID"] = tournamentNewLiquipediaBracketId_();
    SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TOURNAMENT.SHEETS.TOURNAMENTS)
      .getRange(tournament.__row, column).setValue(tournament["Liquipedia Bracket ID"]);
  }
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const players = tournamentRowsFor_(ss.getSheetByName(TOURNAMENT.SHEETS.PLAYERS), id)
    .filter((row) => !["Withdrawn", "Disqualified"].includes(String(row.Status)));
  const avatars = tournamentAvatarMap_(players);
  const matches = tournamentRowsFor_(ss.getSheetByName(TOURNAMENT.SHEETS.MATCHES), id)
    .map((row) => tournamentWebsiteMatch_(row, avatars)).sort((a, b) => a.order - b.order);
  const final = matches.find((match) => match.round === "Final");
  return Object.assign(tournamentWebsiteSummary_(tournament, players.length, matches.length, final && final.winner), {
    participants: players.map((row) => tournamentWebsitePlayer_(row, avatars)).sort((a, b) => a.seed - b.seed),
    matches,
    highlighted_matches: matches.filter((match) => match.highlighted),
    rounds: [...new Set(matches.map((match) => match.round).filter(Boolean))],
    liquipedia_bracket_id: String(tournament["Liquipedia Bracket ID"]),
    updated_at: tournamentWebsiteUpdatedAt_(id),
  });
}

function tournamentWebsiteSummary_(row, participantCount, matchCount, winner) {
  const status = String(row.Status || "Setup"), phase = ["complete", "completed", "archived"].includes(status.toLowerCase())
    ? "completed" : (["live", "in progress", "check-in", "checkin"].includes(status.toLowerCase()) ? "live" : "upcoming");
  return {
    id: String(row["Tournament ID"] || ""), name: String(row["Tournament Name"] || "GeoNederland Tournament"),
    type: String(row.Type || "Single Elimination"), status, phase,
    maximum_players: Number(row["Maximum Players"] || 0), bracket_size: Number(row["Bracket Size"] || 0),
    default_best_of: Number(row["Default Best Of"] || 3), participant_count: Number(participantCount || 0),
    match_count: Number(matchCount || 0), winner: String(winner || ""),
    rules_url: tournamentWebsiteUrl_(row["Rules URL"]), registration_url: tournamentWebsiteUrl_(row["Registration URL"]),
    stream_url: tournamentWebsiteUrl_(row["Stream URL"]), start_at: tournamentDateIso_(row["Start At"]),
    end_at: tournamentDateIso_(row["End At"]), created_at: tournamentDateIso_(row["Created At"]),
  };
}

function tournamentWebsitePlayer_(row, avatars) {
  const player = String(row.Player || "");
  return {
    seed: Number(row.Seed || 0), player,
    country: String(row.Country || "").toUpperCase().replace(/[^A-Z]/g, "").slice(0, 3),
    status: ["Registered", "Checked In"].includes(String(row.Status)) ? String(row.Status) : "Registered",
    avatar_url: String((avatars || {})[player] || ""),
  };
}

function tournamentWebsiteMatch_(row, avatars) {
  const player1 = String(row["Player 1"] || "TBD"), player2 = String(row["Player 2"] || "TBD");
  return {
    match_id: String(row["Match ID"] || ""), round: String(row.Round || ""), order: Number(row["Bracket Order"] || 0),
    player1, player2, player1_avatar_url: String((avatars || {})[player1] || ""),
    player2_avatar_url: String((avatars || {})[player2] || ""), best_of: Number(row["Best Of"] || 3),
    highlighted: tournamentBool_(row.Highlighted), status: String(row.Status || ""),
    series_score: String(row["Series Score"] || "0-0").replace(/[^0-9\-–: ]/g, "").slice(0, 20),
    winner: String(row.Winner || ""), scheduled_at: tournamentDateIso_(row["Scheduled At"]),
    stream_url: tournamentWebsiteUrl_(row["Stream URL"]), updated_at: tournamentDateIso_(row["Updated At"]),
  };
}

function tournamentWebsiteUrl_(value) {
  const url = String(value || "").trim();
  return /^https:\/\/[a-z0-9.-]+(?:[\/:?#][^\s]*)?$/i.test(url) ? url.slice(0, 500) : "";
}

function tournamentWebsiteUpdatedAt_(tournamentId) {
  const ss = SpreadsheetApp.getActiveSpreadsheet(), values = [];
  [[TOURNAMENT.SHEETS.TOURNAMENTS, "Created At"], [TOURNAMENT.SHEETS.PLAYERS, "Updated At"], [TOURNAMENT.SHEETS.MATCHES, "Updated At"]]
    .forEach(([sheetName, field]) => {
      const sheet = ss.getSheetByName(sheetName), rows = tournamentId ? tournamentRowsFor_(sheet, tournamentId) : tournamentRows_(sheet);
      rows.forEach((row) => {
      if (row[field] instanceof Date) values.push(row[field]);
      });
    });
  return values.length ? new Date(Math.max(...values.map((value) => value.getTime()))).toISOString() : "";
}

function tournamentAvatarMap_(players) {
  const cache = CacheService.getScriptCache(), avatars = {}, missing = [];
  (players || []).forEach((row) => {
    const player = String(row.Player || ""), userId = String(row["GeoGuessr User ID"] || "").trim();
    if (!player || !/^[A-Za-z0-9_-]{6,80}$/.test(userId)) return;
    const key = "tournament-avatar-" + userId, cached = cache.get(key);
    if (cached !== null) avatars[player] = cached === "__none__" ? "" : cached;
    else missing.push({player, userId, key});
  });
  for (let offset = 0; offset < missing.length; offset += 20) {
    const batch = missing.slice(offset, offset + 20);
    let responses = [];
    try {
      responses = UrlFetchApp.fetchAll(batch.map((item) => ({
        url: "https://www.geoguessr.com/api/v3/users/" + encodeURIComponent(item.userId),
        method: "get", muteHttpExceptions: true,
        headers: {"User-Agent": "GeoNederland-Tournament/1.0"},
      })));
    } catch (error) {
      responses = [];
    }
    batch.forEach((item, index) => {
      let avatar = "";
      try {
        const response = responses[index];
        if (response && response.getResponseCode() >= 200 && response.getResponseCode() < 300) {
          avatar = tournamentGeoGuessrAvatarUrl_(JSON.parse(response.getContentText()));
        }
      } catch (error) {
        avatar = "";
      }
      avatars[item.player] = avatar;
      cache.put(item.key, avatar || "__none__", 21600);
    });
  }
  return avatars;
}

function tournamentGeoGuessrAvatarUrl_(profile) {
  const data = profile || {}, image = String(
    data.fullBodyPin || (data.avatar || {}).fullBodyPath || (data.pin || {}).url || data.customImage || "",
  ).trim();
  if (!image) return "";
  if (/^https:\/\/(?:www\.)?geoguessr\.com\//i.test(image)) return image.slice(0, 1000);
  const path = image.replace(/^\/+/, "");
  if (!path || /[\s{}<>]/.test(path) || path.includes(":")) return "";
  return "https://www.geoguessr.com/images/resize:fill:512:512/gravity:no:0:0/plain/" + path.slice(0, 800);
}

function tournamentDateIso_(value) {
  return value instanceof Date && !Number.isNaN(value.getTime()) ? value.toISOString() : String(value || "");
}

function tournamentPlayerByDiscord_(discordUserId, discordName, discordDisplayName) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TOURNAMENT.SHEETS.PLAYERS);
  const id = String(discordUserId || "").trim(), names = [discordName, discordDisplayName]
    .map((value) => String(value || "").trim().replace(/^@/, "").toLowerCase()).filter(Boolean);
  return tournamentRowsForActive_(sheet).find((row) => {
    const rowId = String(row["Discord User ID"] || "").trim(), rowName = String(row.Discord || "").trim().replace(/^@/, "").toLowerCase();
    return (id && rowId === id) || (rowName && names.includes(rowName));
  }) || null;
}

function tournamentMatchForUser_(discordUserId, discordName, discordDisplayName) {
  const player = tournamentPlayerByDiscord_(discordUserId, discordName, discordDisplayName);
  if (!player) return null;
  const matches = tournamentRowsForActive_(SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TOURNAMENT.SHEETS.MATCHES));
  const match = matches.find((row) => !["Complete", "Disqualified"].includes(String(row.Status)) && [row["Player 1"], row["Player 2"]].includes(player.Player));
  return match ? tournamentPublicMatch_(match) : null;
}

function tournamentHandleAction_(payload) {
  const action = String(payload.action || "");
  if (action === "register") return tournamentRegister_(payload);
  if (action === "checkin") return tournamentCheckIn_(payload);
  if (action === "unregister") return tournamentUnregister_(payload);
  const match = tournamentFindMatch_(payload.match_id);
  if (["ready", "party", "result"].includes(action)) tournamentRequireParticipant_(match, payload.discord_user_id, payload.discord_name, payload.discord_display_name);
  if (action === "ready") return tournamentSetReady_(match, payload.discord_user_id, payload.discord_name, payload.discord_display_name);
  if (action === "party") return tournamentSetParty_(match, payload.discord_user_id, payload.url, payload.discord_name, payload.discord_display_name);
  if (action === "result") return tournamentSubmitResult_(match, payload.discord_user_id, payload.url, payload.discord_name, payload.discord_display_name);
  if (action === "release") return tournamentRelease_(match, payload.actor || payload.discord_user_id);
  if (action === "highlight") return tournamentHighlight_(match, payload.actor || payload.discord_user_id, payload.highlighted);
  if (action === "resolve") return tournamentResolve_(match, payload.actor || payload.discord_user_id, payload.winner, payload.score);
  throw Error("Unknown tournament action: " + action);
}

function tournamentGeoGuessrUserId_(value) {
  const text = String(value || "").trim();
  const match = text.match(/geoguessr\.com\/user\/([^/?#]+)/i);
  const id = decodeURIComponent(match ? match[1] : text).trim();
  if (!/^[a-zA-Z0-9_-]{6,80}$/.test(id)) throw Error("Use a valid GeoGuessr profile URL or user ID.");
  return id;
}

function tournamentRegistrationIdentity_(payload) {
  const discordId = String(payload.discord_user_id || "").trim();
  const discordName = String(payload.discord_name || payload.discord_display_name || "").trim().replace(/^@/, "");
  if (!discordId || !discordName) throw Error("Discord identity is missing.");
  return {discordId, discordName};
}

function tournamentPlayerPublic_(row, created) {
  return {
    created: Boolean(created), player: String(row.Player || ""), country: String(row.Country || ""),
    status: String(row.Status || ""), checked_in: tournamentBool_(row["Checked In"]),
    geoguessr_user_id: String(row["GeoGuessr User ID"] || ""),
  };
}

function tournamentRegister_(payload) {
  const config = tournamentConfig_(), tournament = tournamentActive_();
  if (String(config["Registration Status"] || "Closed").toLowerCase() !== "open") throw Error("Tournament registration is closed.");
  const identity = tournamentRegistrationIdentity_(payload), player = String(payload.player || "").trim();
  const country = String(payload.country || "").trim().toUpperCase(), geoId = tournamentGeoGuessrUserId_(payload.geoguessr_profile);
  if (player.length < 2 || player.length > 40) throw Error("Player name must contain 2 to 40 characters.");
  if (!["NL", "BE", "LU"].includes(country)) throw Error("Country must be NL, BE or LU.");
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TOURNAMENT.SHEETS.PLAYERS), rows = tournamentRowsForActive_(sheet);
  const own = rows.find((row) => String(row["Discord User ID"] || "") === identity.discordId);
  const conflict = rows.find((row) => String(row["Discord User ID"] || "") !== identity.discordId && (
    String(row["GeoGuessr User ID"] || "").toLowerCase() === geoId.toLowerCase() || String(row.Player || "").toLowerCase() === player.toLowerCase()
  ));
  if (conflict) throw Error("That GeoGuessr account or player name is already registered.");
  if (!own) {
    const maximum = Math.min(64, Number(tournament["Maximum Players"] || config["Maximum Players"] || 32));
    if (rows.filter((row) => !["Withdrawn", "Disqualified"].includes(String(row.Status))).length >= maximum) throw Error("Tournament registration is full.");
  }
  const now = new Date(), values = [own ? own.Seed : "", player, geoId, identity.discordName, identity.discordId, country,
    "Registered", false, own && own["Registered At"] || now, "", now, own && own.Notes || "", tournamentActiveId_()];
  const rowNumber = own ? own.__row : sheet.getLastRow() + 1;
  sheet.getRange(rowNumber, 1, 1, TOURNAMENT.HEADERS.PLAYERS.length).setValues([values]);
  tournamentLog_(identity.discordId, own ? "registration_updated" : "registered", "", player + " · " + country);
  return tournamentPlayerPublic_(Object.assign({__row: rowNumber}, Object.fromEntries(TOURNAMENT.HEADERS.PLAYERS.map((header, index) => [header, values[index]]))), !own);
}

function tournamentCheckIn_(payload) {
  const identity = tournamentRegistrationIdentity_(payload), row = tournamentPlayerByDiscord_(identity.discordId, identity.discordName, payload.discord_display_name);
  if (!row) throw Error("You are not registered. Use /register first.");
  if (["Withdrawn", "Disqualified"].includes(String(row.Status))) throw Error("This registration cannot be checked in.");
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TOURNAMENT.SHEETS.PLAYERS), now = new Date();
  sheet.getRange(row.__row, 7, 1, 5).setValues([["Checked In", true, row["Registered At"] || now, now, now]]);
  row.Status = "Checked In"; row["Checked In"] = true; row["Checked In At"] = now;
  tournamentLog_(identity.discordId, "checked_in", "", row.Player);
  return tournamentPlayerPublic_(row, false);
}

function tournamentUnregister_(payload) {
  const identity = tournamentRegistrationIdentity_(payload), row = tournamentPlayerByDiscord_(identity.discordId, identity.discordName, payload.discord_display_name);
  if (!row) throw Error("You are not registered.");
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TOURNAMENT.SHEETS.PLAYERS), now = new Date();
  sheet.getRange(row.__row, 7, 1, 5).setValues([["Withdrawn", false, row["Registered At"] || now, "", now]]);
  row.Status = "Withdrawn"; row["Checked In"] = false;
  tournamentLog_(identity.discordId, "withdrawn", "", row.Player);
  return tournamentPlayerPublic_(row, false);
}

function tournamentFindMatch_(matchId) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TOURNAMENT.SHEETS.MATCHES);
  const match = tournamentRowsForActive_(sheet).find((row) => String(row["Match ID"]) === String(matchId || ""));
  if (!match) throw Error("Match not found: " + matchId);
  match.__sheet = sheet;
  return match;
}

function tournamentRequireParticipant_(match, discordUserId, discordName, discordDisplayName) {
  const player = tournamentPlayerByDiscord_(discordUserId, discordName, discordDisplayName);
  if (!player || ![match["Player 1"], match["Player 2"]].includes(player.Player)) throw Error("You are not a player in this match.");
  return player;
}

function tournamentWriteMatch_(match, changes) {
  const headers = TOURNAMENT.HEADERS.MATCHES;
  Object.entries(changes).forEach(([name, value]) => {
    const column = headers.indexOf(name) + 1;
    if (!column) throw Error("Unknown match field: " + name);
    match.__sheet.getRange(match.__row, column).setValue(value);
    match[name] = value;
  });
  const updatedColumn = headers.indexOf("Updated At") + 1;
  match.__sheet.getRange(match.__row, updatedColumn).setValue(new Date());
  try {
    if (tournamentSpreadsheetId_(tournamentActive_()["Public Spreadsheet ID"])) syncTournamentPublicSpreadsheet();
  } catch (error) {
    tournamentLog_("system", "public_sync_error", match["Match ID"], String(error.message || error));
  }
  return tournamentPublicMatch_(match);
}

function tournamentSetReady_(match, discordUserId, discordName, discordDisplayName) {
  if (["Complete", "Disqualified"].includes(String(match.Status))) throw Error("This match is already closed.");
  const player = tournamentRequireParticipant_(match, discordUserId, discordName, discordDisplayName), field = player.Player === match["Player 1"] ? "Player 1 Ready" : "Player 2 Ready";
  match[field] = true;
  const both = tournamentBool_(match["Player 1 Ready"]) && tournamentBool_(match["Player 2 Ready"]);
  const status = both ? (tournamentBool_(match.Highlighted) && !tournamentBool_(match["Admin Released"]) ? "Waiting for broadcast" : "Ready to start") : "Waiting for players";
  tournamentLog_(discordUserId, "ready", match["Match ID"], player.Player);
  return tournamentWriteMatch_(match, {[field]: true, Status: status});
}

function tournamentSetParty_(match, discordUserId, url, discordName, discordDisplayName) {
  const player = tournamentRequireParticipant_(match, discordUserId, discordName, discordDisplayName);
  if (String(player.Player) !== String(match["Player 1"])) {
    throw Error("Only " + match["Player 1"] + " (the upper/left player) can create the party and submit its link.");
  }
  const value = String(url || "").trim();
  if (!/^https:\/\/(www\.)?geoguessr\.com\/(party|game|duels)\//i.test(value)) throw Error("Enter a valid GeoGuessr party link.");
  if (!(tournamentBool_(match["Player 1 Ready"]) && tournamentBool_(match["Player 2 Ready"]))) throw Error("Both players must be ready first.");
  if (tournamentBool_(match.Highlighted) && !tournamentBool_(match["Admin Released"])) throw Error("This highlighted match is waiting for an administrator.");
  tournamentLog_(discordUserId, "party", match["Match ID"], value);
  return tournamentWriteMatch_(match, {"Party URL": value, Status: "Live"});
}

function tournamentSubmitResult_(match, discordUserId, url, discordName, discordDisplayName) {
  tournamentRequireParticipant_(match, discordUserId, discordName, discordDisplayName);
  const value = String(url || "").trim();
  if (!/^https:\/\/(www\.)?geoguessr\.com\//i.test(value)) throw Error("Enter a valid GeoGuessr result link.");
  const gamesSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TOURNAMENT.SHEETS.GAMES);
  const existing = tournamentRowsForActive_(gamesSheet).filter((row) => String(row["Match ID"]) === String(match["Match ID"]));
  const gameNumber = existing.length + 1;
  if (existing.some((row) => String(row["Result URL"]) === value)) throw Error("This result link has already been submitted.");
  const mode = ["Moving", "No Move", "NMPZ"][Math.min(gameNumber - 1, 2)] || "Tiebreak";
  gamesSheet.appendRow([new Date(), match["Match ID"], gameNumber, mode, value, String(discordUserId), "", "", "", "Pending review", "", tournamentActiveId_()]);
  tournamentLog_(discordUserId, "result", match["Match ID"], value);
  return tournamentWriteMatch_(match, {Status: "Pending result"});
}

function tournamentRelease_(match, actor) {
  const both = tournamentBool_(match["Player 1 Ready"]) && tournamentBool_(match["Player 2 Ready"]);
  tournamentLog_(actor, "release", match["Match ID"], "Admin start permission granted");
  return tournamentWriteMatch_(match, {"Admin Released": true, Status: both ? "Ready to start" : "Waiting for players"});
}

function tournamentHighlight_(match, actor, highlighted) {
  const enabled = tournamentBool_(highlighted), both = tournamentBool_(match["Player 1 Ready"]) && tournamentBool_(match["Player 2 Ready"]);
  let status = String(match.Status || "Waiting for players");
  if (both && !match["Party URL"]) status = enabled && !tournamentBool_(match["Admin Released"]) ? "Waiting for broadcast" : "Ready to start";
  tournamentLog_(actor, "highlight", match["Match ID"], enabled ? "Enabled" : "Disabled");
  return tournamentWriteMatch_(match, {Highlighted: enabled, Status: status});
}

function tournamentResolve_(match, actor, winner, score) {
  const name = String(winner || "").trim();
  if (![match["Player 1"], match["Player 2"]].includes(name)) throw Error("Winner must match one of the two players.");
  const result = tournamentWriteMatch_(match, {Winner: name, "Series Score": String(score || ""), Status: "Complete"});
  if (match["Next Match ID"]) {
    const next = tournamentFindMatch_(match["Next Match ID"]), slot = Number(match["Next Slot"] || 1);
    const field = slot === 2 ? "Player 2" : "Player 1";
    const other = slot === 2 ? next["Player 1"] : next["Player 2"];
    const nextStatus = other && other !== "TBD" ? "Waiting for players" : "Waiting for opponent";
    tournamentWriteMatch_(next, {[field]: name, Status: nextStatus});
  }
  tournamentLog_(actor, "resolve", match["Match ID"], name + " " + String(score || ""));
  return result;
}

function tournamentLog_(actor, action, matchId, details) {
  const ss = SpreadsheetApp.getActiveSpreadsheet(), sheet = ss.getSheetByName(TOURNAMENT.SHEETS.LOG);
  if (sheet) sheet.appendRow([new Date(), String(actor || ""), action, matchId || "", details || "", tournamentActiveId_()]);
}

