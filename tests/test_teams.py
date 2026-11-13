from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import insert, select, update
from sqlalchemy.exc import DBAPIError

from backend.models import AuditEvent, InviteCode, JoinRequest
from conftest import key

pytestmark = pytest.mark.asyncio


async def test_create_team_adds_leader(race):
    (leader, headers), = await race.users()
    team_id = await race.team(headers)
    response = await race.client.get(f"/api/teams/{team_id}", headers=headers)
    team = response.json()
    assert (team["leader_id"], team["member_count"]) == (leader, 1)
    assert [member["id"] for member in team["members"]] == [leader]


async def test_create_requires_idempotency_key(race):
    (_, headers), = await race.users()
    response = await race.client.post("/api/hackathons/1/teams", headers=headers, json={"name": "My Team"})
    assert response.status_code == 422


@pytest.mark.parametrize("field", ["name", "description", "needed_skills"])
async def test_create_rejects_invalid_database_text(race, field):
    (_, headers), = await race.users()
    value = "Test\0value"
    body = {"name": "My Team", field: [value] if field == "needed_skills" else value}
    response = await race.client.post(
        "/api/hackathons/1/teams", headers={**headers, **key()}, json=body,
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][:2] == ["body", field]


async def test_join_request_rejects_invalid_database_text(race):
    (_, leader), (_, joiner) = await race.users(2)
    team_id = await race.team(leader)
    response = await race.client.post(
        f"/api/teams/{team_id}/join-requests", headers={**joiner, **key()},
        json={"message": "Hello\0there"},
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "message"]


@pytest.mark.parametrize("endpoint", ["board", "people"])
async def test_board_rejects_invalid_skill_filter(race, endpoint):
    (_, headers), = await race.users()
    response = await race.client.get(
        f"/api/hackathons/1/{endpoint}", headers=headers, params={"skill": "Python\0"},
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "skill"]


async def test_idempotency_key_cannot_change_payload(race):
    (_, auth), = await race.users()
    headers = {**auth, **key()}
    first = await race.client.post("/api/hackathons/1/teams", headers=headers, json={"name": "My Team"})
    other = await race.client.post("/api/hackathons/1/teams", headers=headers, json={"name": "Other Team"})
    assert (first.status_code, other.status_code) == (201, 422)


async def test_one_team_rule(race):
    (_, headers), = await race.users()
    await race.team(headers)
    response = await race.client.post(
        "/api/hackathons/1/teams", headers={**headers, **key()}, json={"name": "Second Team"},
    )
    assert response.status_code == 409


async def test_finalize_requires_minimum(race):
    (_, headers), = await race.users()
    team_id = await race.team(headers)
    assert (await race.client.post(f"/api/teams/{team_id}/lock", headers=headers)).status_code == 422


async def test_finalize_and_reopen(race):
    (_, leader), (_, joiner) = await race.users(2)
    team_id = await race.team(leader)
    code = await race.invite(team_id, leader)
    assert (await race.redeem(code, joiner)).status_code == 200
    locked = await race.client.post(f"/api/teams/{team_id}/lock", headers=leader)
    reopened = await race.client.delete(f"/api/teams/{team_id}/lock", headers=leader)
    assert locked.json()["locked"] is True
    assert reopened.json()["locked"] is False


async def test_rotation_revokes_old_invite(race):
    (_, leader), (_, joiner) = await race.users(2)
    team_id = await race.team(leader)
    old = await race.invite(team_id, leader)
    new = await race.invite(team_id, leader)
    assert (await race.redeem(old, joiner)).status_code == 400
    assert (await race.redeem(new, joiner)).status_code == 200


async def test_expired_invite(race):
    (_, leader), (_, joiner) = await race.users(2)
    team_id = await race.team(leader)
    code = await race.invite(team_id, leader)
    async with race.app.state.sessions.begin() as session:
        await session.execute(update(InviteCode).values(
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        ))
    assert (await race.redeem(code, joiner)).status_code == 400


async def test_invite_rate_limit(race):
    (_, headers), = await race.users()
    for _ in range(8):
        assert (await race.redeem("AAAAAAAAAAAA", headers)).status_code == 400
    assert (await race.redeem("AAAAAAAAAAAA", headers)).status_code == 429


async def test_completed_invite_retry_replays_at_rate_limit(race):
    (_, leader), (_, joiner) = await race.users(2)
    team_id = await race.team(leader)
    code = await race.invite(team_id, leader)
    headers = {**joiner, **key()}
    for _ in range(7):
        assert (await race.redeem("AAAAAAAAAAAA", joiner)).status_code == 400

    first = await race.client.post("/api/invites/redeem", headers=headers, json={"code": code})
    assert first.status_code == 200
    assert (await race.redeem(code, joiner)).status_code == 429
    replay = await race.client.post("/api/invites/redeem", headers=headers, json={"code": code})
    assert replay.status_code == 200
    assert replay.json() == first.json() == {"team_id": team_id, "member_count": 2}
    detail = await race.client.get(f"/api/teams/{team_id}", headers=leader)
    assert len(detail.json()["members"]) == 2


