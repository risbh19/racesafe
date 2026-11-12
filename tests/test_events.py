import asyncio
from contextlib import aclosing
from time import time

import pytest

pytestmark = pytest.mark.asyncio


async def test_event_endpoint_requires_authentication(race):
    response = await race.client.get("/api/hackathons/1/events")
    assert response.status_code == 401


async def test_commit_notifies_two_live_subscribers(race):
    (_, leader), = await race.users()
    events = race.app.state.events
    await asyncio.wait_for(events.ready.wait(), timeout=5)
    empty = await race.client.get("/api/hackathons/1/board", headers=leader)
    assert empty.json()["teams"] == []
    async with aclosing(events.stream(1, int(time()) + 30)) as first:
        async with aclosing(events.stream(1, int(time()) + 30)) as second:
            assert "event: changed" in await anext(first)
            assert "event: changed" in await anext(second)
            team_id = await race.team(leader)
            for stream in (first, second):
                assert "event: changed" in await asyncio.wait_for(anext(stream), timeout=5)
            board = await race.client.get("/api/hackathons/1/board", headers=leader)
            assert board.json()["teams"][0]["id"] == team_id
