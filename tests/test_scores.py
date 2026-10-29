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

def expert_game(score, wrong=0, reaction=4200, jitter=1800, seed=1, deck=17):
    """Telemetry of a plausible two-minute Expert game: 17-card deck, 20 figures per card, one shared figure to find,
    so rounds take a few seconds each. Taps carry the card/slot/x/y detail the app sends."""
    rng = random.Random(seed)
    rounds, taps, t, rnd = [], [], 0, 1
    correct = score + wrong
    deals = [rng.sample(range(deck), 3) for _ in range(correct + 1)]
    figures = ["bulldozer", "hedgehog", "satellite", "violin", "camel", "umbrella", "butterfly", "smiley"]
    answers = [rng.choice(figures) for _ in range(correct + 1)]
    rounds.append({"r": 1, "t": 0, "cards": deals[0], "answer": answers[0]})
    misses = set(rng.sample(range(1, correct), wrong)) if wrong else set()
    for i in range(correct):
        if i in misses:
            t += 1100; taps.append({"t": t, "r": rnd, "s": "pine-tree", "ok": False, "card": 1, "slot": 7, "x": 0.31, "y": 0.62})
        t += reaction + rng.randint(-jitter, jitter)
        taps.append({"t": t, "r": rnd, "s": answers[i], "ok": True, "card": rng.randrange(3), "slot": rng.randrange(20),
                     "x": round(rng.random(), 3), "y": round(rng.random(), 3)})
        rnd += 1; rounds.append({"r": rnd, "t": t + 10, "cards": deals[i + 1], "answer": answers[i + 1]})
    return {"rounds": rounds, "taps": taps, "client": {"app": "web", "version": "2.0.0", "lang": "en", "ua": "Mozilla/5.0"}}

def twin_game(score, wrong=0, reaction=3500, jitter=1200, seed=1, deck=12):
    """Telemetry of a plausible two-minute Twin game: each round is won by naming both shared symbols.
    deck: 12 cards (green, Easy) or 10 (yellow, Hard)."""
    rng = random.Random(seed)
    rounds, taps, t, rnd = [], [], 0, 1
    correct = score + wrong
    deals = [rng.sample(range(deck), 3) for _ in range(correct + 1)]
    pair = ["star", "moon"]
    rounds.append({"r": 1, "t": 0, "cards": deals[0], "answers": pair})
    misses = set(rng.sample(range(1, correct), wrong)) if wrong else set()
    for i in range(correct):
        if i in misses:
            t += 900; taps.append({"t": t, "r": rnd, "s": ["star", "dog"], "ok": False})
        t += reaction + rng.randint(-jitter, jitter)
        taps.append({"t": t, "r": rnd, "s": ["moon", "star"], "ok": True, "card": 0, "slot": 2})
        rnd += 1; rounds.append({"r": rnd, "t": t + 10, "cards": deals[i + 1], "answers": pair})
    return {"rounds": rounds, "taps": taps, "client": {"app": "ios", "version": "1.2.0"}}

