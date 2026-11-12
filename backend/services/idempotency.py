import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Header, HTTPException
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import IdempotencyKey

Key = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=100)]


async def once(
    session: AsyncSession, actor: int, key: str, action: str, payload: dict,
    execute: Callable[[], Awaitable[dict]],
) -> dict:
    request_hash = hashlib.sha256(
        json.dumps([action, payload], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    claimed = await session.scalar(
        insert(IdempotencyKey)
        .values(user_id=actor, key=key, request_hash=request_hash)
        .on_conflict_do_nothing(index_elements=["user_id", "key"])
        .returning(IdempotencyKey)
    )
    if claimed is None:
        previous = await session.get(IdempotencyKey, (actor, key))
        if previous.request_hash != request_hash:
            raise HTTPException(422, "Idempotency-Key was already used for a different request")
        return previous.response

    claimed.response = await execute()
    return claimed.response
