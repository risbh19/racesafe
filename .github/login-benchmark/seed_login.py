import asyncio
import os

from sqlalchemy import text

from backend.config import get_settings
from backend.db import make_engine
from backend.security import hash_password


async def seed():
    engine = make_engine(get_settings())
    try:
        digest = await hash_password(os.environ["LOGIN_BENCH_PASSWORD"])
        async with engine.begin() as conn:
            assert await conn.scalar(text("SELECT current_database()")) == "racesafe_login_benchmark"
            await conn.execute(text("""
                INSERT INTO users (id, email, password_hash, display_name)
                SELECT n, 'login-' || n || '@benchmark.racesafe.test', :digest, 'Benchmark user ' || n
                FROM generate_series(1, 10000) AS series(n)
            """), {"digest": digest})
            await conn.execute(text("""
                INSERT INTO participants (hackathon_id, user_id, looking)
                SELECT 1, id, id > 1500 FROM users
            """))
            await conn.execute(text("""
                INSERT INTO teams (id, hackathon_id, leader_id, name, min_size, max_size, member_count)
                SELECT n, h.id, 3 * n - 2, 'Benchmark team ' || n, h.min_team_size, h.max_team_size, 3
                FROM generate_series(1, 500) AS series(n) CROSS JOIN hackathons AS h WHERE h.id = 1
            """))
            await conn.execute(text("""
                INSERT INTO team_members (team_id, user_id, hackathon_id)
                SELECT (id - 1) / 3 + 1, id, 1 FROM users WHERE id <= 1500
            """))
            counts = (await conn.execute(text("""
                SELECT (SELECT count(*) FROM users),
                       (SELECT count(*) FROM participants WHERE hackathon_id = 1),
                       (SELECT count(*) FROM teams WHERE hackathon_id = 1),
                       (SELECT count(*) FROM team_members WHERE hackathon_id = 1)
            """))).one()
            assert tuple(counts) == (10_000, 10_000, 500, 1_500), counts
            await conn.execute(text("ANALYZE"))
        print("Verified seed: 10,000 users, 10,000 participants, 500 teams, 1,500 memberships")
    finally:
        await engine.dispose()


asyncio.run(seed())
