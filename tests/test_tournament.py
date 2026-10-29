import unittest
from unittest.mock import Mock, patch

from league_bot.tournament import (
    TournamentApi,
    TournamentError,
    tournament_bracket_embed,
    tournament_match_embed,
    tournament_registration_embed,
    tournament_rules_embed,
)


MATCH = {
    "match_id": "PT-QF1",
    "round": "Quarterfinal",
    "order": 1,
    "player1": "Trekk",
    "player2": "Matedu",
    "best_of": 3,
    "presets": ["https://www.geoguessr.com/party/preset/example", "", ""],
    "highlighted": True,
    "player1_ready": True,
    "player2_ready": False,
    "admin_released": False,
    "status": "Waiting for broadcast",
    "series_score": "0-0",
}


class TournamentTests(unittest.TestCase):
    def test_registration_embed_shows_sheet_status(self):
        embed = tournament_registration_embed(
            {"player": "Trekk", "country": "NL", "status": "Checked In", "checked_in": True, "geoguessr_user_id": "abc123"},
            "checkin",
        )
        self.assertEqual(embed.title, "Check-in confirmed")
        self.assertIn("Trekk", embed.description)
        self.assertEqual(embed.fields[0].value, "Checked In")

    def test_unconfigured_api_fails_without_network_request(self):
        with self.assertRaisesRegex(TournamentError, "not configured"):
            TournamentApi().bracket()

    @patch("league_bot.tournament.requests.post")
    def test_api_posts_authenticated_tournament_action(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"ok": True, "data": MATCH}
        post.return_value = response

        result = TournamentApi("https://script.google.com/macros/s/example/exec", "x" * 32).post(
            "ready", match_id="PT-QF1", discord_user_id="123"
        )

        self.assertEqual(result["match_id"], "PT-QF1")
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["secret"], "x" * 32)
        self.assertEqual(body["action"], "ready")

    def test_match_embed_shows_broadcast_lock_and_readiness(self):
        embed = tournament_match_embed(MATCH, rules_url="https://example.com/rules")
        self.assertIn("Trekk", embed.description)
        self.assertIn("Not ready", embed.fields[0].value)
        host_field = next(field for field in embed.fields if field.name == "Party host")
        self.assertIn("Trekk", host_field.value)
        self.assertIn("bovenste/linker speler", host_field.value)
        self.assertTrue(any(field.name == "Reglement" for field in embed.fields))
        self.assertTrue(any("Waiting for admin start permission" in field.value for field in embed.fields))

    def test_bracket_embed_groups_rounds_and_marks_highlighted_match(self):
        embed = tournament_bracket_embed(
            {"config": {"Tournament Name": "Practice Cup"}, "matches": [MATCH]}
        )
        self.assertEqual(embed.title, "Practice Cup")
        self.assertEqual(embed.fields[0].name, "Quarterfinal")
        self.assertIn("📺", embed.fields[0].value)

    def test_rules_embed_links_current_regulations(self):
        embed = tournament_rules_embed(
            {"config": {"Tournament Name": "Practice Cup", "Rules URL": "https://example.com/rules"}}
        )
        self.assertEqual(embed.url, "https://example.com/rules")
        self.assertIn("volledige toernooireglement", embed.description)


if __name__ == "__main__":
    unittest.main()
