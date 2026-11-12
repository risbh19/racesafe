from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import InviteCode, Team
from backend.security import invite_hash, new_invite
from backend.services.audit import changed, record
from backend.services.teams import claim_seat, locked_team, participant, require_leader


async def rotate_invite(session: AsyncSession, team_id: int, actor: int, secret: str) -> dict:
    team = await locked_team(session, team_id)
    require_leader(team, actor)
    now = await session.scalar(select(func.clock_timestamp()))
    await session.execute(
        update(InviteCode).where(InviteCode.team_id == team_id, InviteCode.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    code = new_invite()
    expires_at = now + timedelta(hours=24)
    session.add(InviteCode(
        code_hash=invite_hash(secret, code), team_id=team_id, created_by=actor, expires_at=expires_at,
    ))
    record(session, team.hackathon_id, team_id, actor, "invite.rotated")
    await changed(session, team.hackathon_id)
    return {"code": code, "expires_at": expires_at}


async def redeem(session: AsyncSession, user_id: int, code: str, secret: str) -> dict:
    digest = invite_hash(secret, code)
    found = (
        await session.execute(
            select(InviteCode.team_id, Team.hackathon_id)
            .join(Team, Team.id == InviteCode.team_id)
            .where(InviteCode.code_hash == digest)
        )
    ).one_or_none()
    if found is None:
        raise HTTPException(400, "Invite is invalid or expired")

    enrolled = await participant(session, found.hackathon_id, user_id, lock=True)
    team = await locked_team(session, found.team_id)
    valid = await session.scalar(
        select(InviteCode.code_hash).where(
            InviteCode.code_hash == digest, InviteCode.revoked_at.is_(None),
            InviteCode.expires_at > func.clock_timestamp(),
        )
    )
    if valid is None:
        raise HTTPException(400, "Invite is invalid or expired")
    return await claim_seat(session, team, enrolled, user_id)
