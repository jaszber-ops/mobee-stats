import datetime as dt
import importlib.util
import json
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
import fakeredis

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("daily_summary", root / ".github" / "scripts" / "daily_summary.py")
daily = importlib.util.module_from_spec(spec)
spec.loader.exec_module(daily)
scores = daily.scores
from test_scores import game


class SlackPingTests(unittest.TestCase):
    def setUp(self):
        self.redis = fakeredis.FakeRedis(decode_responses=True)
        self.sent = []
        self.addCleanup(patch.stopall)
        patch.object(scores, "redis_cmd", self.redis.execute_command).start()
        patch.object(scores, "slack_post", side_effect=lambda text: self.sent.append(text) or True).start()

    def play(self, score, player=None, rules="ios-easy-60-v1", **extra):
        d = dict(id=str(uuid.uuid4()), playerId=player or str(uuid.uuid4()), avatar="2-4", score=score,
                 completedAt=time.time(), durationSeconds=60, rules=rules, **game(score), **extra)
        d["client"] = {"app": "web"}
        status, _ = scores.save_score(d, "test", {"city": "Essen", "country": "DE"})
        self.assertEqual(status, 200)
        return d

    def test_new_bests_in_the_top_ten_ping_and_others_stay_quiet(self):
        first = self.play(9)
        self.assertEqual(len(self.sent), 1)
        self.assertIn("New #1 on Easy", self.sent[-1])
        self.assertIn("9 points", self.sent[-1])
        self.assertIn("Essen, DE · web", self.sent[-1])
        self.play(5)
        self.assertIn("#2 on Easy", self.sent[-1])
        self.play(3, player=first["playerId"])          # lower than that player's best: quiet
        self.assertEqual(len(self.sent), 2)
        scores.save_score(first, "test")                 # a retried upload: quiet
        self.assertEqual(len(self.sent), 2)
        for i in range(10):
            self.play(20 + i)
        self.assertIn("New #1 on Easy", self.sent[-1])
        before = len(self.sent)
        self.play(1)                                     # a first game outside the top 10: quiet
        self.assertEqual(len(self.sent), before)

    def test_boards_are_named(self):
        self.play(4, rules="ios-standard-60-v1")
        self.assertIn("New #1 on Hard", self.sent[-1])
        scores.save_score(dict(id=str(uuid.uuid4()), playerId=str(uuid.uuid4()), avatar="2-4", score=3,
                               completedAt=time.time(), durationSeconds=60, rules="tvos-easy-60-v1"), "test")
        self.assertIn("New #1 on Apple TV", self.sent[-1])

    def test_slack_trouble_never_costs_the_score(self):
        patch.object(scores, "slack_post", side_effect=RuntimeError("down")).start()
        d = self.play(7)
        self.assertEqual(scores.tv_board("ios")[0]["id"], d["id"])

    def test_slack_post_is_off_without_configuration(self):
        patch.stopall()
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(scores.slack_post("hello"))


class DailySummaryTests(unittest.TestCase):
    def test_counts_yesterday_only_with_new_players_apps_and_names(self):
        day = dt.date(2026, 10, 21)
        start, _ = daily.day_window(day)
        def g(player, score, at, app="web", city="Budapest"):
            return {"id": str(uuid.uuid4()), "playerId": player, "score": score, "receivedAt": at,
                    "displayName": "Player " + player[:6].upper(), "location": {"city": city, "country": "HU"},
                    "telemetry": {"client": {"app": app}}}
        easy = [g("aaaaaa-1", 3, start - 3600),               # the day before: only makes aaaaaa an old player
                g("aaaaaa-1", 14, start + 3600), g("bbbbbb-2", 9, start + 7200, app="ios", city="Essen"),
                g("cccccc-3", 2, start + 86400 + 60)]         # the day after: not counted
        hard = [g("aaaaaa-1", 6, start + 9000)]
        text = daily.summary(day, {"ios": (easy, [{"receivedAt": start + 5}], {"aaaaaa-1": "Johnny"}),
                                   "ios-standard": (hard, [], {}), "tvos": ([], [], {})})
        self.assertIn("Wed 21 Oct:* 3 games by 2 players (1 new) — web 2 · iOS 1", text)
        self.assertIn("• Easy: 2 games by 2 players, best 14 by Johnny", text)
        self.assertIn("• Hard: 1 game by 1 player, best 6 by Player AAAAAA", text)
        self.assertNotIn("Apple TV:", text)
        self.assertIn("Where: Budapest, HU 2, Essen, HU 1", text)
        self.assertIn("1 score refused by the cheat check", text)

    def test_quiet_day(self):
        self.assertIn("no games", daily.summary(dt.date(2026, 10, 21), {"ios": ([], [], {})}))

    def test_reads_the_boards_from_redis(self):
        redis = fakeredis.FakeRedis(decode_responses=True)
        with patch.object(scores, "redis_cmd", redis.execute_command):
            for i in range(1200):
                redis.hset("mobee:solo:ios:easy:v1:games", f"g{i}", json.dumps({"i": i}))
            redis.hset("mobee:solo:ios:easy:v1:names", "p", "Johnny")
            games, rejected, names = daily.load("mobee:solo:ios:easy:v1")
        self.assertEqual(len(games), 1200)
        self.assertEqual((rejected, names), ([], {"p": "Johnny"}))


if __name__ == "__main__":
    unittest.main()
