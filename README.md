# Møbee stats and leaderboard

- `api/scores.py` is the shared leaderboard API used by play.trippplecard.games, the iOS app and the
  Apple TV app. See GLOBAL-LEADERBOARD.md.
- Slack: a ping for every new personal best that reaches a board's top 10 (sent by the score API),
  and a summary of yesterday's games every morning (`.github/workflows/daily-summary.yml`).
- The stats dashboard (`index.html`, `/api/stats`) still shows the last report of the old web game,
  saved in `mobee_stats.json`; the Slack scraping that produced it was removed in October 2026.
