# RaceSafe

RaceSafe helps hackathon participants find teammates, request to join, and redeem expiring invites. PostgreSQL enforces the capacity and membership rules even when multiple requests compete for one seat.

[Live demo](https://racesafe.onrender.com) · [Design note](docs/DESIGN.md) · [Load-test report](docs/LOAD-TEST.md) · [Walkthrough](docs/WALKTHROUGH.md)

## Run locally on Windows

Open PowerShell in the repository root. Start Docker Desktop first.

```powershell
docker compose up -d --wait db
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000
```

In a second terminal:

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

Open [the React app](http://localhost:5173). [API docs](http://127.0.0.1:8000/docs) and the [database health endpoint](http://127.0.0.1:8000/api/health) are on port 8000. Register two accounts in separate browser sessions to demonstrate team creation, a request, leader approval, and automatic updates.

Forming teams may have one member. A leader can finalize a team after it meets the minimum. Finalizing closes its seats. A departure below the minimum reopens it. A team with zero members is deleted and its audit history is retained.

## Tests

CI uses PostgreSQL 16 and runs the API suite, repeats concurrency tests five times, and builds and lints the React frontend. To run locally, create a **disposable database ending in _test** and set its URL before running the commands below. The tests truncate app tables in this database.

```powershell
docker compose exec db createdb -U racesafe racesafe_test
$env:DATABASE_URL = "postgresql+asyncpg://racesafe:racesafe_dev@127.0.0.1:5432/racesafe_test"
$env:TEST_DATABASE_URL = $env:DATABASE_URL
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q tests/test_concurrency.py --count=5
```

## Board benchmark

[GitHub Actions](https://github.com/risbh19/racesafe/actions/workflows/ci.yml) runs separate 10,000-user and 20,000-user board benchmarks, each with a fresh PostgreSQL database, 2,000 teams and a local API process. Each of the 100 virtual users uses a distinct seeded account. Both CI runs last 60 seconds with no pause between requests. Download `board-benchmark-report-10000-users` and `board-benchmark-report-20000-users` from the workflow run for the measured p95 and error rate.

Use a separate benchmark database, apply the migration, and set the API and seed terminal to the same DATABASE_URL. Choose a password with at least 12 characters for the synthetic benchmark viewer and set SEED_PASSWORD in both the seed and k6 terminals. By default the seed creates 10,000 users, 2,000 teams and 6,000 memberships. Pass `--users 20000` for the larger dataset. Use a fresh database for each size so prior seed data does not affect the comparison.

```powershell
.\.venv\Scripts\python.exe -m scripts.seed
k6 run loadtest/board.js
```

k6 defaults to port 8000 and 100 concurrent virtual users for 60 seconds with a one-second pause between requests per user. Set BASE_URL to target a different instance or PACE_SECONDS=0 to run a saturation test. The threshold is board p95 under 200 ms, zero HTTP errors, and all checks passing. See [load test report](docs/LOAD-TEST.md) and the generated JSON at `loadtest/report.json`. The default local run uses one shared benchmark account. To reproduce CI's distinct accounts, set the same `JWT_SECRET` in the seed and API terminals, run `python -m scripts.seed --board-tokens <new-file>`, and set `BOARD_TOKEN_FILE` to that file's absolute path when running k6. Keep that token file outside the repository.

## Deploy

The root Dockerfile builds the React assets and starts one FastAPI process serving the UI and API on the same origin. It applies migrations at startup and binds to the hosting provider's PORT.

1. Create a PostgreSQL database and copy its direct connection URL. For a managed database requiring TLS, include sslmode=require. A session/direct connection is required for PostgreSQL LISTEN.
2. Create a Docker web service from this repository with the root Dockerfile. Set DATABASE_URL and a unique random JWT_SECRET of at least 32 characters. If DATABASE_URL uses a transaction pooler, set DIRECT_DATABASE_URL to the corresponding direct connection.
3. Set the health check path to /api/health, deploy, then check two browser sessions against the public URL.

A demo can use [Render's free web service and PostgreSQL options](https://render.com/docs/free). Free web services sleep when idle and free Render databases expire after 30 days. See [port and service settings](https://render.com/docs/web-services).

### Enable email verification on Render

Add these variables to the RaceSafe web service and redeploy. Store the sending key in Render's environment settings.

| Variable | Value |
| --- | --- |
| `REQUIRE_EMAIL_VERIFICATION` | `true` |
| `PUBLIC_APP_URL` | Your app's HTTPS origin, for example `https://racesafe.onrender.com` |
| `RESEND_API_KEY` | A sending key from [Resend](https://resend.com/) |
| `VERIFICATION_FROM_EMAIL` | A sender on a [verified Resend domain](https://resend.com/docs/dashboard/domains/introduction) |

New signups receive a single-use link that expires after 30 minutes. They enter the signup password to create the account and receive a JWT. The signup form can request another link after expiration or a delivery failure. Existing accounts can sign in with their current credentials. Verification is disabled by default until the sending provider is configured.

## Design and submission

- [Design note](docs/DESIGN.md)
- [Board benchmark](docs/LOAD-TEST.md)
- [Walkthrough recording and verification](docs/WALKTHROUGH.md)
