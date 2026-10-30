import unittest

from publisher.tournament_export import (
    TournamentExportError,
    build_wikicode,
    match_date,
    wiki_text,
)


TOURNAMENT = {
    "id": "practice-1",
    "name": "ACNL Practice Cup",
    "bracket_size": 4,
    "winner": "Trekk",
    "participants": [
        {"seed": 2, "player": "Matedu", "country": "BE"},
        {"seed": 1, "player": "Trekk", "country": "NL"},
        {"seed": 3, "player": "North", "country": "NL"},
        {"seed": 4, "player": "Jasper", "country": "BE"},
    ],
    "matches": [
        {
            "order": 1,
            "round": "Semifinals",
            "player1": "Trekk",
            "player2": "Jasper",
            "series_score": "2-0",
            "winner": "Trekk",
            "status": "Complete",
            "scheduled_at": "2026-12-12T18:00:00.000Z",
        },
        {
            "order": 2,
            "round": "Semifinals",
            "player1": "Matedu",
            "player2": "North",
            "series_score": "2-1",
            "winner": "Matedu",
            "status": "Complete",
        },
        {
            "order": 3,
            "round": "Final",
            "player1": "Trekk",
            "player2": "Matedu",
            "series_score": "3-1",
            "winner": "Trekk",
            "status": "Complete",
        },
    ],
}


class TournamentExportTests(unittest.TestCase):
    def test_generates_participants_and_real_liquipedia_bracket(self):
        text = build_wikicode(TOURNAMENT)
        self.assertTrue(text.startswith("<!-- LOWLANDS_LEAGUE_MANAGED_TEST_PAGE -->"))
        self.assertIn("{{ParticipantTable|title=Participants", text)
        self.assertLess(text.index("1Opponent|Trekk"), text.index("1Opponent|Matedu"))
        self.assertIn("{{Bracket|Bracket/4|id=practice-1", text)
        self.assertIn("|R1M2={{Match", text)
        self.assertIn("|R2M1={{Match", text)
        self.assertIn("SoloOpponent|Trekk|flag=nl|score=3", text)
        self.assertIn("|finished=true", text)
        self.assertIn("{{player|Trekk}}", text)

    def test_rejects_non_single_elimination_match_count(self):
        invalid = dict(TOURNAMENT, matches=TOURNAMENT["matches"] + [{}])
        with self.assertRaisesRegex(TournamentExportError, "more matches"):
            build_wikicode(invalid)

    def test_rejects_unsupported_bracket_size(self):
        with self.assertRaisesRegex(TournamentExportError, "Unsupported bracket size"):
            build_wikicode(dict(TOURNAMENT, bracket_size=3))

    def test_escapes_wikicode_control_characters(self):
        self.assertEqual(wiki_text("A|B{{C}}"), "A-B(C)")

    def test_formats_amsterdam_standard_time(self):
        self.assertEqual(match_date("2026-12-12T18:00:00Z"), "2026-12-12 19:00 {{Abbr/CET}}")


if __name__ == "__main__":
    unittest.main()

