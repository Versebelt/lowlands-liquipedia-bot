import pathlib
import re
import unittest


SOURCE = (
    pathlib.Path(__file__).parents[1] / "apps-script" / "Tournament.gs"
).read_text(encoding="utf-8")


class TournamentAppsScriptContractTests(unittest.TestCase):
    def test_public_contract_contains_only_geoguessr_avatar_fields(self):
        self.assertIn("avatar_url:", SOURCE)
        self.assertIn("player1_avatar_url:", SOURCE)
        self.assertIn("player2_avatar_url:", SOURCE)
        public_section = SOURCE.split("/* Strict public allowlist", 1)[1].split(
            "function tournamentDateIso_", 1
        )[0]
        self.assertNotIn("Discord User ID", public_section)
        self.assertNotIn("discord_avatar", public_section.lower())

    def test_avatar_source_priority_matches_discord_bot(self):
        expected = (
            "data.fullBodyPin || (data.avatar || {}).fullBodyPath || "
            "(data.pin || {}).url || data.customImage"
        )
        self.assertIn(expected, SOURCE)
        self.assertIn("resize:fill:512:512/gravity:no:0:0/plain/", SOURCE)

    def test_liquipedia_bracket_ids_have_ten_characters(self):
        self.assertIn("/^[A-Za-z0-9]{10}$/", SOURCE)
        self.assertIn("Array.from({length: 10}", SOURCE)
        self.assertNotIn("Array.from({length: 12}", SOURCE)
        ensure = SOURCE.split("function tournamentEnsureLiquipediaBracketIds_", 1)[1].split("\n}", 1)[0]
        self.assertIn("tournamentValidLiquipediaBracketId_", ensure)

    def test_status_changes_never_roll_back_a_started_match(self):
        for name in ("tournamentSetReady_", "tournamentRelease_", "tournamentHighlight_", "tournamentResolve_"):
            body = SOURCE.split(f"function {name}(", 1)[1].split("\n}", 1)[0]
            self.assertIn("tournamentBeforeStart_", body, name)
        for name in ("tournamentSetParty_", "tournamentSubmitResult_"):
            body = SOURCE.split(f"function {name}(", 1)[1].split("\n}", 1)[0]
            self.assertIn("tournamentClosed_(match)", body, name)

    def test_byes_advance_when_the_bracket_is_generated(self):
        generate = SOURCE.split("function tournamentBuildBracket_(", 1)[1].split("function tournamentGenerateOfficialBracket_", 1)[0]
        self.assertIn("tournamentAdvanceByes_(rows)", generate)

    def test_public_schedule_shows_amsterdam_time(self):
        self.assertIn('"Europe/Amsterdam"', SOURCE)
        self.assertIn("tournamentAmsterdamTime_(m.scheduled_at)", SOURCE)

    def test_every_called_tournament_helper_is_defined(self):
        defined = set(re.findall(r"function (tournament\w+_)\(", SOURCE))
        called = set(re.findall(r"\b(tournament\w+_)\(", SOURCE))
        self.assertEqual(called - defined, set())

    def test_avatar_cache_and_batching_are_enabled(self):
        self.assertIn("UrlFetchApp.fetchAll", SOURCE)
        self.assertIn("CacheService.getScriptCache", SOURCE)
        self.assertIn("21600", SOURCE)

    def test_checkin_window_is_enforced_server_side(self):
        self.assertIn('"Check-in Opens At", "Check-in Closes At"', SOURCE)
        checkin = SOURCE.split("function tournamentCheckIn_(", 1)[1].split("\n}", 1)[0]
        self.assertIn("tournamentCheckInWindow_", checkin)
        self.assertIn('window.state === "too_early"', checkin)
        self.assertIn('window.state === "closed"', checkin)

    def test_preview_bracket_is_separate_from_official_matches(self):
        preview = SOURCE.split("function generateTournamentPreviewBracket(", 1)[1].split(
            "function tournamentMatchValuesToPublic_", 1
        )[0]
        self.assertIn('getSheetByName("Proefbracket")', preview)
        self.assertIn('"Bracket Label": "PROEFBRACKET — NIET DEFINITIEF"', preview)
        self.assertIn("tournamentRegisteredPlayers_()", preview)
        self.assertNotIn("deleteRow", preview)
        self.assertNotIn("TOURNAMENT.SHEETS.MATCHES", preview)

    def test_automatic_bracket_never_replaces_existing_matches(self):
        generate = SOURCE.split("function tournamentGenerateOfficialBracket_(", 1)[1].split(
            "// A player drawn", 1
        )[0]
        self.assertIn("oldMatches.length && !settings.replaceExisting", generate)
        self.assertIn('"Auto-generate Official Bracket"', SOURCE)
        self.assertIn("everyMinutes(5)", SOURCE)

    def test_new_rows_skip_empty_checkbox_rows(self):
        # Checkbox columns make getLastRow() return the bottom of the sheet.
        self.assertNotIn("getLastRow() + 1", SOURCE)
        for name in ("createTournament", "tournamentEnsureInitialTournament_", "tournamentRegister_"):
            body = SOURCE.split(f"function {name}(", 1)[1].split("\n}", 1)[0]
            self.assertIn("tournamentNextRow_(", body, name)


if __name__ == "__main__":
    unittest.main()

