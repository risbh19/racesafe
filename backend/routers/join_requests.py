from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from backend.db import Session
from backend.models import JoinRequest, Team, User
from backend.schemas import ID, JoinInput
from backend.security import CurrentUser
from backend.services.audit import changed, record
from backend.services.idempotency import Key, once
from backend.services.teams import claim_seat, ensure_teamless, locked_team, participant, require_leader

router = APIRouter(prefix="/api")


async def locate(session: Session, request_id: int):
    row = (
        await session.execute(
            select(JoinRequest.team_id, JoinRequest.user_id, Team.hackathon_id)
            .join(Team, Team.id == JoinRequest.team_id).where(JoinRequest.id == request_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(404, "Join request not found")
    return row


async def lock_pending(session: Session, request_id: int) -> JoinRequest:
    row = await session.scalar(
        select(JoinRequest).where(JoinRequest.id == request_id).with_for_update()
    )
    if row is None:
        raise HTTPException(404, "Join request not found")
    if row.status != "pending":
        raise HTTPException(409, "Join request was already decided")
    return row


@router.post("/teams/{team_id}/join-requests", status_code=201)
async def submit(team_id: ID, data: JoinInput, actor: CurrentUser, key: Key, session: Session):
    async def execute():
        hackathon_id = await session.scalar(select(Team.hackathon_id).where(Team.id == team_id))
        if hackathon_id is None:
            raise HTTPException(404, "Team not found")
        await participant(session, hackathon_id, actor, lock=True)
        team = await locked_team(session, team_id)
        await ensure_teamless(session, hackathon_id, actor)
        if team.locked_at is not None or team.member_count >= team.max_size:
            raise HTTPException(409, "Team is full or locked")
        existing = await session.scalar(
            select(JoinRequest.id).where(
                JoinRequest.team_id == team_id, JoinRequest.user_id == actor,
                JoinRequest.status == "pending",
            )
        )
        if existing is not None:
            raise HTTPException(409, "You already have a pending request for this team")
        row = JoinRequest(team_id=team_id, user_id=actor, message=data.message)
        session.add(row)
        await session.flush()
        record(session, hackathon_id, team_id, actor, "request.created", request_id=row.id)
        await changed(session, hackathon_id)
        return {"request_id": row.id, "status": "pending"}

    async with session.begin():
        return await once(session, actor, key, f"request:{team_id}", data.model_dump(), execute)


@router.get("/teams/{team_id}/join-requests")
async def pending(
    team_id: ID, actor: CurrentUser, session: Session,
    after: ID | None = None, limit: Annotated[int, Query(ge=1, le=100)] = 100,
):
    team = await session.get(Team, team_id)
    if team is None:
        raise HTTPException(404, "Team not found")
    require_leader(team, actor)
    query = (
        select(JoinRequest, User.display_name)
        .join(User, User.id == JoinRequest.user_id)
        .where(JoinRequest.team_id == team_id, JoinRequest.status == "pending")
        .order_by(JoinRequest.id).limit(limit + 1)
    )
    if after is not None:
        query = query.where(JoinRequest.id > after)
    rows = (await session.execute(query)).all()
    return {
        "requests": [
            {"id": row.id, "user_id": row.user_id, "message": row.message, "display_name": name}
            for row, name in rows[:limit]
        ],
        "next_after": rows[limit - 1][0].id if len(rows) > limit else None,
    }


@router.post("/join-requests/{request_id}/accept")
async def accept(request_id: ID, actor: CurrentUser, key: Key, session: Session):
    async def execute():
        found = await locate(session, request_id)
        enrolled = await participant(session, found.hackathon_id, found.user_id, lock=True)
        team = await locked_team(session, found.team_id)
        require_leader(team, actor)
        return await claim_seat(session, team, enrolled, actor, await lock_pending(session, request_id))

    async with session.begin():
        return await once(session, actor, key, f"accept:{request_id}", {}, execute)


async def decide(session: Session, request_id: int, actor: int, status: str):
    async with session.begin():
        found = await locate(session, request_id)
        team = await locked_team(session, found.team_id)
        if status == "declined":
            require_leader(team, actor)
        elif actor != found.user_id:
            raise HTTPException(403, "Only the requester can cancel")
        row = await lock_pending(session, request_id)
        row.status = status
        row.decided_by = actor
        row.decided_at = func.now()
        record(session, team.hackathon_id, team.id, actor, f"request.{status}", request_id=row.id)
        await changed(session, team.hackathon_id)
    return {"status": status}


@router.post("/join-requests/{request_id}/decline")
async def decline(request_id: ID, actor: CurrentUser, session: Session):
    return await decide(session, request_id, actor, "declined")


@router.delete("/join-requests/{request_id}")
async def cancel(request_id: ID, actor: CurrentUser, session: Session):
    return await decide(session, request_id, actor, "cancelled")
