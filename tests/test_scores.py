import importlib.util
import json
import sys
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
import fakeredis

path = Path(__file__).resolve().parents[1] / "api" / "scores.py"
spec = importlib.util.spec_from_file_location("scores", path)
scores = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scores)

import random
def game(score, wrong=0, reaction=1200, jitter=400, seed=1):
    """Telemetry of a plausible 60-second game ending on `score`: score+wrong correct taps, `wrong` misses (each -1), human-ish timing."""
    rng = random.Random(seed)
    rounds, taps, t, rnd = [], [], 0, 1
    correct = score + wrong
    deals = [rng.sample(range(8), 3) for _ in range(correct + 1)]
    rounds.append({"r": 1, "t": 0, "cards": deals[0], "answer": "star"})
    misses = set(rng.sample(range(1, correct), wrong)) if wrong else set()
    for i in range(correct):
        if i in misses:
            t += 500; taps.append({"t": t, "r": rnd, "s": "dog", "ok": False})
        t += reaction + rng.randint(-jitter, jitter)
        taps.append({"t": t, "r": rnd, "s": "star", "ok": True, "card": 0, "slot": 2})
        rnd += 1; rounds.append({"r": rnd, "t": t + 10, "cards": deals[i + 1], "answer": "star"})
    return {"rounds": rounds, "taps": taps, "client": {"app": "ios", "version": "1.1.0"}}

