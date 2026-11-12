import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable
from contextlib import suppress
from time import time

import asyncpg
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from backend.schemas import ID
from backend.security import BEARER, authenticate
from backend.services.teams import participant

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)
CHANGE = "event: changed\ndata: {}\n\n"


class Events:
    """The stream carries invalidations. Clients fetch snapshots on every connect."""

    def __init__(self, dsn: str, invalidate_board: Callable[[int], None]):
        self.dsn = dsn
        self.invalidate_board = invalidate_board
        self.ready = asyncio.Event()
        self.subscribers: dict[int, set[asyncio.Queue]] = defaultdict(set)

    def publish(self, hackathon_id: int) -> None:
        self.invalidate_board(hackathon_id)
        for queue in self.subscribers.get(hackathon_id, ()):
            if queue.empty():
                queue.put_nowait(None)

    def notified(self, _connection, _pid, _channel, payload):
        if payload.isdecimal():
            self.publish(int(payload))

    async def listen(self):
        delay = 0.5
        while True:
            connection = None
            disconnected = asyncio.Event()
            try:
                connection = await asyncpg.connect(self.dsn, timeout=5)
                connection.add_termination_listener(lambda _: disconnected.set())
                await connection.add_listener("racesafe_changes", self.notified)
                self.ready.set()
                for hackathon_id in self.subscribers:
                    self.publish(hackathon_id)
                delay = 0.5
                await disconnected.wait()
            except (OSError, asyncpg.PostgresError, TimeoutError):
                logger.warning("PostgreSQL event listener disconnected. Reconnecting.")
            finally:
                self.ready.clear()
                if connection and not connection.is_closed():
                    with suppress(TimeoutError, OSError, asyncpg.PostgresError):
                        await connection.close(timeout=2)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 10)

    async def stream(self, hackathon_id: int, expires: int):
        queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        subscribers = self.subscribers[hackathon_id]
        subscribers.add(queue)
        try:
            yield "retry: 2000\n" + CHANGE
            while expires > time():
                try:
                    await asyncio.wait_for(queue.get(), min(15, expires - time()))
                except TimeoutError:
                    yield ": keepalive\n\n" if self.ready.is_set() else CHANGE
                else:
                    yield CHANGE
        finally:
            subscribers.discard(queue)
            if not subscribers:
                self.subscribers.pop(hackathon_id, None)


@router.get("/hackathons/{hackathon_id}/events")
async def stream(hackathon_id: ID, request: Request, credentials=Depends(BEARER)):
    actor, expires = authenticate(request, credentials)
    async with request.app.state.sessions() as session:
        await participant(session, hackathon_id, actor)
    return StreamingResponse(
        request.app.state.events.stream(hackathon_id, expires),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
