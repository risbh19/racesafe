import asyncio
from collections import OrderedDict
from time import monotonic

from fastapi.responses import JSONResponse


class BoardCache:
    """Short-lived, per-hackathon read snapshots. Writes always use PostgreSQL."""

    def __init__(self):
        self.enrolled: OrderedDict[tuple[int, int], float] = OrderedDict()
        self.snapshots: OrderedDict[tuple[int, int], tuple[float, JSONResponse]] = OrderedDict()
        self.generation = 0
        self.loading = asyncio.Lock()

    def has_enrollment(self, hackathon_id: int, user_id: int) -> bool:
        return self.enrolled.get((hackathon_id, user_id), 0) > monotonic()

    def remember_enrollment(self, hackathon_id: int, user_id: int) -> None:
        key = (hackathon_id, user_id)
        self.enrolled[key] = monotonic() + 30
        self.enrolled.move_to_end(key)
        if len(self.enrolled) > 12_000:
            self.enrolled.popitem(last=False)

    def get(self, hackathon_id: int, limit: int) -> JSONResponse | None:
        cached = self.snapshots.get((hackathon_id, limit))
        return cached[1] if cached and cached[0] > monotonic() else None

    def store(self, hackathon_id: int, limit: int, response: JSONResponse, generation: int) -> None:
        if self.generation != generation:
            return
        key = (hackathon_id, limit)
        self.snapshots[key] = (monotonic() + 1, response)
        self.snapshots.move_to_end(key)
        if len(self.snapshots) > 128:
            self.snapshots.popitem(last=False)

    def invalidate(self, hackathon_id: int) -> None:
        self.generation += 1
        for key in tuple(self.snapshots):
            if key[0] == hackathon_id:
                del self.snapshots[key]
