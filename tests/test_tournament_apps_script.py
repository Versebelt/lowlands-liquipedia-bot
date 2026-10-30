import pathlib
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

    def test_avatar_cache_and_batching_are_enabled(self):
        self.assertIn("UrlFetchApp.fetchAll", SOURCE)
        self.assertIn("CacheService.getScriptCache", SOURCE)
        self.assertIn("21600", SOURCE)


if __name__ == "__main__":
    unittest.main()

