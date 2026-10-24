# Shared Møbee scores

The leaderboard domain serves the score API (/api/scores) and sends visitors of its root to
play.trippplecard.games, where the boards are shown. The stats domain retains its dashboard.
The stats API serves the report snapshot produced by the existing scheduled GitHub workflow.
It does not need Slack credentials or requests at page-load time.

## Boards

- /api/scores?board=ios and ?board=ios-standard: play.trippplecard.games and the iOS app (Easy, Hard).
- /api/scores?board=tvos: the Apple TV app (also the default when no board is given).
- The old leaderboard.html / tvos.html pages, the multiplayer leaderboard (/api/leaderboard)
  and the legacy board were removed in October 2026. Their source data was not deleted.

## Vercel configuration

Deploy this repository to both existing Vercel projects. The Python functions include
the report JSON files. Set the same Upstash database in both projects using either pair:

- UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN (preferred)
- UPSTASH_REDIS_URL and UPSTASH_REDIS_TOKEN (existing aliases)

The leaderboard deployment already had working Redis credentials; the stats deployment
did not. Never put these values into the Apple TV app or GitHub source.

## New Apple TV scores

POST /api/scores accepts id, playerId, avatar (row-column), score, completedAt
(Unix seconds), durationSeconds=60, and rules=tvos-easy-60-v1.

Each avatar selection starts a new anonymous visitor ID; Play again retains it.
The TV keeps a persistent upload queue and cached boards. It retries while running and
when the leaderboard opens. Identical game IDs are accepted once. An atomic Lua
transaction records the game and updates a player's best only when it improves.

The new namespace mobee:solo:tvos:v1 keeps its games, best-score index and player metadata
separate from the existing web data. Staff reset clears only the local TV top 10.

Submissions are client-reported. Validation, per-address rate limits and idempotency
reduce accidental/bulk abuse; they do not establish cheat-proof competitive scores.
No account linking across installations is implemented.

## Verification

Run: pip install 'fakeredis[lua]'
Then: python -m unittest discover -s tests -v

Tests execute the actual Redis Lua scripts in an isolated fake Redis engine and cover
idempotent retries, player bests, top-10 order, ties, invalid input and rate limits. They do not write production scores.

Check both homepages, /api/stats and /api/scores after deployment.
Do not submit fabricated scores to the production board as a smoke test.
