# RaceSafe

RaceSafe helps hackathon participants find teammates, request to join, and redeem expiring invites. PostgreSQL enforces the capacity and membership rules even when multiple requests compete for one seat.

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

[GitHub Actions](https://github.com/risbh19/racesafe/actions/workflows/ci.yml) runs the board benchmark against a disposable PostgreSQL database and a local API process. Each of the 100 virtual users uses a distinct seeded account. The CI run lasts 60 seconds with no pause between requests. Download `board-benchmark-report` from the workflow run for the measured p95 and error rate.

Use a separate benchmark database, apply the migration, and set the API and seed terminal to the same DATABASE_URL. Choose a password with at least 12 characters for the synthetic benchmark viewer and set SEED_PASSWORD in both the seed and k6 terminals. The seed creates 10,000 users, 2,000 teams and 6,000 memberships.

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

## Design and submission

- [Design note](docs/DESIGN.md)
- [Board benchmark](docs/LOAD-TEST.md)
- [Walkthrough outline](docs/WALKTHROUGH.md)
