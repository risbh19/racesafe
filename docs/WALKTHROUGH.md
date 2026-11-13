# RaceSafe walkthrough

[Download the walkthrough MP4 (ZIP)](https://github.com/risbh19/racesafe/actions/runs/43473115252/artifacts/14061753462).

The **Browser walkthrough** job records two independent browser sessions against the built React app, FastAPI and a disposable PostgreSQL database. Open the [RaceSafe CI runs](https://github.com/risbh19/racesafe/actions/workflows/ci.yml), choose a successful run, and download the `racesafe-walkthrough` artifact. The MP4 is under five minutes.

- Left side is the team leader on desktop. Right side is the applicant in a 390 px mobile viewport.
- Both accounts are created and operated by keyboard. The applicant loads 40 board cards, then receives the newly created team live while retaining 40 cards.
- The applicant requests to join, the leader accepts, and the applicant sees the updated membership and seat count without a page reload.
- The leader displays an expiring invite, explained teammate rankings, and the approval audit entry.

The [concurrency tests](../tests/test_concurrency.py) assert one winner and 49 conflicts for the last seat. The [design note](DESIGN.md) describes the transaction, and the [load-test report](LOAD-TEST.md) contains the board benchmark.