class ScoresTests(unittest.TestCase):
    def setUp(self):
        self.redis = fakeredis.FakeRedis(decode_responses=True)
        self.mock = patch.object(scores, "redis_cmd", self.redis.execute_command)
        self.mock.start()
        self.addCleanup(self.mock.stop)
    def entry(self, **overrides):
        d = dict(id=str(uuid.uuid4()), playerId=str(uuid.uuid4()), avatar="10-13",
                 score=12, completedAt=time.time(), durationSeconds=60, rules=scores.RULES)
        if overrides.get("rules") in scores.RULE_SPECS:
            d["durationSeconds"] = scores.RULE_SPECS[overrides["rules"]]["seconds"]
        d.update(overrides)
        if d["rules"].startswith("ios-expert-") and "taps" not in d:
            d.update(expert_game(d["score"]))
        elif d["rules"].startswith("ios-") and "taps" not in d:
            d.update(game(d["score"]))
        if d["rules"].startswith("twin-") and "taps" not in d:
            d.update(twin_game(d["score"], deck=scores.RULE_SPECS[d["rules"]]["deck"]))
        return d
    def test_twin_board_replays_pairs_over_two_minutes(self):
        twin = lambda **k: self.entry(rules="twin-green-120-v1", **k)
        self.assertEqual(scores.save_score(twin(), "test")[0], 200)
        self.assertEqual(scores.save_score(twin(score=20, **twin_game(20, wrong=3, seed=4)), "test")[0], 200)
        bad = [twin(taps=None, rounds=None),                                        # no telemetry
               twin(durationSeconds=60),                                            # Twin games are two minutes
               twin(score=13, **twin_game(12)),                                     # score above the taps
               twin(score=9, **game(9)),                                            # single-symbol answers are not Twin
               twin(score=50, **twin_game(50, reaction=3000, jitter=300))]          # 50 rounds at 3 s overrun 120 s
        one = twin_game(5); one["taps"][0]["s"] = ["moon", "moon"]                   # the same symbol twice
        bad.append(twin(score=5, **one))
        statuses = []
        for d in bad:
            try: statuses.append(scores.save_score(d, "test")[0])
            except ValueError: statuses.append(400)
        self.assertTrue(all(s != 200 for s in statuses), statuses)
        self.assertEqual(len(scores.tv_board("twin")), 2)
        self.assertTrue(all(e["rules"] == "twin-green-120-v1" for e in scores.tv_board("twin")))
    def test_twin_hard_yellow_deck_has_its_own_board(self):
        """Twin 2.0 Hard: the yellow 10-card deck (24 figures a card), two minutes, two shared symbols, board twin-yellow."""
        yellow = lambda **k: self.entry(**{"rules": "twin-yellow-120-v1", **k})
        self.assertEqual(scores.BOARDS["twin-yellow"], ("mobee:solo:twin:yellow:v1", "twin-yellow-120-v1"))
        good = [yellow(score=8, **twin_game(8, reaction=6000, jitter=2500, deck=10)),
                yellow(score=14, **twin_game(14, wrong=2, reaction=5500, jitter=2000, seed=3, deck=10))]
        for d in good:
            self.assertEqual(scores.save_score(d, "test")[0], 200)
        self.assertEqual(scores.save_score(self.entry(rules="twin-green-120-v1"), "test")[0], 200)
        green_deal = twin_game(6, deck=12)
        green_deal["rounds"][0]["cards"] = [9, 10, 11]                                   # cards 10 and 11 are not in the yellow deck
        bad = [yellow(taps=None, rounds=None),                                            # no telemetry
               yellow(durationSeconds=60),                                                # two-minute games
               yellow(score=7, **twin_game(6, deck=10)),                                  # score above the taps
               yellow(score=6, **green_deal),                                             # card index outside the 10-card deck
               yellow(score=9, **game(9)),                                                # single-symbol answers are not Twin
               yellow(score=40, **twin_game(40, reaction=3200, jitter=300, deck=10))]     # 40 rounds overrun 120 s
        statuses = []
        for d in bad:
            try: statuses.append(scores.save_score(d, "test")[0])
            except ValueError: statuses.append(400)
        self.assertTrue(all(s != 200 for s in statuses), statuses)
        top = scores.tv_board("twin-yellow")
        self.assertEqual([e["score"] for e in top], [14, 8])
        self.assertTrue(all(e["rules"] == "twin-yellow-120-v1" for e in top))
        self.assertEqual([e["rules"] for e in scores.tv_board("twin")], ["twin-green-120-v1"])  # boards stay apart
        self.assertEqual(scores.BOARD_LABELS["twin-yellow"], "Twin Hard")
    def test_hard_90_second_games_share_the_existing_hard_board(self):
        """Møbee 2.0 plays Hard for 90 s (ios-standard-90-v1); the 60-second Hard scores stay on the same board."""
        hard = lambda **k: self.entry(**{"rules": "ios-standard-90-v1", **k})
        old = self.entry(rules="ios-standard-60-v1", score=30, **game(30, reaction=1500, jitter=500))
        self.assertEqual(scores.save_score(old, "test")[0], 200)
        # 50 rounds at ~1.6 s run to ~80 s: past a 60-second clock, inside a 90-second one
        long = game(50, reaction=1600, jitter=500, seed=3)
        self.assertGreater(long["taps"][-1]["t"], 60000)
        self.assertEqual(scores.save_score(hard(score=50, **long), "test")[0], 200)
        self.assertEqual(scores.save_score(hard(score=9, **game(9, wrong=2, seed=5)), "test")[0], 200)
        top = scores.tv_board("ios-standard")
        self.assertEqual([(e["score"], e["rules"]) for e in top],
                         [(50, "ios-standard-90-v1"), (30, "ios-standard-60-v1"), (9, "ios-standard-90-v1")])
        self.assertEqual(self.redis.hlen("mobee:solo:ios:standard:v1:games"), 3)
        bad = [hard(durationSeconds=60),                                            # a 90-second rules id needs 90 s
               self.entry(rules="ios-standard-60-v1", score=50, **long),            # taps after a 60-second clock
               hard(score=70, **game(70, reaction=1400, jitter=400)),               # 70 rounds at 1.4 s overrun 90 s
               hard(score=9, **game(9, jitter=0))]                                  # metronomic
        eleventh = game(5); eleventh["rounds"][2]["cards"] = [0, 4, 10]              # the Hard deck has 10 cards
        bad.append(hard(score=5, **eleventh))
        for d in bad:
            try: status = scores.save_score(d, "test")[0]
            except ValueError: status = 400
            self.assertNotEqual(status, 200)
        self.assertEqual(len(scores.tv_board("ios-standard")), 3)
        self.assertEqual(self.redis.keys("mobee:solo:ios:standard:v2*"), [])
    def test_expert_board_accepts_two_minute_games_on_the_17_card_deck(self):
        expert = lambda **k: self.entry(**{"rules": "ios-expert-120-v1", **k})
        honest = expert(score=24, **expert_game(24, wrong=3, seed=2))
        self.assertEqual(scores.save_score(honest, "test")[0], 200)
        self.assertLess(len(json.dumps(honest)), scores.MAX_BODY)
        self.assertEqual(scores.save_score(expert(score=8, **expert_game(8, seed=6)), "test")[0], 200)
        fast = expert_game(40, reaction=2600, jitter=900, seed=7)                    # a very good player: ~2.6 s a round
        self.assertGreater(fast["rounds"][-1]["t"], 90000)
        self.assertEqual(scores.save_score(expert(score=40, **fast), "test")[0], 200)
        top = scores.tv_board("ios-expert")
        self.assertEqual([e["score"] for e in top], [40, 24, 8])
        self.assertTrue(all(e["rules"] == "ios-expert-120-v1" for e in top))
        self.assertNotIn("telemetry", top[0])
        self.assertEqual(self.redis.hlen("mobee:solo:ios:expert:v1:games"), 3)
        # Expert stays off the other boards
        self.assertEqual(scores.tv_board("ios-standard"), [])
        self.assertEqual(scores.tv_board("ios"), [])
    def test_expert_forgeries_are_refused(self):
        expert = lambda **k: self.entry(**{"rules": "ios-expert-120-v1", **k})
        off_deck = expert_game(6); off_deck["rounds"][3]["cards"] = [2, 9, 17]      # card 17 does not exist (0..16)
        pair = twin_game(6)                                                           # two-symbol answers are Twin, not Expert
        bad = [expert(taps=None, rounds=None),                                        # no telemetry
               expert(durationSeconds=60),                                            # Expert games are two minutes
               expert(score=15, **expert_game(14)),                                   # score above the taps
               expert(score=12, **expert_game(12, reaction=300, jitter=50)),          # inhuman reactions
               expert(score=12, **expert_game(12, jitter=0)),                         # metronomic
               expert(score=60, **expert_game(60, reaction=2200, jitter=400)),        # 60 rounds at 2.2 s overrun 120 s
               expert(score=6, **off_deck), expert(score=6, **pair),
               expert(score=241)]                                                     # above any possible score
        for d in bad:
            try: status = scores.save_score(d, "test")[0]
            except ValueError: status = 400
            self.assertNotEqual(status, 200, d.get("score"))
        self.assertEqual(scores.tv_board("ios-expert"), [])
        self.assertGreaterEqual(self.redis.hlen("mobee:solo:ios:expert:v1:rejected"), 6)
    def test_staging_app_rules_ids_are_all_accepted(self):
        """rulesFor(level) in mobee-ios staging www/scores.js, with gameSeconds 60/90/120, and boardFor(level)."""
        for level, rules, board in [(1, "ios-easy-60-v1", "ios"), (2, "ios-standard-90-v1", "ios-standard"),
                                    (3, "ios-expert-120-v1", "ios-expert")]:
            d = self.entry(rules=rules)
            self.assertEqual(d["durationSeconds"], {1: 60, 2: 90, 3: 120}[level])
            self.assertEqual(scores.save_score(d, "test")[0], 200, rules)
            self.assertEqual(scores.tv_board(board)[0]["id"], d["id"])
        # Twin: rulesFor(level) / boardFor(level) in mobee-ios twin www/scores.js (Easy green, Hard yellow)
        for rules, board in [("twin-green-120-v1", "twin"), ("twin-yellow-120-v1", "twin-yellow")]:
            self.assertEqual(scores.save_score(self.entry(rules=rules), "test")[0], 200, rules)
            self.assertEqual(scores.tv_board(board)[0]["rules"], rules)
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
        self.assertEqual(len(scores.tv_board("ios-expert")), 1)

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

    def live_app_submission(self, **overrides):
        """Exactly what play.trippplecard.games and the released iOS app post today (www/scores.js on main): no name."""
        d = dict(id=str(uuid.uuid4()), playerId=str(uuid.uuid4()), avatar="1-1", score=11,
                 completedAt=int(time.time()), durationSeconds=60, rules="ios-easy-60-v1", **game(11))
        d["client"] = {"app": "web", "version": "1.2.0", "lang": "en", "ua": "Mozilla/5.0"}
        d.update(overrides)
        return d

    def test_live_app_scores_are_kept_exactly_as_before(self):
        board_keys = {"id", "playerId", "avatar", "score", "completedAt", "receivedAt", "rules", "displayName", "location"}
        for rules in ("ios-easy-60-v1", "ios-standard-60-v1"):
            d = self.live_app_submission(rules=rules)
            status, body = scores.save_score(d, "test", {"city": "Essen", "country": "DE"})
            self.assertEqual((status, body["accepted"]), (200, True))
            board = "ios" if "easy" in rules else "ios-standard"
            top = scores.tv_board(board)[0]
            self.assertEqual(set(top), board_keys)
            self.assertEqual(top["displayName"], "Player " + d["playerId"][:6].upper())
            stored = json.loads(self.redis.hget(scores.BOARDS[board][0] + ":games", d["id"]))
            self.assertNotIn("name", stored)
            self.assertEqual(stored["telemetry"]["taps"], d["taps"])
        self.assertEqual(self.redis.keys("*:names"), [])

    def test_records_written_before_names_existed_still_read(self):
        prefix = scores.BOARDS["ios"][0]
        old = {"id": str(uuid.uuid4()), "playerId": str(uuid.uuid4()), "avatar": "3-4", "score": 30,
               "completedAt": 1, "receivedAt": 2, "rules": "ios-easy-60-v1", "displayName": "Player ABCDEF"}
        self.redis.zadd(prefix + ":best", {old["playerId"]: 30})
        self.redis.hset(prefix + ":players", old["playerId"], json.dumps(old))
        scores.save_score(self.live_app_submission(name="Johnny", score=9, **game(9)), "test")
        top = scores.tv_board("ios")
        self.assertEqual([(e["score"], e["displayName"]) for e in top], [(30, "Player ABCDEF"), (9, "Johnny")])

    def test_name_is_shown_kept_renamed_and_cleared(self):
        player = str(uuid.uuid4())
        first = self.live_app_submission(playerId=player, score=20, name="  Johnny  ", **game(20))
        scores.save_score(first, "test")
        self.assertEqual(scores.tv_board("ios")[0]["displayName"], "Johnny")
        self.assertEqual(scores.tv_board("ios")[0]["name"], "Johnny")
        self.assertEqual(json.loads(self.redis.hget("mobee:solo:ios:easy:v1:games", first["id"]))["name"], "Johnny")
        # a later, lower game without a name field leaves the name alone
        scores.save_score(self.live_app_submission(playerId=player, score=3, **game(3)), "test")
        self.assertEqual(scores.tv_board("ios")[0]["displayName"], "Johnny")
        # renaming shows on the best score that was set under the old name
        scores.save_score(self.live_app_submission(playerId=player, score=4, name="Johnny B", **game(4)), "test")
        self.assertEqual([(e["score"], e["displayName"]) for e in scores.tv_board("ios")], [(20, "Johnny B")])
        # a retried submission cannot change the name again
        scores.save_score(dict(first, name="Someone"), "test")
        self.assertEqual(scores.tv_board("ios")[0]["displayName"], "Johnny B")
        # emptying the name goes back to the default label
        scores.save_score(self.live_app_submission(playerId=player, score=2, name="", **game(2)), "test")
        top = scores.tv_board("ios")[0]
        self.assertEqual(top["displayName"], "Player " + player[:6].upper())
        self.assertNotIn("name", top)

    def test_a_bad_name_never_costs_the_score(self):
        player = str(uuid.uuid4())
        scores.save_score(self.live_app_submission(playerId=player, name="Anna"), "test")
        for bad in ["Møbee Master", "MOBEE", "Mo\u0301bee", 42, ["x"], {"a": 1}]:
            status, body = scores.save_score(self.live_app_submission(playerId=player, name=bad), "test")
            self.assertEqual((status, body["accepted"]), (200, True), bad)
        self.assertEqual(scores.tv_board("ios")[0]["displayName"], "Anna")
        scores.save_score(self.live_app_submission(playerId=player, name="Zs\u200bófi with a very long name"), "test")
        self.assertEqual(scores.tv_board("ios")[0]["displayName"], "Zsófi with a ver")

    def test_names_are_per_board_and_tvos_unchanged(self):
        player = str(uuid.uuid4())
        scores.save_score(self.live_app_submission(playerId=player, name="Johnny"), "test")
        scores.save_score(self.entry(playerId=player), "test")
        self.assertEqual(scores.tv_board("ios")[0]["displayName"], "Johnny")
        self.assertEqual(scores.tv_board()[0]["displayName"], "Player " + player[:6].upper())

    def test_rude_names_show_as_player_and_the_score_still_counts(self):
        ok = ["Johnny", "Zsófi", "Szarvas", "Classic", "Hancock", "Nigeria", "Nazira", "Assisi", "Dickens",
              "Kassandra", "Cumbria", "Basil", "Analise", "Titus", "Penelope", "Áron"]
        bad = ["sh1t", "s h i t", "fuuuck", "FüCK", "f*ck you", "kurva", "k.u.r.v.a", "Arsch", "4ss", "ASS",
               "big dick", "szar", "Nazi", "hitler88", "geci", "b@zmeg", "köcsög", "Fotze", "Scheiße", "p0rn"]
        self.assertEqual([n for n in ok if scores.name_blocked(n)], [])
        self.assertEqual([n for n in bad if not scores.name_blocked(n)], [])
        player = str(uuid.uuid4())
        scores.save_score(self.live_app_submission(playerId=player, name="Johnny"), "test")
        status, body = scores.save_score(self.live_app_submission(playerId=player, name="sh1t head", score=12, **game(12)), "test")
        self.assertEqual((status, body["accepted"]), (200, True))
        top = scores.tv_board("ios")[0]
        self.assertEqual((top["score"], top["displayName"]), (12, "Player " + player[:6].upper()))
        self.assertNotIn("name", json.loads(self.redis.hget("mobee:solo:ios:easy:v1:games", body["id"])))

if __name__ == "__main__":
    unittest.main()
