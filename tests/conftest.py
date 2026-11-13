import os
from dataclasses import dataclass
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert, text
from sqlalchemy.engine import make_url

from backend.config import Settings
from backend.main import create_app
from backend.models import Participant, User
from backend.security import issue_token


def key() -> dict:
    return {"Idempotency-Key": str(uuid4())}


@dataclass
class RaceSafe:
    client: AsyncClient
    app: object

    async def users(self, number: int = 1, skills=None, offset: int = 0):
        suffix = uuid4().hex
        async with self.app.state.sessions.begin() as session:
            ids = (await session.scalars(insert(User).returning(User.id), [
                {
                    "email": f"person-{suffix}-{n}@example.test", "display_name": f"Person {n}",
                    "password_hash": "fixture-only", "skills": skills or [], "utc_offset_minutes": offset,
                }
                for n in range(number)
            ])).all()
            await session.execute(insert(Participant), [
                {"hackathon_id": 1, "user_id": user_id} for user_id in ids
            ])
        return [
            (user_id, {"Authorization": "Bearer " + issue_token(SimpleNamespace(app=self.app), user_id)})
            for user_id in ids
        ]

    async def team(self, headers, name="Example Team", **body):
        response = await self.client.post(
            "/api/hackathons/1/teams", json={"name": name, **body}, headers={**headers, **key()},
        )
        assert response.status_code == 201, response.text
        return response.json()["team_id"]

    async def invite(self, team_id, headers):
        response = await self.client.post(f"/api/teams/{team_id}/invite-code", headers=headers)
        assert response.status_code == 201, response.text
        return response.json()["code"]

    async def redeem(self, code, headers):
        return await self.client.post(
            "/api/invites/redeem", json={"code": code}, headers={**headers, **key()},
        )

    async def request(self, team_id, headers):
        response = await self.client.post(
            f"/api/teams/{team_id}/join-requests", json={}, headers={**headers, **key()},
        )
        assert response.status_code == 201, response.text
        return response.json()["request_id"]


@pytest_asyncio.fixture
async def race():
    url = os.getenv("TEST_DATABASE_URL")
    if not url or not (make_url(url).database or "").endswith("_test"):
        pytest.fail("Set TEST_DATABASE_URL to a migrated, disposable PostgreSQL database ending in _test")
    settings = Settings(
        database_url=url, direct_database_url=url, _env_file=None,
        jwt_secret="test-only-signing-secret-with-at-least-32-characters",
        hackathon_id=1, database_pool_size=50, require_email_verification=False,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with app.state.engine.begin() as connection:
            actual = await connection.scalar(text("SELECT current_database()"))
            assert actual.endswith("_test")
            await connection.execute(text(
                "TRUNCATE pending_registrations, idempotency_keys, join_requests, invite_codes, "
                "team_members, teams, participants, users CONTINUE IDENTITY"
            ))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield RaceSafe(client, app)
