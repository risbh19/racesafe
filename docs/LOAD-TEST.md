# RaceSafe board load test

## GitHub Actions

The [fix-branch validation run](https://github.com/risbh19/racesafe/actions/runs/43470830477) used one API process and PostgreSQL 16. Each 60-second run used 100 distinct authenticated virtual users with no pause between requests and fetched 20 teams from the first board page.

| Seed dataset | Board p95 | HTTP errors | Report |
| --- | ---: | ---: | --- |
| 10,000 users and 2,000 teams | 14.99 ms | 0% | [10,000-user JSON artifact](https://github.com/risbh19/racesafe/actions/runs/43470830477/artifacts/14060572045) |
| 20,000 users and 2,000 teams | 15.05 ms | 0% | [20,000-user JSON artifact](https://github.com/risbh19/racesafe/actions/runs/43470830477/artifacts/14061681117) |

Both runs met the p95 target of 200 ms. Render latency, concurrent login and SSE fan-out are outside this benchmark.

## Local baseline

Measured on 13 November 2026. Both 60-second runs used k6 2.4.0 on the same Windows host as one Uvicorn worker. PostgreSQL 16 ran in Docker Desktop with the API pool limited to 12 connections. The seed command verified 10,000 users, 2,000 teams and 6,000 memberships. Each request fetched 20 teams from the authenticated board endpoint. The 100 virtual users reused a single synthetic benchmark account.

| Workload | Successful requests | Requests/sec | Median | p95 | p99 | HTTP errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 virtual users, one-second pause | 5,600 | 91.76 | 78.26 ms | 135.04 ms | 154.56 ms | 0% |
| 100 virtual users, no pause | 96,830 | 1,611.47 | 21.61 ms | 34.83 ms | 1,430.32 ms | 0% |

Both runs passed the p95 under 200 ms threshold. The unpaced run still had large tail spikes, visible in p99. These are local results for the first board page. Public hosting, filtered queries, and simultaneous team writes were outside this benchmark.

The initial unpaced implementation measured 886.28 ms p95. A one-second first-page cache invalidated by committed PostgreSQL notifications improved it to 400.10 ms p95. The final hot path skips creating a database session when the board snapshot and the authenticated participant's enrollment are cached.

Run the benchmark from the repository root with SEED_PASSWORD configured as described in the README. The default run has a one-second pause per user. Set PACE_SECONDS=0 for the saturation run.
