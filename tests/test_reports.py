import json
import os
import time
import unittest
import uuid
from http.server import HTTPServer
from threading import Thread
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import fakeredis

from test_scores import scores, game

TOKEN = "t" * 32


class NameReportTests(unittest.TestCase):
    def setUp(self):
        self.redis = fakeredis.FakeRedis(decode_responses=True)
        self.sent = []
        self.addCleanup(patch.stopall)
        patch.object(scores, "redis_cmd", self.redis.execute_command).start()
        patch.object(scores, "slack_post", side_effect=lambda text: self.sent.append(text) or True).start()
        patch.dict(os.environ, {"ADMIN_TOKEN": TOKEN}).start()

    def play(self, name=None, score=11, player=None, rules="ios-easy-60-v1"):
        d = dict(id=str(uuid.uuid4()), playerId=player or str(uuid.uuid4()), avatar="1-1", score=score,
                 completedAt=time.time(), durationSeconds=60, rules=rules, **game(score))
        if name is not None:
            d["name"] = name
        self.assertEqual(scores.save_score(d, "player")[0], 200)
        return d["playerId"]

    def shown(self, board="ios"):
        return [e["displayName"] for e in scores.tv_board(board)]

    def test_three_distinct_reporters_hide_the_name_pending_review(self):
        johnny = self.play("Johnny", score=20)
        self.play("Anna", score=5)
        self.sent.clear()                                                    # top-10 pings
        report = {"board": "ios", "playerId": johnny, "name": "Johnny"}
        self.assertEqual(scores.report_name(report, "1.1.1.1"), (200, {"reported": True}))
        self.assertEqual(scores.report_name(report, "1.1.1.1")[0], 200)     # the same address again: counted once
        self.assertEqual(scores.report_name(report, "2.2.2.2")[0], 200)
        self.assertEqual(self.shown(), ["Johnny", "Anna"])
        self.assertEqual(len(self.sent), 2)                                  # one ping per distinct reporter
        self.assertIn("Name reported on Easy", self.sent[0])
        self.assertIn("“Johnny”", self.sent[0])
        self.assertIn("1 report, still shown", self.sent[0])
        self.assertIn("action=hide", self.sent[0])
        self.assertIn('"playerId":"%s"' % johnny, self.sent[0])
        self.assertNotIn(TOKEN, self.sent[0])
        scores.report_name(report, "3.3.3.3")
        self.assertIn("3 reports, :no_entry_sign: hidden from the board until reviewed", self.sent[-1])
        self.assertEqual(self.shown(), ["Player " + johnny[:6].upper(), "Anna"])
        top = scores.tv_board("ios")[0]
        self.assertEqual(top["score"], 20)                                   # the score stays
        self.assertNotIn("name", top)
        self.assertEqual(json.loads(self.redis.hget("mobee:solo:ios:easy:v1:reported", johnny))["count"], 3)
        # renaming does not escape the hide
        self.play("Johnny2", score=2, player=johnny)
        self.assertEqual(self.shown()[0], "Player " + johnny[:6].upper())

    def test_reports_are_per_board_and_need_a_name(self):
        player = self.play("Johnny")
        self.play("Johnny", player=player, rules="ios-standard-60-v1")
        for address in ("a", "b", "c"):
            scores.report_name({"board": "ios", "playerId": player}, address)
        self.assertEqual(self.shown("ios"), ["Player " + player[:6].upper()])
        self.assertEqual(self.shown("ios-standard"), ["Johnny"])
        nameless = self.play()
        self.assertEqual(scores.report_name({"board": "ios", "playerId": nameless}, "a")[0], 404)
        for bad in [{"board": "nope", "playerId": player}, {"board": "ios", "playerId": "x"}, [], None]:
            with self.assertRaises(ValueError):
                scores.report_name(bad, "a")

    def test_report_rate_limit_per_address(self):
        players = [self.play("P%d" % i) for i in range(scores.REPORT_RATE_LIMIT + 1)]
        statuses = [scores.report_name({"board": "ios", "playerId": p}, "9.9.9.9")[0] for p in players]
        self.assertEqual(statuses[:-1], [200] * scores.REPORT_RATE_LIMIT)
        self.assertEqual(statuses[-1], 429)

    def test_slack_trouble_never_breaks_a_report_and_names_are_escaped(self):
        player = self.play("<!channel> hi")
        self.sent.clear()
        scores.report_name({"board": "ios", "playerId": player}, "a")
        self.assertIn("&lt;!channel&gt; hi", self.sent[-1])
        patch.object(scores, "slack_post", side_effect=RuntimeError("down")).start()
        self.assertEqual(scores.report_name({"board": "ios", "playerId": player}, "b")[0], 200)

    def test_admin_hide_and_unhide(self):
        player = self.play("Johnny")
        scores.set_hidden({"board": "ios", "playerId": player}, True)
        self.assertEqual(self.shown(), ["Player " + player[:6].upper()])
        self.assertEqual(json.loads(self.redis.hget("mobee:solo:ios:easy:v1:hidden", player))["by"], "admin")
        for address in ("a", "b"):
            scores.report_name({"board": "ios", "playerId": player}, address)
        scores.set_hidden({"board": "ios", "playerId": player}, False)
        self.assertEqual(self.shown(), ["Johnny"])
        self.assertEqual(self.redis.keys("*:reports:*"), [])
        scores.report_name({"board": "ios", "playerId": player}, "c")       # counting starts again
        self.assertEqual(self.shown(), ["Johnny"])

    def test_admin_token_is_required(self):
        self.assertTrue(scores.admin_authorized({"Authorization": "Bearer " + TOKEN}, "a"))
        self.assertFalse(scores.admin_authorized({"Authorization": "Bearer nope"}, "a"))
        self.assertFalse(scores.admin_authorized({}, "a"))
        with patch.dict(os.environ, {"ADMIN_TOKEN": ""}):
            self.assertFalse(scores.admin_authorized({"Authorization": "Bearer "}, "b"))
        with patch.dict(os.environ, {"ADMIN_TOKEN": "short"}):                # too short to be a real secret
            self.assertFalse(scores.admin_authorized({"Authorization": "Bearer short"}, "b"))

    def test_http_routes(self):
        server = HTTPServer(("127.0.0.1", 0), scores.handler)
        Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_port}/api/scores"
        def call(query, body=None, token=None, method=None):
            headers = {"Content-Type": "application/json"}
            if token:
                headers["Authorization"] = "Bearer " + token
            data = json.dumps(body).encode() if body is not None else None
            try:
                with urlopen(Request(base + query, data=data, headers=headers, method=method)) as r:
                    return r.status, json.load(r), r.headers
            except HTTPError as e:
                return e.code, json.load(e), e.headers
        try:
            player = self.play("Johnny")
            target = {"board": "ios", "playerId": player}
            status, body, headers = call("?action=report", target)
            self.assertEqual((status, body), (200, {"reported": True}))
            self.assertEqual(headers["Access-Control-Allow-Origin"], "*")
            self.assertEqual(call("?action=report", {"board": "ios", "playerId": "bad"})[0], 400)
            self.assertEqual(call("?action=whatever", target)[0], 404)
            self.assertEqual(call("?action=hide", target)[0], 401)
            self.assertEqual(call("?action=hide", target, token="wrong")[0], 401)
            self.assertEqual(self.shown(), ["Johnny"])
            self.assertEqual(call("?action=hide", target, token=TOKEN)[:2],
                             (200, {"board": "ios", "playerId": player, "hidden": True}))
            self.assertEqual(self.shown(), ["Player " + player[:6].upper()])
            status, body, _ = call("?board=ios&action=reports", token=TOKEN)
            self.assertEqual(status, 200)
            self.assertEqual(body["reported"][player]["count"], 1)
            self.assertEqual(body["hidden"][player]["name"], "Johnny")
            self.assertEqual(call("?board=ios&action=reports")[0], 401)
            self.assertEqual(call("?action=unhide", target, token=TOKEN)[0], 200)
            self.assertEqual(self.shown(), ["Johnny"])
            # the board itself is unchanged
            status, body, _ = call("?board=ios")
            self.assertEqual(body["entries"][0]["displayName"], "Johnny")
            # repeated wrong tokens lock the address out, even with the right token
            for _ in range(scores.ADMIN_FAILURE_LIMIT):
                call("?action=hide", target, token="wrong")
            self.assertEqual(call("?action=hide", target, token=TOKEN)[0], 429)
            # CORS preflight allows the in-app report POST
            with urlopen(Request(base + "?action=report", method="OPTIONS")) as r:
                self.assertEqual(r.status, 204)
                self.assertIn("POST", r.headers["Access-Control-Allow-Methods"])
        finally:
            server.shutdown(); server.server_close()

    def test_an_old_backend_ignores_reports(self):
        """Until this is deployed, the app's report POST reaches save_score: it must be refused without writing."""
        with self.assertRaises(ValueError):
            scores.save_score({"board": "ios", "playerId": str(uuid.uuid4()), "name": "x"}, "a")
        self.assertEqual(self.redis.dbsize(), 0)


if __name__ == "__main__":
    unittest.main()
