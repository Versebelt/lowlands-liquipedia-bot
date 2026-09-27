import unittest
from datetime import date, datetime

from reminders.send import Config, ReminderError, build_message, current_week, resolve_kind


class ReminderTests(unittest.TestCase):
    def config(self, players=()) -> Config:
        return Config(
            webhook_url="https://discord.com/api/webhooks/test/test",
            generic_role_id="111",
            player_role_ids=tuple(players),
            season_start=date(2026, 9, 7),
            season_weeks=10,
            sheet_url="https://example.com/sheet",
        )

    def test_week_number(self):
        self.assertEqual(current_week(date(2026, 9, 7), date(2026, 9, 7), 10), 1)
        self.assertEqual(current_week(date(2026, 9, 27), date(2026, 9, 7), 10), 3)
        self.assertIsNone(current_week(date(2026, 11, 16), date(2026, 9, 7), 10))

    def test_auto_kind_uses_weekday(self):
        self.assertEqual(resolve_kind("auto", datetime(2026, 9, 28, 9)), "open")
        self.assertEqual(resolve_kind("auto", datetime(2026, 10, 2, 20)), "friday")
        self.assertEqual(resolve_kind("auto", datetime(2026, 10, 4, 10)), "sunday")

    def test_sunday_mentions_each_player_role(self):
        content, allowed = build_message("sunday", 4, self.config(("222", "333")))
        self.assertIn("<@&222> <@&333>", content)
        self.assertEqual(allowed, ("222", "333"))

    def test_sunday_refuses_empty_player_list(self):
        with self.assertRaises(ReminderError):
            build_message("sunday", 4, self.config())


if __name__ == "__main__":
    unittest.main()