async def test_leader_can_page_past_first_hundred_join_requests(race):
    (_, leader), = await race.users()
    applicants = await race.users(101)
    team_id = await race.team(leader)
    async with race.app.state.sessions.begin() as session:
        await session.execute(insert(JoinRequest), [
            {"team_id": team_id, "user_id": user_id} for user_id, _ in applicants
        ])

    path = f"/api/teams/{team_id}/join-requests"
    first = await race.client.get(path, headers=leader)
    assert first.status_code == 200
    assert len(first.json()["requests"]) == 100
    cursor = first.json()["next_after"]
    assert cursor == first.json()["requests"][-1]["id"]
    second = await race.client.get(path, headers=leader, params={"after": cursor})
    assert second.status_code == 200
    assert [row["user_id"] for row in second.json()["requests"]] == [applicants[-1][0]]
    assert second.json()["next_after"] is None
    forbidden = await race.client.get(path, headers=applicants[-1][1], params={"after": cursor})
    assert forbidden.status_code == 403


async def test_join_request_leader_only_and_accept(race):
    (_, leader), (_, joiner), (_, outsider) = await race.users(3)
    team_id = await race.team(leader)
    request_id = await race.request(team_id, joiner)
    for action in ("accept", "decline"):
        response = await race.client.post(
            f"/api/join-requests/{request_id}/{action}", headers={**outsider, **key()},
        )
        assert response.status_code == 403
    accepted = await race.client.post(
        f"/api/join-requests/{request_id}/accept", headers={**leader, **key()},
    )
    assert accepted.json()["member_count"] == 2
    me = (await race.client.get("/api/me", headers=joiner)).json()
    assert me["requests"][0]["status"] == "accepted"


async def test_leader_declines(race):
    (_, leader), (_, joiner) = await race.users(2)
    team_id = await race.team(leader)
    request_id = await race.request(team_id, joiner)
    response = await race.client.post(f"/api/join-requests/{request_id}/decline", headers=leader)
    assert response.json() == {"status": "declined"}


async def test_accept_cancels_other_pending_requests(race):
    (_, first), (_, second), (_, joiner) = await race.users(3)
    first_team = await race.team(first, "First Team")
    second_team = await race.team(second, "Second Team")
    winner = await race.request(first_team, joiner)
    other = await race.request(second_team, joiner)
    accepted = await race.client.post(
        f"/api/join-requests/{winner}/accept", headers={**first, **key()},
    )
    assert accepted.status_code == 200
    me = (await race.client.get("/api/me", headers=joiner)).json()
    statuses = {item["id"]: item["status"] for item in me["requests"]}
    assert statuses == {winner: "accepted", other: "cancelled"}


async def test_non_leader_cannot_remove(race):
    (leader_id, leader), (_, joiner) = await race.users(2)
    team_id = await race.team(leader)
    await race.redeem(await race.invite(team_id, leader), joiner)
    response = await race.client.delete(f"/api/teams/{team_id}/members/{leader_id}", headers=joiner)
    assert response.status_code == 403


async def test_remove_restores_looking(race):
    (_, leader), (member_id, member) = await race.users(2)
    team_id = await race.team(leader)
    await race.redeem(await race.invite(team_id, leader), member)
    removed = await race.client.delete(f"/api/teams/{team_id}/members/{member_id}", headers=leader)
    assert removed.status_code == 200
    assert (await race.client.get("/api/me", headers=member)).json()["looking"] is True


async def test_leave_promotes_oldest(race):
    (_, leader), (first, first_headers), (_, second_headers) = await race.users(3)
    team_id = await race.team(leader)
    code = await race.invite(team_id, leader)
    await race.redeem(code, first_headers)
    await race.redeem(code, second_headers)
    response = await race.client.delete(f"/api/teams/{team_id}/members/me", headers=leader)
    assert response.json()["leader_id"] == first


async def test_last_member_deletes_team_preserves_audit(race):
    (actor, leader), = await race.users()
    team_id = await race.team(leader)
    response = await race.client.delete(f"/api/teams/{team_id}/members/me", headers=leader)
    assert response.json()["deleted"] is True
    assert (await race.client.get(f"/api/teams/{team_id}", headers=leader)).status_code == 404
    async with race.app.state.sessions() as session:
        event = await session.scalar(select(AuditEvent).where(
            AuditEvent.team_id == team_id, AuditEvent.action == "team.deleted",
        ))
        assert event.actor_id == actor


async def test_audit_is_append_only(race):
    (_, leader), = await race.users()
    team_id = await race.team(leader)
    response = await race.client.get(f"/api/teams/{team_id}/audit", headers=leader)
    assert response.json()["events"][0]["action"] == "team.created"
    with pytest.raises(DBAPIError, match="append-only"):
        async with race.app.state.sessions.begin() as session:
            await session.execute(update(AuditEvent).values(action="tampered"))
