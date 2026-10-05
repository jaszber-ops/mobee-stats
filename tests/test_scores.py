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
        return d
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

    def test_legacy_best_per_player(self):
        data=[dict(user_code="old1",score=5,timestamp="100"),dict(user_code="old1",score=8,timestamp="101"),
              dict(user_code="old2",score=9,timestamp="102")]
        with patch.object(Path,"read_text",return_value=json.dumps(data)):
            result=scores.legacy_board()
        self.assertEqual([e["score"] for e in result],[9,8])
        self.assertTrue(all(e["rules"]=="legacy" for e in result))
        self.assertEqual(self.redis.dbsize(),0)

if __name__ == "__main__":unittest.main()
