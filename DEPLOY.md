# Deploying mobee-stats

This one doc replaces `DEPLOYMENT_GUIDE.md`, `DEPLOY_NOW.md`, `VERCEL_DEPLOYMENT.md`, `setup.sh` and `deploy-commands.sh`. Those described the old Slack-scraping report: `SLACK_TOKEN`/`CHANNEL_ID` in Vercel, an `/api/daily-report` Vercel cron, PDF and SendGrid emails, and `git init` from scratch. None of that exists any more.

## What gets deployed

| Path | What it is |
|---|---|
| `api/scores.py` | The shared leaderboard API, `GET/POST/OPTIONS /api/scores`. It holds the boards `ios`, `ios-standard`, `ios-expert`, `twin` and `tvos` (default), with rules ids, telemetry checks, player names, rate limits and Slack pings. See [GLOBAL-LEADERBOARD.md](GLOBAL-LEADERBOARD.md). Standard library only (`api/requirements.txt`). |
| `api/stats.py` | `GET /api/stats`: serves the saved snapshot `mobee_stats.json` (the last report of the old web game). No credentials needed. |
| `index.html`, `assets/`, `fonts/`, `pdf.png`, `mobee_stats_report.pdf`, `mobee_stats.json` | The static stats dashboard. On the leaderboard host, `index.html` sends visitors to the web game (still to `play.trippplecard.games`). |
| `vercel.json` | Python runtime `@vercel/python@4.3.1` for `api/*.py`, with `includeFiles: mobee*.json` so `stats.py` can read the snapshot. |

There is no build step and no Vercel cron.

## Vercel projects

The repository is deployed to **two existing Vercel projects**. Both serve the same code.

- **Leaderboard:** `https://mobee-leaderboard.trippplecard.games`, which serves `/api/scores` to the iPhone/iPad app and the web game (mobee-ios `www/scores.js`). The `tvos` board is still served, but the current Apple TV app sends nothing. Leave this host as it is: `leaderboard.mobeecards.com` is not set up.
- **Stats:** the dashboard and `/api/stats`.

Both projects deploy through Vercel's Git integration. `main` is the production branch, and every other branch and PR gets a preview deployment (check Settings → Git in each project). So **merging into `main` deploys the score API that every released app talks to.** Merge only when the leaderboard checks are green.

### Environment variables (Vercel → project → Settings → Environment Variables)

| Variable | Used by | Needed |
|---|---|---|
| `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN` | `api/scores.py` (`redis_cmd`) | **Yes**, in the project that serves `/api/scores`. Without them, `/api/scores` answers 503. |
| `UPSTASH_REDIS_URL`, `UPSTASH_REDIS_TOKEN` | the same, older aliases | Only if the pair above isn't set |
| `SLACK_WEBHOOK_URL` | Slack pings for a new top-10 best | Optional |
| `SLACK_BOT_TOKEN` + `SLACK_CHANNEL_ID` | the same, via `chat.postMessage` (used when there is no webhook) | Optional. Without either, nothing is posted. |

Both projects use the same Upstash database. `api/stats.py` needs no variables. Never put these values in the apps or in the repository. After changing a variable, redeploy the latest production deployment.

## GitHub Actions

| Workflow | When | Secrets |
|---|---|---|
| `leaderboard-checks.yml` | Every push and PR: `python -m unittest discover -s tests -v` (with `fakeredis[lua]`) and `py_compile` of both APIs | none |
| `daily-summary.yml` | Every day at 06:07 UTC, plus by hand (Actions → *Daily Møbee summary*; "dry run" is on by default and prints instead of posting). It runs `.github/scripts/daily_summary.py`, which reads yesterday's games from Redis and posts a summary to Slack. | `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`, `SLACK_TOKEN` (passed as `SLACK_BOT_TOKEN`), `REPORT_CHANNEL_ID` (passed as `SLACK_CHANNEL_ID`) |

## Before merging into main

1. Run the tests locally: `pip install 'fakeredis[lua]' redis` and then `python3 -m unittest discover -s tests -v`. They run the real Lua scripts against a fake Redis and never write production scores.
2. When the rules ids change, update mobee-ios `tests/fixtures/server-rules.json` too. mobee-ios CI (`scripts/check-rules.mjs`) compares that file with `api/scores.py` on `main`.
3. After the deployment, check that `GET https://mobee-leaderboard.trippplecard.games/api/scores?board=ios`, `?board=ios-standard`, `?board=ios-expert` and `?board=tvos` answer 200, that `/api/stats` answers 200 on the stats host, and that the dashboard loads. **Do not post fabricated scores** to the production boards as a smoke test.

## Rolling back

Vercel → the project → Deployments → pick the previous production deployment → *Promote to Production* (or *Instant Rollback*). The data lives in Upstash, so a rollback never loses scores. A board the older code doesn't know (for example `ios-expert` before Møbee 2.0) answers 400 until you roll forward. Its scores stay in Redis.
