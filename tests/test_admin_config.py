import unittest

from league_bot.admin_config import AdminConfig, decode_topic, encode_topic, valid_time


class AdminConfigTests(unittest.TestCase):
    def test_topic_round_trip(self):
        expected = AdminConfig(
            announcement_channel_id="123",
            reminder_role_id="456",
            reminders_enabled=False,
        )
        self.assertEqual(decode_topic(encode_topic(expected)), expected)

    def test_invalid_topic_is_ignored(self):
        self.assertIsNone(decode_topic("ordinary channel topic"))
        self.assertIsNone(decode_topic("LLBOT_CONFIG_V1:not-valid-base64"))

    def test_time_validation(self):
        self.assertTrue(valid_time("09:00"))
        self.assertTrue(valid_time("23:59"))
        self.assertFalse(valid_time("24:00"))
        self.assertFalse(valid_time("nine"))


if __name__ == "__main__":
    unittest.main()
