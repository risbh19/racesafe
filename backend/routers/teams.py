from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import func, select

from backend.db import Session
from backend.models import AuditEvent, JoinRequest, Team, TeamMember, User
from backend.schemas import ID, InviteInput, TeamInput, normalized_skills
from backend.security import CurrentUser, client_ip
from backend.services import invites
from backend.services.audit import changed, record
from backend.services.idempotency import Key, once
from backend.services.teams import (
    create_team, locked_team, participant, remove_member, require_leader, team_summary,
)

router = APIRouter(prefix="/api")


@router.post("/hackathons/{hackathon_id}/teams", status_code=201)
async def create(hackathon_id: ID, data: TeamInput, actor: CurrentUser, key: Key, session: Session):
    async with session.begin():
        return await once(
            session, actor, key, f"create:{hackathon_id}", data.model_dump(mode="json"),
            lambda: create_team(session, hackathon_id, actor, data),
        )


@router.get("/teams/{team_id}")
async def detail(team_id: ID, actor: CurrentUser, session: Session):
    pending_request = select(JoinRequest.id).where(
        JoinRequest.team_id == team_id, JoinRequest.user_id == actor, JoinRequest.status == "pending",
    ).scalar_subquery()
    rows = (
        await session.execute(
            select(Team, User, pending_request)
            .select_from(Team)
            .join(TeamMember, TeamMember.team_id == Team.id)
            .join(User, User.id == TeamMember.user_id)
            .where(Team.id == team_id).order_by(TeamMember.joined_at, TeamMember.user_id)
        )
    ).all()
    if not rows:
        raise HTTPException(404, "Team not found")
    team = rows[0][0]
    await participant(session, team.hackathon_id, actor)
    return {
        **team_summary(team),
        "invite_version": team.invite_version if team.leader_id == actor else None,
        "my_pending_request_id": rows[0][2],
        "members": [
            {"id": user.id, "display_name": user.display_name, "skills": user.skills}
            for _, user, _ in rows
        ],
    }


@router.patch("/teams/{team_id}")
async def edit(team_id: ID, data: TeamInput, actor: CurrentUser, session: Session):
    async with session.begin():
        team = await locked_team(session, team_id)
        require_leader(team, actor)
        fields = data.model_dump()
        fields["needed_skills"] = normalized_skills(data.needed_skills)
        changes = {}
        for field, value in fields.items():
            previous = getattr(team, field)
            if previous != value:
                changes[field] = {"before": previous, "after": value}
                setattr(team, field, value)
        if changes:
            record(session, team.hackathon_id, team_id, actor, "team.updated", changes=changes)
            await changed(session, team.hackathon_id)
    return team_summary(team)


@router.post("/teams/{team_id}/lock")
@router.delete("/teams/{team_id}/lock")
async def set_locked(team_id: ID, request: Request, actor: CurrentUser, session: Session):
    locking = request.method == "POST"
    async with session.begin():
        team = await locked_team(session, team_id)
        require_leader(team, actor)
        if locking and team.member_count < team.min_size:
            raise HTTPException(422, f"At least {team.min_size} members are required to finalize")
        if locking != (team.locked_at is not None):
            team.locked_at = await session.scalar(select(func.clock_timestamp())) if locking else None
            record(
                session, team.hackathon_id, team_id, actor,
                "team.finalized" if locking else "team.reopened",
            )
            await changed(session, team.hackathon_id)
    return team_summary(team)


@router.post("/teams/{team_id}/invite-code", status_code=201)
async def rotate(team_id: ID, request: Request, actor: CurrentUser, session: Session):
    async with session.begin():
        return await invites.rotate_invite(session, team_id, actor, request.app.state.secret)


@router.post("/invites/redeem")
async def redeem(data: InviteInput, request: Request, actor: CurrentUser, key: Key, session: Session):
    async def attempt():
        limiter = request.app.state.limiter
        await limiter.take("invite-ip", client_ip(request), limit=500, seconds=600)
        await limiter.take("invite-user", str(actor), limit=8, seconds=600)
        return await invites.redeem(session, actor, data.code, request.app.state.secret)

    async with session.begin():
        return await once(session, actor, key, "invite.redeem", {"code": data.code}, attempt)


async def change_membership(
    session: Session, team_id: int, actor: int, target: int, leader_only: bool,
):
    async with session.begin():
        hackathon_id = await session.scalar(select(Team.hackathon_id).where(Team.id == team_id))
        if hackathon_id is None:
            raise HTTPException(404, "Team not found")
        enrolled = await participant(session, hackathon_id, target, lock=True)
        team = await locked_team(session, team_id)
        if leader_only:
            require_leader(team, actor)
            if actor == target:
                raise HTTPException(422, "Use Leave team to remove yourself")
        return await remove_member(session, team, enrolled, actor)


@router.delete("/teams/{team_id}/members/me")
async def leave(team_id: ID, actor: CurrentUser, session: Session):
    return await change_membership(session, team_id, actor, actor, False)


@router.delete("/teams/{team_id}/members/{user_id}")
async def remove(team_id: ID, user_id: ID, actor: CurrentUser, session: Session):
    return await change_membership(session, team_id, actor, user_id, True)


@router.get("/teams/{team_id}/audit")
async def audit(
    team_id: ID, actor: CurrentUser, session: Session, before: ID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
):
    member = await session.get(TeamMember, (team_id, actor))
    if member is not None:
        hackathon_id = member.hackathon_id
    else:
        # The last member, who deletes the team by leaving, retains access to its history.
        hackathon_id = await session.scalar(select(AuditEvent.hackathon_id).where(
            AuditEvent.team_id == team_id, AuditEvent.actor_id == actor,
            AuditEvent.action == "team.deleted",
        ))
        if hackathon_id is None:
            raise HTTPException(403, "Only current members or the member who deleted the team can see activity")
    query = (
        select(AuditEvent, User.display_name)
        .outerjoin(User, User.id == AuditEvent.actor_id)
        .where(AuditEvent.hackathon_id == hackathon_id, AuditEvent.team_id == team_id)
        .order_by(AuditEvent.id.desc()).limit(limit + 1)
    )
    if before is not None:
        query = query.where(AuditEvent.id < before)
    rows = (await session.execute(query)).all()
    return {
        "events": [
            {"id": row.id, "actor_id": row.actor_id, "actor_name": actor_name, "action": row.action,
             "details": row.details, "created_at": row.created_at}
            for row, actor_name in rows[:limit]
        ],
        "next_before": rows[limit - 1][0].id if len(rows) > limit else None,
    }
