import json
import unittest
from unittest.mock import Mock

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from league_bot import broadcast
from league_bot.broadcast import (
    BroadcastData,
    bracket_feed,
    featured_match,
    match_feed,
    participants_feed,
    schedule_feed,
    standings_feed,
    to_csv,
    to_xml,
    tournament_feed,
)


def tournament():
    return {
        "id": "nk27-oq1",
        "name": "NK 2027 Open Qualifier 1",
        "status": "Live",
        "phase": "live",
        "type": "Single Elimination",
        "default_best_of": 3,
        "participant_count": 4,
        "participants": [
            {"seed": 1, "player": "Trekk", "country": "NL", "avatar_url": "https://www.geoguessr.com/images/a.png"},
            {"seed": 2, "player": "Matedu", "country": "BE", "avatar_url": ""},
            {"seed": 3, "player": "Lux", "country": "LU", "avatar_url": "javascript:alert(1)"},
            {"seed": 4, "player": "Kees", "country": "NL", "avatar_url": ""},
        ],
        "rounds": ["Semifinal", "Final"],
        "placements": [],
        "matches": [
            {"match_id": "OQ1-R1-M1", "round": "Semifinal", "order": 1, "player1": "Trekk", "player2": "Kees",
             "best_of": 3, "highlighted": False, "status": "Complete", "series_score": "2-0", "winner": "Trekk",
             "scheduled_at": "2026-12-12T18:00:00.000Z", "party_url": "https://www.geoguessr.com/party/secret"},
            {"match_id": "OQ1-R1-M2", "round": "Semifinal", "order": 2, "player1": "Matedu", "player2": "Lux",
             "best_of": 3, "highlighted": True, "status": "Live", "series_score": "1-1", "winner": "",
             "scheduled_at": "2026-12-12T18:30:00.000Z"},
            {"match_id": "OQ1-R2-M1", "round": "Final", "order": 3, "player1": "Trekk", "player2": "TBD",
             "best_of": 5, "highlighted": True, "status": "Waiting for players", "series_score": "0-0", "winner": "",
             "scheduled_at": "2026-12-12T20:00:00.000Z"},
        ],
    }


class RowBuilderTests(unittest.TestCase):
    def test_featured_prefers_live_highlighted_match(self):
        self.assertEqual(featured_match(tournament())["match_id"], "OQ1-R1-M2")

    def test_featured_explicit_match_wins(self):
        self.assertEqual(featured_match(tournament(), "oq1-r2-m1")["match_id"], "OQ1-R2-M1")

    def test_featured_falls_back_to_next_highlighted_then_open_match(self):
        data = tournament()
        data["matches"][1]["status"], data["matches"][1]["winner"] = "Complete", "Matedu"
        self.assertEqual(featured_match(data)["match_id"], "OQ1-R2-M1")
        for match in data["matches"]:
            match["highlighted"] = False
        self.assertEqual(featured_match(data)["match_id"], "OQ1-R2-M1")

    def test_match_row_is_flat_and_never_exposes_party_links(self):
        row = match_feed(tournament(), match_id="OQ1-R1-M1")[0]
        self.assertTrue(all(isinstance(value, str) for value in row.values()))
        self.assertNotIn("party", json.dumps(row))
        self.assertEqual((row["p1_score"], row["p2_score"], row["p1_winner"], row["p2_winner"]), ("2", "0", "1", ""))
        self.assertEqual(row["p1_flag"], "https://flagcdn.com/w160/nl.png")
        self.assertEqual(row["p1_avatar"], "https://www.geoguessr.com/images/a.png")
        self.assertEqual((row["scheduled"], row["scheduled_day"]), ("19:00", "za 12 dec"))  # Amsterdam time

    def test_unsafe_avatar_urls_are_dropped(self):
        row = match_feed(tournament())[0]
        self.assertEqual(row["p2_name"], "Lux")
        self.assertEqual(row["p2_avatar"], "")

    def test_first_to_follows_best_of(self):
        row = match_feed(tournament(), match_id="OQ1-R2-M1")[0]
        self.assertEqual((row["best_of"], row["first_to"], row["format"]), ("5", "3", "Best of 5"))

    def test_control_score_overrides_only_running_match(self):
        control = {"match_id": "OQ1-R1-M2", "p1_score": "2", "p2_score": "1"}
        self.assertEqual(match_feed(tournament(), control)[0]["series_score"], "2-1")
        control = {"match_id": "OQ1-R1-M1", "p1_score": "0", "p2_score": "2"}
        self.assertEqual(match_feed(tournament(), control)[0]["series_score"], "2-0")

    def test_empty_tournament_still_returns_one_row(self):
        rows = match_feed({"name": "Empty", "matches": []})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["p1_name"], "TBD")

    def test_bracket_feed_numbers_rounds_and_slots(self):
        rows = bracket_feed(tournament())
        self.assertEqual([(row["round_index"], row["slot"]) for row in rows], [("1", "1"), ("1", "2"), ("2", "1")])
        self.assertEqual(rows[0]["done"], "1")

    def test_schedule_lists_live_first_and_skips_finished(self):
        rows = schedule_feed(tournament())
        self.assertEqual([row["match_id"] for row in rows], ["OQ1-R1-M2", "OQ1-R2-M1"])

    def test_participants_and_tournament_feeds(self):
        people = participants_feed(tournament())
        self.assertEqual([row["seed"] for row in people], ["1", "2", "3", "4"])
        info = tournament_feed(tournament(), {"caster_1": "Anna", "ticker": "Welkom!"})[0]
        self.assertEqual((info["matches_done"], info["current_round"], info["caster_1"], info["ticker"]),
                         ("1", "Semifinal", "Anna", "Welkom!"))

    def test_standings_feed(self):
        rows = standings_feed([{"rank": "1", "player": "Trekk", "country": "NL", "points": "1234.0",
                                "weeks": "8", "moving": "1", "nm": "2", "nmpz": "3", "playoffs": "Q"}], 16)
        self.assertEqual((rows[0]["points"], rows[0]["flag"]), ("1,234", "https://flagcdn.com/w160/nl.png"))

    def test_csv_and_xml_escape_values(self):
        rows = [{"player": 'A & "B" <C>', "score": "1"}]
        self.assertIn('"A & ""B"" <C>"', to_csv(rows))
        self.assertIn("<player>A &amp; \"B\" &lt;C&gt;</player>", to_xml(rows))

    def test_control_validation(self):
        data = BroadcastData(Mock(), Mock(), cache_seconds=0)
        data.update_control({"p1_score": "2", "caster_1": "Anna\nB"})
        self.assertEqual(data.control["caster_1"], "Anna B")
        with self.assertRaises(ValueError):
            data.update_control({"p1_score": "two"})
        with self.assertRaises(ValueError):
            data.update_control({"match_id": "../x"})


class RouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        api = Mock()
        api.bracket.return_value = {"config": {"Tournament ID": "nk27-oq1"}}
        api.get.return_value = {"tournament": tournament()}
        sheet = Mock()
        sheet.standings.return_value = [{"rank": "1", "player": "Trekk", "country": "NL", "points": "10"}]
        self.api = api
        self.data = BroadcastData(sheet, api, cache_seconds=60)
        self.data.control_secret = "s" * 32
        app = web.Application()
        broadcast.setup_routes(app, self.data)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    async def test_json_feed_uses_active_tournament_and_cache(self):
        for _ in range(3):
            response = await self.client.get("/broadcast/feed/match.json")
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["Access-Control-Allow-Origin"], "*")
            rows = await response.json()
        self.assertEqual(rows[0]["match_id"], "OQ1-R1-M2")
        self.api.get.assert_called_once_with("public_tournament", tournament_id="nk27-oq1")

    async def test_csv_and_xml_feeds(self):
        response = await self.client.get("/broadcast/feed/schedule.csv")
        self.assertTrue((await response.text()).startswith("tournament,match_id"))
        response = await self.client.get("/broadcast/feed/standings.xml")
        self.assertIn("<player>Trekk</player>", await response.text())

    async def test_stale_data_stays_on_air_when_refresh_fails(self):
        await self.client.get("/broadcast/feed/match.json")
        self.data._tournaments["nk27-oq1"].loaded_at = 0
        self.api.get.side_effect = RuntimeError("Apps Script down")
        response = await self.client.get("/broadcast/feed/match.json")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers.get("X-Broadcast-Stale"), "1")

    async def test_first_failure_returns_503_without_details(self):
        self.api.get.side_effect = RuntimeError("secret=abc")
        response = await self.client.get("/broadcast/feed/match.json")
        self.assertEqual(response.status, 503)
        self.assertNotIn("abc", await response.text())

    async def test_unknown_feed_and_overlay(self):
        self.assertEqual((await self.client.get("/broadcast/feed/nope.json")).status, 404)
        self.assertEqual((await self.client.get("/broadcast/overlay/nope")).status, 404)
        self.assertEqual((await self.client.get("/broadcast/overlay/scorebug")).status, 200)
        self.assertEqual((await self.client.get("/broadcast/assets/overlay.js")).status, 200)

    async def test_control_requires_secret(self):
        response = await self.client.post("/broadcast/control", json={"caster_1": "Anna"})
        self.assertEqual(response.status, 403)
        response = await self.client.post("/broadcast/control", json={"match_id": "OQ1-R1-M2", "p1_score": "2", "p2_score": "1"},
                                          headers={"X-Broadcast-Secret": "s" * 32})
        self.assertEqual(response.status, 200)
        rows = await (await self.client.get("/broadcast/feed/match.json")).json()
        self.assertEqual(rows[0]["series_score"], "2-1")


if __name__ == "__main__":
    unittest.main()
