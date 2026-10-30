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
    "liquipedia_bracket_id": "qFhEInlFiO",
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
        self.assertIn("{{Bracket|Bracket/4|id=qFhEInlFiO", text)
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

    def test_rejects_missing_persistent_bracket_id(self):
        with self.assertRaisesRegex(TournamentExportError, "persistent Liquipedia bracket ID"):
            build_wikicode(dict(TOURNAMENT, liquipedia_bracket_id=""))

    def test_accepts_letters_and_rejects_wrong_length_or_symbols(self):
        self.assertIn("id=qFhEInlFiO", build_wikicode(TOURNAMENT))
        with self.assertRaisesRegex(TournamentExportError, "persistent Liquipedia bracket ID"):
            build_wikicode(dict(TOURNAMENT, liquipedia_bracket_id="abc123456789"))
        with self.assertRaisesRegex(TournamentExportError, "persistent Liquipedia bracket ID"):
            build_wikicode(dict(TOURNAMENT, liquipedia_bracket_id="abc123456"))
        with self.assertRaisesRegex(TournamentExportError, "persistent Liquipedia bracket ID"):
            build_wikicode(dict(TOURNAMENT, liquipedia_bracket_id="abc123456!"))

    def test_escapes_wikicode_control_characters(self):
        self.assertEqual(wiki_text("A|B{{C}}"), "A-B(C)")

    def test_escapes_links_comments_and_named_parameters(self):
        escaped = wiki_text("a=b <!-- [[x]] ~~~~ __NOTOC__ &")
        for unsafe in ("=", "<", "[[", "~~~", "__"):
            self.assertNotIn(unsafe, escaped)
        self.assertIn("&amp;", escaped)

    def test_bracket_slot_comes_from_match_id_not_row_order(self):
        matches = [dict(match) for match in TOURNAMENT["matches"]]
        for match, match_id in zip(matches, ["t-R1-M2", "t-R1-M1", "t-R2-M1"]):
            match["match_id"] = match_id
        text = build_wikicode(dict(TOURNAMENT, matches=matches))
        self.assertIn("|R1M2={{Match\n    |opponent1={{SoloOpponent|Trekk", text)
        self.assertIn("|R1M1={{Match\n    |opponent1={{SoloOpponent|Matedu", text)

    def test_rejects_duplicate_or_impossible_slots(self):
        matches = [dict(match, match_id="t-R1-M1") for match in TOURNAMENT["matches"][:2]]
        with self.assertRaisesRegex(TournamentExportError, "share bracket slot"):
            build_wikicode(dict(TOURNAMENT, matches=matches))
        with self.assertRaisesRegex(TournamentExportError, "does not fit"):
            build_wikicode(dict(TOURNAMENT, matches=[dict(TOURNAMENT["matches"][0], match_id="t-R1-M3")]))

    def test_bye_is_a_walkover_for_the_other_player(self):
        bye = dict(TOURNAMENT["matches"][0], player2="BYE", series_score="0-0")
        text = build_wikicode(dict(TOURNAMENT, matches=[bye]))
        self.assertIn("{{LiteralOpponent|BYE}}", text)
        self.assertIn("|winner=1", text)

    def test_no_displaytitle_on_test_page(self):
        self.assertNotIn("DISPLAYTITLE", build_wikicode(TOURNAMENT))

    def test_formats_amsterdam_standard_time(self):
        self.assertEqual(match_date("2026-12-12T18:00:00Z"), "2026-12-12 19:00 {{Abbr/CET}}")


if __name__ == "__main__":
    unittest.main()

