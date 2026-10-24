#!/usr/bin/env python3
"""Post yesterday's Møbee games (play.trippplecard.games, iOS, Apple TV) to Slack.

Reads the games the apps upload to the leaderboard (Redis), not Slack. Run with --dry-run to print
the message instead of posting it.
"""
import datetime as dt
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Budapest")
spec = importlib.util.spec_from_file_location("scores", Path(__file__).resolve().parents[2] / "api" / "scores.py")
scores = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scores)


def hash_values(key):
    """Every value of a Redis hash, read in pages so a large one never arrives in a single reply."""
    cursor, values = "0", []
    while True:
        cursor, page = scores.redis_cmd("HSCAN", key, cursor, "COUNT", 500)
        # Upstash answers [cursor, [field, value, ...]]; a local Redis client may give a dict instead.
        values += list(page.values()) if isinstance(page, dict) else page[1::2]
        if str(cursor) == "0":
            return values


def hash_dict(key):
    flat = scores.redis_cmd("HGETALL", key) or []
    return dict(flat) if isinstance(flat, dict) else dict(zip(flat[::2], flat[1::2]))


def load(prefix):
    games = []
    for raw in hash_values(prefix + ":games"):
        try:
            games.append(json.loads(raw))
        except ValueError:
            pass
    rejected = []
    for raw in hash_values(prefix + ":rejected"):
        try:
            rejected.append(json.loads(raw))
        except ValueError:
            pass
    return games, rejected, hash_dict(prefix + ":names")


def n(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


def day_window(day):
    start = dt.datetime.combine(day, dt.time(), TZ)
    return start.timestamp(), (start + dt.timedelta(days=1)).timestamp()


def summary(day, boards):
    """boards: {board: (games, rejected, names)} -> Slack message text for `day` (a date in Budapest time)."""
    start, end = day_window(day)
    label = day.strftime("%a %-d %b")
    lines, everyone, new, apps, places, played, blocked = [], set(), set(), Counter(), Counter(), 0, 0
    first_seen = {}  # a player's first game on any board: new to Møbee, not just new to Hard
    for games, _, _ in boards.values():
        for g in games:
            first_seen[g["playerId"]] = min(first_seen.get(g["playerId"], g["receivedAt"]), g["receivedAt"])
    for board, (games, rejected, names) in boards.items():
        today = [g for g in games if start <= g["receivedAt"] < end]
        blocked += sum(1 for r in rejected if start <= r.get("receivedAt", 0) < end)
        if not today:
            continue
        played += len(today)
        players = {g["playerId"] for g in today}
        everyone |= players
        new |= {p for p in players if start <= first_seen[p] < end}
        for g in today:
            apps[((g.get("telemetry") or {}).get("client") or {}).get("app") or ("tv" if board == "tvos" else "?")] += 1
            loc = g.get("location") or {}
            if loc.get("city") or loc.get("country"):
                places[", ".join(x for x in (loc.get("city"), loc.get("country")) if x)] += 1
        best = max(today, key=lambda g: (g["score"], -g["receivedAt"]))
        who = names.get(best["playerId"]) or best.get("name") or best.get("displayName") or "Player"
        lines.append(f"• {scores.BOARD_LABELS[board]}: {n(len(today), 'game')} by {n(len(players), 'player')}, best {best['score']} by {who}")
    if not played:
        text = f":zzz: *Møbee, {label}:* no games."
    else:
        app_names = {"web": "web", "ios": "iOS", "tv": "Apple TV"}
        split = " · ".join(f"{app_names.get(a, a)} {n}" for a, n in apps.most_common())
        text = (f":bar_chart: *Møbee, {label}:* {n(played, 'game')} by {n(len(everyone), 'player')}"
                f" ({len(new)} new) — {split}\n" + "\n".join(lines))
        if places:
            text += "\n• Where: " + ", ".join(f"{p} {n}" for p, n in places.most_common(5))
    if blocked:
        text += f"\n• {n(blocked, 'score')} refused by the cheat check"
    return text


def main(argv):
    day = dt.datetime.now(TZ).date() - dt.timedelta(days=1)
    text = summary(day, {board: load(prefix) for board, (prefix, _) in scores.BOARDS.items()})
    if "--dry-run" in argv:
        print(text)
        return 0
    if not scores.slack_post(text):
        print("Slack post failed or Slack is not configured", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
