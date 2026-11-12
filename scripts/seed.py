import asyncio
import os

from sqlalchemy import text

from backend.config import get_settings
from backend.db import make_engine
from backend.security import hash_password

VIEWER = "seed-10000@benchmark.racesafe.test"


async def seed():
    password = os.environ.get("SEED_PASSWORD", "")
    if len(password) < 12:
        raise SystemExit("Set SEED_PASSWORD to at least 12 characters for the benchmark account.")

    settings = get_settings()
    engine = make_engine(settings)
    params = {"hackathon_id": settings.hackathon_id, "viewer_hash": await hash_password(password)}
    try:
        async with engine.begin() as connection:
            await connection.execute(text("""
                INSERT INTO users (email, password_hash, display_name, skills, utc_offset_minutes)
                SELECT 'seed-' || n || '@benchmark.racesafe.test',
                       CASE WHEN n = 10000 THEN :viewer_hash ELSE '!benchmark-only!' END,
                       'Benchmark participant ' || n,
                       ARRAY[(ARRAY['python', 'react', 'design', 'sql', 'testing'])[(n % 5) + 1]],
                       ((n % 25) - 12) * 60
                FROM generate_series(1, 10000) AS numbers(n)
                ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash
                WHERE users.email = 'seed-10000@benchmark.racesafe.test'
                  AND users.display_name = 'Benchmark participant 10000'
            """), params)
            await connection.execute(text("""
                CREATE TEMP TABLE racesafe_seed_users ON COMMIT DROP AS
                SELECT n, u.id AS user_id
                FROM generate_series(1, 10000) AS numbers(n)
                JOIN users AS u ON u.email = 'seed-' || n || '@benchmark.racesafe.test'
                WHERE u.display_name = 'Benchmark participant ' || n
            """))
            await connection.execute(text("""
                INSERT INTO participants (hackathon_id, user_id, looking)
                SELECT :hackathon_id, user_id, n > 6000 FROM racesafe_seed_users
                ON CONFLICT (hackathon_id, user_id) DO NOTHING
            """), params)
            await connection.execute(text("""
                INSERT INTO teams (hackathon_id, leader_id, name, description, needed_skills,
                                   min_size, max_size, member_count)
                SELECT h.id, s.user_id, 'Benchmark team ' || ((s.n - 1) / 3 + 1),
                       'Synthetic team for the board benchmark.',
                       ARRAY[(ARRAY['python', 'react', 'design', 'sql', 'testing'])[(s.n % 5) + 1]],
                       h.min_team_size, h.max_team_size, 3
                FROM racesafe_seed_users AS s
                JOIN hackathons AS h ON h.id = :hackathon_id
                WHERE s.n <= 6000 AND s.n % 3 = 1
                ON CONFLICT (hackathon_id, name) DO NOTHING
            """), params)
            await connection.execute(text("""
                INSERT INTO team_members (team_id, user_id, hackathon_id)
                SELECT t.id, s.user_id, t.hackathon_id
                FROM racesafe_seed_users AS s
                JOIN racesafe_seed_users AS lead ON lead.n = ((s.n - 1) / 3) * 3 + 1
                JOIN teams AS t ON t.hackathon_id = :hackathon_id AND t.leader_id = lead.user_id
                               AND t.name = 'Benchmark team ' || ((s.n - 1) / 3 + 1)
                WHERE s.n <= 6000
                ON CONFLICT (hackathon_id, user_id) DO NOTHING
            """), params)
            counts = (await connection.execute(text("""
                SELECT
                  (SELECT count(*) FROM racesafe_seed_users) AS users,
                  (SELECT count(*) FROM teams AS t JOIN racesafe_seed_users AS s ON s.user_id = t.leader_id
                    WHERE t.hackathon_id = :hackathon_id
                      AND t.name = 'Benchmark team ' || ((s.n - 1) / 3 + 1)) AS teams,
                  (SELECT count(*) FROM team_members AS m
                    JOIN racesafe_seed_users AS s ON s.user_id = m.user_id
                    JOIN teams AS t ON t.id = m.team_id
                    WHERE m.hackathon_id = :hackathon_id AND s.n <= 6000
                      AND t.name = 'Benchmark team ' || ((s.n - 1) / 3 + 1)) AS memberships
            """), params)).one()
            if tuple(counts) != (10_000, 2_000, 6_000):
                raise RuntimeError(f"Unexpected benchmark counts: {tuple(counts)}")
            bad = await connection.scalar(text("""
                SELECT count(*) FROM teams AS t
                JOIN racesafe_seed_users AS s ON s.user_id = t.leader_id
                WHERE t.hackathon_id = :hackathon_id
                  AND t.name = 'Benchmark team ' || ((s.n - 1) / 3 + 1)
                  AND t.member_count <> (SELECT count(*) FROM team_members AS m WHERE m.team_id = t.id)
            """), params)
            if bad:
                raise RuntimeError(f"Seat count invariant failed for {bad} seeded teams")
            await connection.execute(
                text("SELECT pg_notify('racesafe_changes', :hackathon)"),
                {"hackathon": str(settings.hackathon_id)},
            )
        async with engine.begin() as connection:
            for table in ("users", "teams", "team_members", "participants"):
                await connection.execute(text(f"ANALYZE {table}"))
        print(f"Seeded 10,000 users, 2,000 teams and 6,000 memberships. Benchmark account: {VIEWER}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
