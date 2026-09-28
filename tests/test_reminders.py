import unittest
from unittest.mock import patch

from reminders.send import Config, ReminderError, build_payload, parse_players, resolve_players


class ReminderTests(unittest.TestCase):
    def test_test_payload_never_mentions_users_or_roles(self):
        payload = build_payload("test", 4, self.config(), [])

        self.assertIn("reminder system test", payload["content"])
        self.assertEqual(
            payload["allowed_mentions"],
            {"parse": [], "roles": [], "users": [], "replied_user": False},
        )

    def config(self) -> Config:
        return Config("token", "100", "200", "300", "https://example.com/sheet")

    def members(self):
        return [
            {"nick": "Billy Butcher", "user": {"id": "10", "username": "butcher", "global_name": "Billy"}},
            {"nick": None, "user": {"id": "11", "username": "Trekk", "global_name": None}},
        ]

    def test_resolves_username_or_server_nickname_case_insensitively(self):
        players = [
            {"player": "A", "discord": "@trekk", "missing": 2},
            {"player": "B", "discord": "billy butcher", "missing": 1},
        ]
        resolved = resolve_players(players, self.members())
        self.assertEqual([p["user_id"] for p in resolved], ["11", "10"])

    def test_ambiguous_name_aborts_before_sending(self):
        members = self.members() + [
            {"nick": "Trekk", "user": {"id": "12", "username": "other"}}
        ]
        with self.assertRaises(ReminderError):
            resolve_players([{"player": "Trekk", "discord": "Trekk"}], members)

    def test_sunday_payload_mentions_only_resolved_users(self):
        players = [{"player": "Trekk", "user_id": "11", "missing": 2}]
        payload = build_payload("sunday", 4, self.config(), players)
        self.assertIn("<@11>", payload["content"])
        self.assertIn("2 seed(s) remaining", payload["content"])
        self.assertEqual(payload["allowed_mentions"]["users"], ["11"])
        self.assertEqual(payload["allowed_mentions"]["roles"], [])

    def test_friday_payload_mentions_generic_role(self):
        payload = build_payload("friday", 4, self.config(), [])
        self.assertIn("<@&300>", payload["content"])
        self.assertEqual(payload["allowed_mentions"]["roles"], ["300"])

    @patch("reminders.send.PublicSheet")
    def test_recap_payload_uses_latest_completed_week(self, sheet_class):
        sheet_class.return_value.all_player_stats.return_value = [
            {"player": "Trekk", "weekly": ["100", "250"]},
            {"player": "Matedu", "weekly": ["200", "150"]},
        ]
        payload = build_payload("recap", 2, self.config(), [])
        self.assertIn("Week 2 recap", payload["content"])
        self.assertIn("Trekk", payload["content"])
        self.assertEqual(payload["allowed_mentions"]["users"], [])

    def test_parse_players_requires_list_of_objects(self):
        self.assertEqual(parse_players('[{"player":"A"}]')[0]["player"], "A")
        with self.assertRaises(ReminderError):
            parse_players('{"player":"A"}')


if __name__ == "__main__":
    unittest.main()
