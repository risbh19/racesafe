"""Kill a real API process after it reserves a seat and before it inserts the member."""

import asyncio
import os
import socket
import sys
from contextlib import asynccontextmanager

import httpx
import pytest
from sqlalchemy import func, select, text

from backend.models import AuditEvent, IdempotencyKey, Team, TeamMember
from conftest import key

JOIN_GATE = 703491
TOKEN_SECRET = "test-only-signing-secret-with-at-least-32-characters"


@asynccontextmanager
async def api_process(tmp_path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    environment = {
        **os.environ, "DATABASE_URL": os.environ["TEST_DATABASE_URL"],
        "DIRECT_DATABASE_URL": os.environ["TEST_DATABASE_URL"], "JWT_SECRET": TOKEN_SECRET,
    }
    log_path = tmp_path / f"uvicorn-{port}.log"
    with log_path.open("wb") as log:
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "uvicorn", "backend.main:app",
            "--host", "127.0.0.1", "--port", str(port), env=environment,
            stdout=log, stderr=log,
        )
        try:
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=20) as client:
                for _ in range(100):
                    if process.returncode is not None:
                        break
                    try:
                        if (await client.get("/api/health", timeout=1)).status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    await asyncio.sleep(0.1)
                else:
                    pytest.fail("API did not become healthy\n" + log_path.read_text(errors="replace"))
                assert process.returncode is None, log_path.read_text(errors="replace")
                yield process, client
        finally:
            if process.returncode is None:
                process.kill()
            await asyncio.wait_for(process.wait(), timeout=10)


async def wait_for_blocked_insert(connection):
    async with asyncio.timeout(10):
        while not await connection.scalar(text(
            "SELECT EXISTS (SELECT 1 FROM pg_locks "
            "WHERE locktype = 'advisory' AND classid = 0 AND objid = :key "
            "AND objsubid = 1 AND NOT granted)"
        ), {"key": JOIN_GATE}):
            await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_kill_mid_join_rolls_back_and_same_request_can_retry(race, tmp_path):
    (_, leader), (applicant_id, applicant) = await race.users(2)
    team_id = await race.team(leader)
    invite = await race.invite(team_id, leader)
    headers = {**applicant, **key()}
    engine = race.app.state.engine

    async with engine.begin() as connection:
        await connection.execute(text(f"""
            CREATE FUNCTION test_gate_join() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                PERFORM pg_advisory_xact_lock({JOIN_GATE});
                RETURN NEW;
            END;
            $$
        """))
        await connection.execute(text(
            "CREATE TRIGGER test_gate_join BEFORE INSERT ON team_members "
            "FOR EACH ROW EXECUTE FUNCTION test_gate_join()"
        ))

    try:
        async with engine.connect() as gate:
            await gate.scalar(text("SELECT pg_advisory_lock(:key)"), {"key": JOIN_GATE})
            try:
                async with api_process(tmp_path) as (process, client):
                    joining = asyncio.create_task(client.post(
                        "/api/invites/redeem", json={"code": invite}, headers=headers,
                    ))
                    try:
                        # The trigger runs on INSERT, after the seat counter was updated.
                        await wait_for_blocked_insert(gate)
                        process.kill()
                        await asyncio.wait_for(process.wait(), timeout=10)
                        with pytest.raises(httpx.TransportError):
                            await joining
                    finally:
                        if not joining.done():
                            joining.cancel()
                            await asyncio.gather(joining, return_exceptions=True)
            finally:
                await gate.scalar(text("SELECT pg_advisory_unlock(:key)"), {"key": JOIN_GATE})
    finally:
        async with engine.begin() as connection:
            await connection.execute(text("DROP TRIGGER test_gate_join ON team_members"))
            await connection.execute(text("DROP FUNCTION test_gate_join()"))

    async with race.app.state.sessions.begin() as session:
        team = await session.get(Team, team_id, with_for_update=True)
        assert team.member_count == 1 and team.is_draft
        assert await session.get(TeamMember, (team_id, applicant_id)) is None
        assert await session.get(IdempotencyKey, (applicant_id, headers["Idempotency-Key"])) is None
        joined = select(func.count()).select_from(AuditEvent).where(
            AuditEvent.team_id == team_id, AuditEvent.action == "member.joined",
        )
        assert await session.scalar(joined) == 0

    async with api_process(tmp_path) as (_, client):
        first = await client.post("/api/invites/redeem", json={"code": invite}, headers=headers)
        replay = await client.post("/api/invites/redeem", json={"code": invite}, headers=headers)
        assert first.status_code == replay.status_code == 200
        assert first.json() == replay.json() == {"team_id": team_id, "member_count": 2}

    async with race.app.state.sessions() as session:
        team = await session.get(Team, team_id)
        actual = await session.scalar(select(func.count()).select_from(TeamMember).where(
            TeamMember.team_id == team_id,
        ))
        assert actual == team.member_count == 2 and not team.is_draft
        assert await session.scalar(joined) == 1
        assert await session.get(TeamMember, (team_id, applicant_id)) is not None
