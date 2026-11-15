import asyncio
import hashlib
import hmac
import logging
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from backend.models import RateLimit

logger = logging.getLogger(__name__)
table = RateLimit.__table__


class RateLimiter:
    """Shared fixed windows. Count rejected attempts outside the mutation transaction."""

    def __init__(self, engine: AsyncEngine, secret: str):
        self.engine = engine
        self.secret = secret.encode()

    async def take(self, scope: str, key: str, *, limit: int, seconds: int = 60) -> None:
        bucket = hmac.new(self.secret, f"{scope}:{key}".encode(), hashlib.sha256).hexdigest()
        now = func.clock_timestamp()
        expired = table.c.expires_at <= now
        expiry = now + timedelta(seconds=seconds)
        statement = insert(table).values(bucket=bucket, attempts=1, expires_at=expiry)
        statement = statement.on_conflict_do_update(
            index_elements=[table.c.bucket],
            set_={
                "attempts": case((expired, 1), else_=table.c.attempts + 1),
                "expires_at": case((expired, expiry), else_=table.c.expires_at),
            },
            where=or_(expired, table.c.attempts < limit),
        ).returning(table.c.attempts)
        retry_after = seconds
        try:
            async with self.engine.begin() as connection:
                count = await connection.scalar(statement)
                if count is None:
                    retry_after = await connection.scalar(
                        select(func.ceil(func.extract("epoch", table.c.expires_at - now)))
                        .where(table.c.bucket == bucket)
                    )
        except (SQLAlchemyError, OSError) as exc:
            raise HTTPException(503, "Rate limit check temporarily unavailable", {"Retry-After": "1"}) from exc
        if count is None:
            raise HTTPException(429, "Too many attempts. Try again shortly.", {
                "Retry-After": str(max(1, int(retry_after or 0))),
            })

    async def prune(self) -> None:
        candidates = (
            select(table.c.bucket).where(table.c.expires_at <= func.now())
            .order_by(table.c.expires_at).limit(5000).with_for_update(skip_locked=True)
        )
        while True:
            await asyncio.sleep(60)
            try:
                async with self.engine.begin() as connection:
                    await connection.execute(delete(table).where(table.c.bucket.in_(candidates)))
            except (SQLAlchemyError, OSError):
                logger.warning("Could not clean up expired rate limits", exc_info=True)
