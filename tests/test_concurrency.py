import asyncio

import pytest
from sqlalchemy import func, select

from backend.models import JoinRequest, Team, TeamMember
from conftest import key

pytestmark = pytest.mark.asyncio


async def together(operations):
    gate = asyncio.Event()

    async def run(operation):
        await gate.wait()
        return await operation()

    tasks = [asyncio.create_task(run(operation)) for operation in operations]
    await asyncio.sleep(0)
    gate.set()
    return await asyncio.wait_for(asyncio.gather(*tasks), timeout=30)


async def nearly_full(race):
    (_, leader), (_, first), (_, second) = await race.users(3)
    team_id = await race.team(leader)
    invite = await race.invite(team_id, leader)
    for headers in (first, second):
        assert (await race.redeem(invite, headers)).status_code == 200
    return team_id, leader, invite


async def assert_last_seat(race, team_id, results):
    codes = [response.status_code for response in results]
    assert codes.count(200) == 1, [response.text for response in results]
    assert codes.count(409) == 49, [response.text for response in results]
    async with race.app.state.sessions() as session:
        team = await session.get(Team, team_id)
        actual = await session.scalar(
            select(func.count()).select_from(TeamMember).where(TeamMember.team_id == team_id)
        )
        assert actual == team.member_count == team.max_size == 4


async def test_50_invites_compete_for_one_seat(race):
    team_id, _, invite = await nearly_full(race)
    contenders = await race.users(50)
    results = await together([
        lambda headers=headers: race.redeem(invite, headers) for _, headers in contenders
    ])
    await assert_last_seat(race, team_id, results)


async def test_50_approvals_compete_for_one_seat(race):
    team_id, leader, _ = await nearly_full(race)
    contenders = await race.users(50)
    request_ids = [await race.request(team_id, headers) for _, headers in contenders]
    results = await together([
        lambda rid=rid: race.client.post(
            f"/api/join-requests/{rid}/accept", headers={**leader, **key()},
        )
        for rid in request_ids
    ])
    await assert_last_seat(race, team_id, results)
    async with race.app.state.sessions() as session:
        approved = await session.scalar(
            select(func.count()).select_from(JoinRequest)
            .where(JoinRequest.team_id == team_id, JoinRequest.status == "accepted")
        )
        assert approved == 1


async def test_same_create_request_replayed_20_times(race):
    (_, leader), = await race.users()
    headers = {**leader, **key()}

    async def create():
        return await race.client.post(
            "/api/hackathons/1/teams", json={"name": "Same Team"}, headers=headers,
        )

    results = await together([create] * 20)
    assert all(response.status_code == 201 for response in results)
    assert len({response.json()["team_id"] for response in results}) == 1
    async with race.app.state.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Team)) == 1
        assert await session.scalar(select(func.count()).select_from(TeamMember)) == 1


async def test_same_invite_request_replays_join(race):
    (_, leader), (_, joiner) = await race.users(2)
    team_id = await race.team(leader)
    invite = await race.invite(team_id, leader)
    headers = {**joiner, **key()}

    async def redeem():
        return await race.client.post("/api/invites/redeem", headers=headers, json={"code": invite})

    first, second = await together([redeem, redeem])
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == {"team_id": team_id, "member_count": 2}
    async with race.app.state.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(TeamMember)) == 2


async def test_same_user_cannot_join_two_teams_in_parallel(race):
    (_, first), (_, second), (_, joiner) = await race.users(3)
    first_team = await race.team(first, "First Team")
    second_team = await race.team(second, "Second Team")
    first_code = await race.invite(first_team, first)
    second_code = await race.invite(second_team, second)
    results = await together([
        lambda: race.redeem(first_code, joiner),
        lambda: race.redeem(second_code, joiner),
    ])
    assert sorted(response.status_code for response in results) == [200, 409]


async def test_accept_and_decline_cannot_both_succeed(race):
    (_, leader), (_, joiner) = await race.users(2)
    team_id = await race.team(leader)
    request_id = await race.request(team_id, joiner)
    results = await together([
        lambda: race.client.post(
            f"/api/join-requests/{request_id}/accept", headers={**leader, **key()},
        ),
        lambda: race.client.post(f"/api/join-requests/{request_id}/decline", headers=leader),
    ])
    assert sorted(response.status_code for response in results) == [200, 409]
