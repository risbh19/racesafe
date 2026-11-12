from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from backend.config import Settings


def make_engine(settings: Settings):
    url, args = settings.database_connection()
    return create_async_engine(
        url, connect_args=args, pool_pre_ping=True,
        pool_size=settings.database_pool_size, max_overflow=0,
    )


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessions() as session:
        yield session


Session = Annotated[AsyncSession, Depends(get_session)]
