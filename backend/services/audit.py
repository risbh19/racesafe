from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AuditEvent


def record(
    session: AsyncSession, hackathon_id: int, team_id: int, actor_id: int,
    action: str, **details,
) -> None:
    session.add(AuditEvent(
        hackathon_id=hackathon_id, team_id=team_id,
        actor_id=actor_id, action=action, details=details,
    ))


async def changed(session: AsyncSession, hackathon_id: int) -> None:
    await session.execute(
        text("SELECT pg_notify('racesafe_changes', :hackathon)"),
        {"hackathon": str(hackathon_id)},
    )
