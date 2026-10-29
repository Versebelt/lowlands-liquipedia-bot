/**
 * GeoNederland Tournament Control
 * Install ONLY in the dedicated Tournament Admin spreadsheet.
 * The Lowlands League Season 2 spreadsheets are not used by this project.
 */

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("Tournament Control")
    .addItem("Set up / repair Admin sheet", "setupTournamentSystem")
    .addItem("Set up / repair Public bracket", "setupTournamentPublicSpreadsheet")
    .addSeparator()
    .addItem("Generate 8-player practice bracket", "generatePracticeTournament")
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
    PLAYERS: "Tournament Players",
    MATCHES: "Tournament Matches",
    GAMES: "Tournament Games",
    LOG: "Tournament Log",
  },
  HEADERS: {
    CONFIG: ["Setting", "Value", "Notes"],
    PLAYERS: [
      "Seed", "Player", "GeoGuessr User ID", "Discord", "Discord User ID", "Country",
      "Status", "Checked In", "Registered At", "Checked In At", "Updated At", "Notes",
    ],
    MATCHES: [
      "Match ID", "Round", "Bracket Order", "Player 1", "Player 2",
      "Best Of", "Preset 1", "Preset 2", "Preset 3", "Highlighted",
      "Player 1 Ready", "Player 2 Ready", "Admin Released", "Status",
      "Party URL", "Series Score", "Winner", "Next Match ID", "Next Slot",
      "Scheduled At", "Stream URL", "Discord Message ID", "Updated At",
    ],
    GAMES: [
      "Submitted At", "Match ID", "Game", "Mode", "Result URL", "Submitted By",
      "Player 1 Score", "Player 2 Score", "Winner", "Status", "Notes",
    ],
    LOG: ["Timestamp", "Actor", "Action", "Match ID", "Details"],
  },
};

