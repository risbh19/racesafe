# RaceSafe walkthrough

[Watch or download the walkthrough MP4](racesafe-walkthrough.mp4). GitHub Actions also generates a fresh recording on each successful browser run.

The **Browser walkthrough** job records two independent browser sessions against the built React app, FastAPI and a disposable PostgreSQL database. Open the [RaceSafe CI runs](https://github.com/risbh19/racesafe/actions/workflows/ci.yml), choose a successful run, and download the `racesafe-walkthrough` artifact. The MP4 is under five minutes.

- Left side is the team leader on desktop. Right side is the applicant in a 390 px mobile viewport.
- Both accounts are created and operated by keyboard. The applicant loads 40 board cards, then receives the newly created team live while retaining 40 cards.
- The leader inbox restores an optimistically removed request after a simulated conflict. A successful retry forms the team and updates the applicant's seat count live.
- A second leader session rotates the invite. The first session discards its revoked code. The suggestions list updates when a new match arrives, and the approval appears in the audit log.

The [concurrency tests](../tests/test_concurrency.py) assert one winner and 49 conflicts for the last seat. The [design note](DESIGN.md) describes the transaction, and the [load-test report](LOAD-TEST.md) contains the board benchmark.