class ScoresTests(unittest.TestCase):
    def setUp(self):
        self.redis = fakeredis.FakeRedis(decode_responses=True)
        self.mock = patch.object(scores, "redis_cmd", self.redis.execute_command)
        self.mock.start()
        self.addCleanup(self.mock.stop)
    def entry(self, **overrides):
        d = dict(id=str(uuid.uuid4()), playerId=str(uuid.uuid4()), avatar="10-13",
                 score=12, completedAt=time.time(), durationSeconds=60, rules=scores.RULES)
        d.update(overrides)
        if d["rules"].startswith("ios-") and "taps" not in d:
            d.update(game(d["score"]))
        return d
    def test_ios_requires_telemetry_that_replays_to_the_score(self):
        ios = lambda **k: self.entry(rules="ios-easy-60-v1", **k)
        self.assertEqual(scores.save_score(ios(), "test")[0], 200)
        honest = game(9, wrong=2)
        self.assertEqual(scores.save_score(ios(score=9, **honest), "test")[0], 200)
        bad = [ios(taps=None, rounds=None),                       # no telemetry at all
               ios(score=13, **game(12)),                         # score higher than the taps show
               ios(score=9, **game(9, reaction=200, jitter=20)),   # every tap ~200 ms after the deal
               ios(score=9, **game(9, jitter=0)),                 # metronomic reactions
               ios(score=45, **game(45, reaction=1500))]          # 45 rounds at 1.5 s overrun the 60 s clock
        for d in bad:
            status, body = scores.save_score(d, "test")
            self.assertEqual(status, 422, d.get("score"))
            self.assertFalse(body["accepted"])
        self.assertEqual(self.redis.hlen("mobee:solo:ios:easy:v1:rejected"), len(bad))
        self.assertEqual(len(scores.tv_board("ios")), 2)
    def test_tvos_without_telemetry_still_accepted(self):
        self.assertEqual(scores.save_score(self.entry(), "test")[0], 200)
    def test_retry_is_idempotent_and_player_best_is_retained(self):
        d = self.entry()
        self.assertTrue(scores.save_score(d, "test")[1]["accepted"])
        self.assertTrue(scores.save_score(d, "test")[1]["duplicate"])
        scores.save_score(self.entry(playerId=d["playerId"], score=4), "test")
        self.assertEqual(scores.tv_board()[0]["score"],12)
        self.assertEqual(self.redis.hlen(scores.PREFIX + ":games"),2)
        scores.save_score(self.entry(playerId=d["playerId"],score=15),"test")
        self.assertEqual(scores.tv_board()[0]["score"],15)
    def test_top_ten_ties_and_no_duplicate_players(self):
        first = self.entry(score=20)
        scores.save_score(first,"test")
        for i in range(15): scores.save_score(self.entry(score=20 if i<3 else i),"test")
        top = scores.tv_board()
        self.assertEqual(len(top),10)
        self.assertEqual(top[0]["id"],first["id"])
        self.assertEqual(len(set(e["playerId"] for e in top)),10)
        self.assertEqual([e["score"] for e in top],sorted([e["score"] for e in top],reverse=True))
    def test_invalid_submissions_never_write(self):
        for change in [dict(score=-1),dict(score=True),dict(score=121),dict(avatar="dog"),
                       dict(durationSeconds=30),dict(rules="web"),dict(id="bad"),
                       dict(completedAt=float("nan")),dict(completedAt=time.time()+1000)]:
            with self.assertRaises((ValueError,TypeError)):scores.save_score(self.entry(**change),"test")
        self.assertEqual(self.redis.dbsize(),0)
    def test_rate_limit(self):
        for _ in range(120): self.assertEqual(scores.save_score(self.entry(),"test")[0],200)
        self.assertEqual(scores.save_score(self.entry(),"test")[0],429)
    def test_ios_boards_are_isolated_and_retry_safe(self):
        player = str(uuid.uuid4())
        for board, (_, rules) in scores.BOARDS.items():
            d = self.entry(playerId=player, rules=rules)
            self.assertEqual(scores.save_score(d, "test")[0], 200)
            self.assertTrue(scores.save_score(d, "test")[1]["duplicate"])
            self.assertEqual(scores.tv_board(board)[0]["rules"], rules)
        self.assertEqual(len(scores.tv_board()), 1)
        self.assertEqual(len(scores.tv_board("ios")), 1)
        self.assertEqual(len(scores.tv_board("ios-standard")), 1)

    def test_http_routes_select_ios_board_and_preserve_default_tv(self):
        from http.server import HTTPServer
        from threading import Thread
        from urllib.request import urlopen, Request
        server = HTTPServer(("127.0.0.1", 0), scores.handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for board, (_, rules) in scores.BOARDS.items():
                scores.save_score(self.entry(rules=rules), "test")
                with urlopen(f"http://127.0.0.1:{server.server_port}/api/scores?board={board}") as response:
                    result = json.load(response)
                    self.assertEqual(result["board"], board)
                    self.assertEqual(result["entries"][0]["rules"], rules)
                    self.assertEqual(response.headers["Access-Control-Allow-Origin"], "*")
            with urlopen(f"http://127.0.0.1:{server.server_port}/api/scores") as response:
                self.assertEqual(json.load(response)["board"], "tvos")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_legacy_board_is_gone(self):
        from http.server import HTTPServer
        from threading import Thread
        from urllib.request import urlopen
        from urllib.error import HTTPError
        server = HTTPServer(("127.0.0.1", 0), scores.handler)
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            with self.assertRaises(HTTPError) as caught:
                urlopen(f"http://127.0.0.1:{server.server_port}/api/scores?board=legacy")
            self.assertEqual(caught.exception.code, 400)
        finally:
            server.shutdown(); server.server_close()

    def test_location_is_recorded_from_edge_headers_only(self):
        loc = scores.location_from_headers({"x-vercel-ip-city": "Budapest", "x-vercel-ip-country": "HU"})
        self.assertEqual(loc, {"city": "Budapest", "country": "HU"})
        self.assertIsNone(scores.location_from_headers({}))
        self.assertEqual(scores.location_from_headers({"x-vercel-ip-city": "S%C3%A3o%20Paulo", "x-vercel-ip-country": "br"}),
                         {"city": "São Paulo", "country": "BR"})
        d = self.entry(rules="ios-easy-60-v1")
        scores.save_score(d, "test", loc)
        self.assertEqual(scores.tv_board("ios")[0]["location"], loc)
        scores.save_score(self.entry(rules="ios-standard-60-v1"), "test", None)
        self.assertNotIn("location", scores.tv_board("ios-standard")[0])

    def test_board_shows_current_avatar_and_keeps_telemetry_off_the_board(self):
        player = str(uuid.uuid4())
        best = self.entry(playerId=player, score=20, avatar="1-1", rules="ios-easy-60-v1", **game(20))
        best["taps"][0].update({"s": "star", "x": 0.4, "y": 0.5})
        scores.save_score(best, "test")
        scores.save_score(self.entry(playerId=player, score=5, avatar="8-12", rules="ios-easy-60-v1"), "test")
        top = scores.tv_board("ios")[0]
        self.assertEqual(top["score"], 20)
        self.assertEqual(top["avatar"], "8-12")
        self.assertNotIn("telemetry", top)
        stored = json.loads(self.redis.hget("mobee:solo:ios:easy:v1:games", best["id"]))
        self.assertEqual(stored["telemetry"]["taps"][0]["x"], 0.4)
        self.assertEqual(stored["telemetry"]["client"]["app"], "ios")

if __name__ == "__main__":
    unittest.main()