function setupTournamentSystem() {
  const ss = SpreadsheetApp.getActiveSpreadsheet(), s = TOURNAMENT.SHEETS;
  tournamentInitSheet_(ss, s.CONFIG, TOURNAMENT.HEADERS.CONFIG);
  tournamentInitSheet_(ss, s.PLAYERS, TOURNAMENT.HEADERS.PLAYERS);
  tournamentInitSheet_(ss, s.MATCHES, TOURNAMENT.HEADERS.MATCHES);
  tournamentInitSheet_(ss, s.GAMES, TOURNAMENT.HEADERS.GAMES);
  tournamentInitSheet_(ss, s.LOG, TOURNAMENT.HEADERS.LOG);

  const config = ss.getSheetByName(s.CONFIG);
  if (config.getLastRow() < 2) {
    config.getRange(2, 1, 13, 3).setValues([
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
  ss.toast("Tournament system ready.", "GeoNederland Tournament", 6);
}

function setupTournamentPublicSpreadsheet() {
  setupTournamentSystem();
  const config = tournamentConfig_(), id = tournamentSpreadsheetId_(config["Public Spreadsheet ID"]);
  if (!id) throw Error("Enter the separate Public Spreadsheet ID on the Tournament tab first.");
  if (id === SpreadsheetApp.getActiveSpreadsheet().getId()) throw Error("Admin and Public must be separate spreadsheets.");
  const publicSs = SpreadsheetApp.openById(id), bracket = publicSs.getSheetByName("Bracket") || publicSs.insertSheet("Bracket"), schedule = publicSs.getSheetByName("Schedule") || publicSs.insertSheet("Schedule");
  bracket.setHiddenGridlines(true); schedule.setHiddenGridlines(true);
  tournamentSetConfig_("Public Bracket URL", "https://docs.google.com/spreadsheets/d/" + id + "/edit");
  syncTournamentPublicSpreadsheet();
  SpreadsheetApp.getActiveSpreadsheet().toast("Public bracket ready.", "GeoNederland Tournament", 6);
}

function syncTournamentPublicSpreadsheet() {
  const config = tournamentConfig_(), id = tournamentSpreadsheetId_(config["Public Spreadsheet ID"]);
  if (!id) throw Error("Public Spreadsheet ID is empty on the Tournament tab.");
  const publicSs = SpreadsheetApp.openById(id), bracket = publicSs.getSheetByName("Bracket") || publicSs.insertSheet("Bracket"), schedule = publicSs.getSheetByName("Schedule") || publicSs.insertSheet("Schedule"), matches = tournamentPublicMatches_();
  tournamentRenderPublicBracket_(bracket, config, matches);
  tournamentRenderPublicSchedule_(schedule, config, matches);
  SpreadsheetApp.flush();
}

function tournamentRenderPublicBracket_(sheet, config, matches) {
  sheet.clear(); sheet.setHiddenGridlines(true); sheet.setFrozenRows(3);
  sheet.getRange("A1:H1").merge().setValue(String(config["Tournament Name"] || "GeoNederland Tournament")).setBackground("#00182f").setFontColor("#ffffff").setFontSize(18).setFontWeight("bold");
  sheet.getRange("A2:H2").merge().setValue("Official bracket · " + String(config["Tournament Status"] || "Setup")).setBackground("#01397a").setFontColor("#ffffff").setFontWeight("bold");
  const headers = ["Round", "Match", "Player 1", "Player 2", "Score", "Status", "Broadcast", "Scheduled"];
  sheet.getRange(3, 1, 1, headers.length).setValues([headers]).setBackground("#00182f").setFontColor("#ffffff").setFontWeight("bold");
  const rows = matches.sort((a, b) => a.order - b.order).map((m) => [m.round, m.match_id, m.player1, m.player2, m.series_score, m.status, m.highlighted ? "Highlighted" : "", m.scheduled_at || ""]);
  if (rows.length) sheet.getRange(4, 1, rows.length, headers.length).setValues(rows);
  sheet.setConditionalFormatRules([
    SpreadsheetApp.newConditionalFormatRule().whenTextEqualTo("Complete").setBackground("#d9ead3").setRanges([sheet.getRange("F4:F")]).build(),
    SpreadsheetApp.newConditionalFormatRule().whenTextEqualTo("Live").setBackground("#f4cccc").setRanges([sheet.getRange("F4:F")]).build(),
    SpreadsheetApp.newConditionalFormatRule().whenTextEqualTo("Waiting for broadcast").setBackground("#fff2cc").setRanges([sheet.getRange("F4:F")]).build(),
    SpreadsheetApp.newConditionalFormatRule().whenTextEqualTo("Highlighted").setBackground("#d9d2e9").setRanges([sheet.getRange("G4:G")]).build(),
  ]);
  [120, 110, 180, 180, 90, 170, 120, 170].forEach((width, index) => sheet.setColumnWidth(index + 1, width));
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
  setupTournamentSystem();
  const ss = SpreadsheetApp.getActiveSpreadsheet(), playersSheet = ss.getSheetByName(TOURNAMENT.SHEETS.PLAYERS);
  const players = tournamentRows_(playersSheet)
    .filter((row) => tournamentBool_(row["Checked In"]) && String(row.Status || "").toLowerCase() !== "withdrawn")
    .sort((a, b) => Number(a.Seed || 999) - Number(b.Seed || 999));
  if (players.length !== 8) {
    throw Error("The practice bracket requires exactly 8 checked-in players in Tournament Players.");
  }
  const matchesSheet = ss.getSheetByName(TOURNAMENT.SHEETS.MATCHES);
  if (matchesSheet.getLastRow() > 1) {
    const choice = SpreadsheetApp.getUi().alert(
      "Replace practice bracket?",
      "Existing tournament matches will be cleared. Player and game data will remain.",
      SpreadsheetApp.getUi().ButtonSet.YES_NO,
    );
    if (choice !== SpreadsheetApp.getUi().Button.YES) return;
    matchesSheet.getRange(2, 1, matchesSheet.getLastRow() - 1, matchesSheet.getLastColumn()).clearContent();
  }

  const config = tournamentConfig_(), bestOf = Number(config["Default Best Of"] || 3);
  const presets = [config["Preset 1"] || "", config["Preset 2"] || "", config["Preset 3"] || ""];
  const bySeed = Object.fromEntries(players.map((p) => [Number(p.Seed), String(p.Player)]));
  const pairings = [[1, 8], [4, 5], [2, 7], [3, 6]];
  const rows = pairings.map((pair, index) => tournamentMatchRow_({
    id: "PT-QF" + (index + 1), round: "Quarterfinal", order: index + 1,
    player1: bySeed[pair[0]], player2: bySeed[pair[1]], bestOf, presets,
    next: index < 2 ? "PT-SF1" : "PT-SF2", slot: index % 2 ? 2 : 1,
  }));
  rows.push(tournamentMatchRow_({id: "PT-SF1", round: "Semifinal", order: 5, bestOf, presets, next: "PT-F", slot: 1}));
  rows.push(tournamentMatchRow_({id: "PT-SF2", round: "Semifinal", order: 6, bestOf, presets, next: "PT-F", slot: 2}));
  rows.push(tournamentMatchRow_({id: "PT-F", round: "Final", order: 7, bestOf, presets, highlighted: true}));
  matchesSheet.getRange(2, 1, rows.length, TOURNAMENT.HEADERS.MATCHES.length).setValues(rows);
  tournamentFormat_(ss);
  tournamentLog_("sheet", "generate_bracket", "", "Generated 8-player practice bracket");
  const publicId = tournamentSpreadsheetId_(config["Public Spreadsheet ID"]);
  if (publicId) syncTournamentPublicSpreadsheet();
  ss.toast("Practice bracket generated.", "GeoNederland Tournament", 6);
}

function tournamentMatchRow_(input) {
  const status = input.player1 && input.player2 ? "Waiting for players" : "Waiting for opponent";
  return [
    input.id, input.round, input.order, input.player1 || "TBD", input.player2 || "TBD",
    input.bestOf || 3, input.presets[0] || "", input.presets[1] || "", input.presets[2] || "",
    Boolean(input.highlighted), false, false, false, status, "", "0-0", "",
    input.next || "", input.slot || "", "", "", "", new Date(),
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
    sheet.setFrozenRows(1).setHiddenGridlines(true);
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
  return sheet.getRange(2, 1, sheet.getLastRow() - 1, sheet.getLastColumn()).getValues().map((values, index) => {
    const row = {__row: index + 2};
    headers.forEach((header, col) => row[header] = values[col]);
    return row;
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
    if (action === "bracket") return tournamentJson_({ok: true, config: tournamentConfig_(), matches: tournamentPublicMatches_()});
    if (action === "match") return tournamentJson_({ok: true, match: tournamentMatchForUser_(e.parameter.discord_user_id, e.parameter.discord_name, e.parameter.discord_display_name)});
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
  return tournamentRows_(sheet).map(tournamentPublicMatch_);
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

function tournamentDateIso_(value) {
  return value instanceof Date && !Number.isNaN(value.getTime()) ? value.toISOString() : String(value || "");
}

function tournamentPlayerByDiscord_(discordUserId, discordName, discordDisplayName) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TOURNAMENT.SHEETS.PLAYERS);
  const id = String(discordUserId || "").trim(), names = [discordName, discordDisplayName]
    .map((value) => String(value || "").trim().replace(/^@/, "").toLowerCase()).filter(Boolean);
  return tournamentRows_(sheet).find((row) => {
    const rowId = String(row["Discord User ID"] || "").trim(), rowName = String(row.Discord || "").trim().replace(/^@/, "").toLowerCase();
    return (id && rowId === id) || (rowName && names.includes(rowName));
  }) || null;
}

function tournamentMatchForUser_(discordUserId, discordName, discordDisplayName) {
  const player = tournamentPlayerByDiscord_(discordUserId, discordName, discordDisplayName);
  if (!player) return null;
  const matches = tournamentRows_(SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TOURNAMENT.SHEETS.MATCHES));
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
  const config = tournamentConfig_();
  if (String(config["Registration Status"] || "Closed").toLowerCase() !== "open") throw Error("Tournament registration is closed.");
  const identity = tournamentRegistrationIdentity_(payload), player = String(payload.player || "").trim();
  const country = String(payload.country || "").trim().toUpperCase(), geoId = tournamentGeoGuessrUserId_(payload.geoguessr_profile);
  if (player.length < 2 || player.length > 40) throw Error("Player name must contain 2 to 40 characters.");
  if (!["NL", "BE", "LU"].includes(country)) throw Error("Country must be NL, BE or LU.");
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TOURNAMENT.SHEETS.PLAYERS), rows = tournamentRows_(sheet);
  const own = rows.find((row) => String(row["Discord User ID"] || "") === identity.discordId);
  const conflict = rows.find((row) => String(row["Discord User ID"] || "") !== identity.discordId && (
    String(row["GeoGuessr User ID"] || "").toLowerCase() === geoId.toLowerCase() || String(row.Player || "").toLowerCase() === player.toLowerCase()
  ));
  if (conflict) throw Error("That GeoGuessr account or player name is already registered.");
  if (!own) {
    const maximum = Number(config["Maximum Players"] || 32);
    if (rows.filter((row) => !["Withdrawn", "Disqualified"].includes(String(row.Status))).length >= maximum) throw Error("Tournament registration is full.");
  }
  const now = new Date(), values = [own ? own.Seed : "", player, geoId, identity.discordName, identity.discordId, country,
    "Registered", false, own && own["Registered At"] || now, "", now, own && own.Notes || ""];
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
  const match = tournamentRows_(sheet).find((row) => String(row["Match ID"]) === String(matchId || ""));
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
    if (tournamentSpreadsheetId_(tournamentConfig_()["Public Spreadsheet ID"])) syncTournamentPublicSpreadsheet();
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
  tournamentRequireParticipant_(match, discordUserId, discordName, discordDisplayName);
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
  const existing = tournamentRows_(gamesSheet).filter((row) => String(row["Match ID"]) === String(match["Match ID"]));
  const gameNumber = existing.length + 1;
  if (existing.some((row) => String(row["Result URL"]) === value)) throw Error("This result link has already been submitted.");
  const mode = ["Moving", "No Move", "NMPZ"][Math.min(gameNumber - 1, 2)] || "Tiebreak";
  gamesSheet.appendRow([new Date(), match["Match ID"], gameNumber, mode, value, String(discordUserId), "", "", "", "Pending review", ""]);
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
  if (sheet) sheet.appendRow([new Date(), String(actor || ""), action, matchId || "", details || ""]);
}
