import unittest
import json

from league_bot.sheets import PublicSheet, display_number, first_value, normalized


class SheetTests(unittest.TestCase):
    def test_helpers(self):
        self.assertEqual(normalized("  TrEkk "), "trekk")
        self.assertEqual(display_number("24,950"), "24,950")
        self.assertEqual(first_value({"League Points": "42"}, ("Points", "League Points")), "42")

    def test_player_lookup_prefers_exact_and_requires_unique_partial(self):
        sheet = PublicSheet()
        sheet.standings = lambda: [
            {"player": "Trekk", "rank": "1"},
            {"player": "TrekkGeo", "rank": "2"},
        ]
        self.assertEqual(sheet.player("Trekk")["rank"], "1")
        self.assertIsNone(sheet.player("Tre"))

    def test_mode_leaderboard_sorts_descending(self):
        sheet = PublicSheet()
        sheet.standings = lambda: [
            {"player": "A", "moving": "900", "nm": "1", "nmpz": "1"},
            {"player": "B", "moving": "1200", "nm": "1", "nmpz": "1"},
        ]
        self.assertEqual(sheet.mode_leaderboard("Moving")[0]["player"], "B")
        self.assertEqual(sheet.mode_leaderboard("invalid"), [])

    def test_player_stats_reads_weekly_form(self):
        sheet = PublicSheet()
        sheet.profile_urls = lambda: {"trekk": "https://www.geoguessr.com/user/123"}
        sheet.rows = lambda tab: [
            {
                "Player Stats Rank": "1",
                "Player": "Trekk",
                "League Points": "4.000,0",
                "Week 1": "1.300,0",
                "Week 2": "1.400,0",
            }
        ]
        row = sheet.player_stats("trekk")
        self.assertEqual(row["rank"], "1")
        self.assertEqual(row["weekly"][:2], ["1.300,0", "1.400,0"])
        self.assertEqual(row["profile_url"], "https://www.geoguessr.com/user/123")
        self.assertIn("fives", row)

    def test_tab_url_uses_discovered_gid(self):
        sheet = PublicSheet()
        sheet.tab_gids = lambda: {"Week 4": "911011305"}
        self.assertEqual(
            sheet.tab_url("Week 4"),
            "https://docs.google.com/spreadsheets/d/"
            + sheet.spreadsheet_id
            + "/edit?gid=911011305#gid=911011305",
        )

    def test_profile_prefers_full_body_avatar(self):
        sheet = PublicSheet()
        sheet.profile_urls = lambda: {"trekk": "https://www.geoguessr.com/user/123"}
        sheet._request = lambda url: json.dumps(
            {"fullBodyPin": "pin/full-body.png", "pin": {"url": "pin/profile.png"}}
        ).encode()
        profile = sheet.profile("Trekk")
        self.assertIn("pin/full-body.png", profile["avatar"])
        self.assertNotIn("pin/profile.png", profile["avatar"])


if __name__ == "__main__":
    unittest.main()
