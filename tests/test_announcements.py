import unittest
from datetime import datetime, timedelta, timezone

from league_bot.announcements import announcements, baseline, next_opponent, results_text

NOW = datetime(2026, 11, 5, 19, 0, tzinfo=timezone.utc)


def match(match_id, one, two, **extra):
    return {"match_id": match_id, "player1": one, "player2": two, "round": "Semifinal", "best_of": 3, **extra}


class AnnouncementTests(unittest.TestCase):
    def test_baseline_never_repeats_what_already_happened(self):
        matches = [
            match("M1", "Anna", "Bas", highlighted=True, admin_released=True, status="Live"),
            match("M2", "Cor", "Eva", status="Complete", winner="Eva", series_score="1-2"),
        ]
        messages, _ = announcements(baseline(matches, NOW), matches, NOW)
        self.assertEqual(messages, [])

    def test_stream_result_and_reminder_each_once(self):
        start = (NOW + timedelta(minutes=10)).isoformat()
        before = [
            match("M1", "Anna", "Bas", highlighted=True, status="Waiting for broadcast"),
            match("M2", "Cor", "Eva", status="Live", series_score="1-1"),
            match("M3", "Dirk", "Fien", status="Waiting for players", scheduled_at=(NOW + timedelta(hours=2)).isoformat()),
            match("F", "Anna", "TBD", round="Final"),
        ]
        state = baseline(before, NOW)
        after = [
            match("M1", "Anna", "Bas", highlighted=True, admin_released=True, status="Ready to start", stream_url="https://twitch.tv/geonederland"),
            match("M2", "Cor", "Eva", status="Complete", winner="Eva", series_score="1-2"),
            match("M3", "Dirk", "Fien", status="Waiting for players", scheduled_at=start),
            match("F", "Anna", "Eva", round="Final"),
        ]
        messages, state = announcements(state, after, NOW)
        self.assertEqual(len(messages), 3)
        self.assertIn("**Now on stream:** Anna vs Bas (Semifinal, best of 3)", messages[0])
        self.assertIn("<https://twitch.tv/geonederland>", messages[0])
        self.assertEqual(messages[1], "**Result:** **Eva** beats Cor 2-1 (Semifinal). Next up for Eva: Anna.")
        self.assertTrue(messages[2].startswith("**Starting soon:** Dirk vs Fien"))
        again, _ = announcements(state, after, NOW)
        self.assertEqual(again, [], "every moment only once")

    def test_no_mentions_or_party_links(self):
        after = [match("M1", "@everyone", "Bas", highlighted=True, admin_released=True, party_url="https://www.geoguessr.com/party/x")]
        messages, _ = announcements({}, after, NOW)
        self.assertNotIn("geoguessr.com/party", "".join(messages))

    def test_next_opponent_and_results_text(self):
        matches = [
            match("M1", "Anna", "Bas", status="Complete", winner="Anna", series_score="2-0"),
            match("F", "Anna", "TBD"),
        ]
        self.assertEqual(next_opponent(matches, "Anna", "M1"), "")
        self.assertEqual(results_text(matches, "Cup"), "**Cup**\nSemifinal: **Anna** 2-0 Bas")
        self.assertEqual(results_text([]), "No completed matches yet.")


if __name__ == "__main__":
    unittest.main()
