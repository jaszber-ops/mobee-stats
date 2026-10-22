# Shared Møbee scores

The leaderboard domain opens /leaderboard.html; the stats domain retains its dashboard.
The stats API serves the report snapshot produced by the existing scheduled GitHub workflow.
It does not need Slack credentials or requests at page-load time.

## Existing data

- Legacy scores remain in mobee_games_raw.json. No migration or deletion is required.
- The existing web leaderboard reads mobee8:events:7 and mobee8:events:12 from Redis.
- /tvos.html offers the worldwide Apple TV and historical Legacy boards.
- /api/scores?board=legacy derives each historical player's best score from the saved records.
- /api/scores?board=tvos returns the best score per anonymous TV player.

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
Legacy, web multiplayer and Apple TV solo results remain separate competitions.
No account linking across installations is implemented.

## Player names

Any submission may carry an optional `name`. The server tidies it (spacing, invisible
characters, at most 16 characters) and keeps the player's latest name per board in
`<board prefix>:names`, next to their current avatar. Board entries then show it as
`displayName` and `name`; players who never set one keep "Player XXXXXX".

- No `name` field (every app version released so far): the stored name is left alone.
- `name: ""`: the player cleared it; the board goes back to "Player XXXXXX".
- A name containing "Møbee"/"Mobee", or one that isn't text, is ignored. The score is
  still accepted: the app re-sends anything refused with 400, so a name must never block it.
- Rude names (a short English, German and Hungarian word list in `api/scores.py`, kept identical to
  the app's) show as "Player", as if no name were set; the score still counts. Words in
  `BLOCKED_ANYWHERE` are caught inside longer names and through spacing, accents, repeated
  letters and digits ("s h 1 t", "fuuuck"); `BLOCKED_WORDS` only as whole words, because they
  also occur in ordinary names (Szarvas, Hancock). No list catches everything.

Existing scores need no migration. Removing a name by hand is `HDEL <prefix>:names <playerId>`.

## Verification

Run: pip install 'fakeredis[lua]'
Then: python -m unittest discover -s tests -v

Tests execute the actual Redis Lua scripts in an isolated fake Redis engine and cover
idempotent retries, player bests, top-10 order, ties, invalid input, rate limits and
legacy aggregation. They do not write production scores.

Check both homepages, /api/stats, /api/leaderboard and /api/scores after deployment.
Do not submit fabricated scores to the production board as a smoke test.
