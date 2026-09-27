import unittest

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


if __name__ == "__main__":
    unittest.main()
