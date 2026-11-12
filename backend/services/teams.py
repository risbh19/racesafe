from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Hackathon, JoinRequest, Participant, Team, TeamMember
from backend.schemas import TeamInput, normalized_skills
from backend.services.audit import changed, record


async def participant(
    session: AsyncSession, hackathon_id: int, user_id: int, *, lock: bool = False,
) -> Participant:
    statement = select(Participant).where(
        Participant.hackathon_id == hackathon_id, Participant.user_id == user_id,
    )
    if lock:
        # NO KEY UPDATE serializes this participant's writes and permits FK checks.
        statement = statement.with_for_update(key_share=True)
    row = await session.scalar(statement)
    if row is None:
        raise HTTPException(403, "You are not registered for this hackathon")
    return row


async def locked_team(session: AsyncSession, team_id: int) -> Team:
    team = await session.scalar(select(Team).where(Team.id == team_id).with_for_update())
    if team is None:
        raise HTTPException(404, "Team not found")
    return team


def require_leader(team: Team, actor: int) -> None:
    if team.leader_id != actor:
        raise HTTPException(403, "Only the team leader can do that")


async def ensure_teamless(session: AsyncSession, hackathon_id: int, user_id: int) -> None:
    team_id = await session.scalar(
        select(TeamMember.team_id).where(
            TeamMember.hackathon_id == hackathon_id, TeamMember.user_id == user_id,
        )
    )
    if team_id is not None:
        raise HTTPException(409, "You already belong to a team in this hackathon")


async def cancel_other_requests(
    session: AsyncSession, hackathon_id: int, user_id: int, actor: int,
    accepted_request_id: int | None = None,
) -> None:
    filters = [
        JoinRequest.user_id == user_id, JoinRequest.status == "pending",
        JoinRequest.team_id.in_(select(Team.id).where(Team.hackathon_id == hackathon_id)),
    ]
    if accepted_request_id is not None:
        filters.append(JoinRequest.id != accepted_request_id)
    rows = await session.execute(
        update(JoinRequest).where(*filters)
        .values(status="cancelled", decided_at=func.now(), decided_by=actor)
        .returning(JoinRequest.id, JoinRequest.team_id)
    )
    for request_id, team_id in rows:
        record(session, hackathon_id, team_id, actor, "request.cancelled", request_id=request_id)


async def create_team(
    session: AsyncSession, hackathon_id: int, actor: int, data: TeamInput,
) -> dict:
    enrolled = await participant(session, hackathon_id, actor, lock=True)
    await ensure_teamless(session, hackathon_id, actor)
    hackathon = await session.get(Hackathon, hackathon_id)
    team = Team(
        hackathon_id=hackathon_id, leader_id=actor, name=data.name,
        description=data.description, needed_skills=normalized_skills(data.needed_skills),
        looking=data.looking, min_size=hackathon.min_team_size, max_size=hackathon.max_team_size,
    )
    session.add(team)
    await session.flush()
    session.add(TeamMember(team_id=team.id, hackathon_id=hackathon_id, user_id=actor))
    enrolled.looking = False
    await cancel_other_requests(session, hackathon_id, actor, actor)
    record(session, hackathon_id, team.id, actor, "team.created")
    await changed(session, hackathon_id)
    return {"team_id": team.id, "member_count": 1}


async def claim_seat(
    session: AsyncSession, team: Team, enrolled: Participant, actor: int,
    request: JoinRequest | None = None,
) -> dict:
    user_id = enrolled.user_id
    await ensure_teamless(session, team.hackathon_id, user_id)
    member_count = await session.scalar(
        update(Team)
        .where(Team.id == team.id, Team.member_count < Team.max_size, Team.locked_at.is_(None))
        .values(member_count=Team.member_count + 1)
        .returning(Team.member_count)
    )
    if member_count is None:
        raise HTTPException(409, "Team is full or locked")

    session.add(TeamMember(team_id=team.id, hackathon_id=team.hackathon_id, user_id=user_id))
    enrolled.looking = False
    if request is not None:
        request.status = "accepted"
        request.decided_at = func.now()
        request.decided_by = actor
        record(session, team.hackathon_id, team.id, actor, "request.accepted", request_id=request.id)
    await cancel_other_requests(
        session, team.hackathon_id, user_id, actor, request.id if request else None,
    )
    record(session, team.hackathon_id, team.id, actor, "member.joined", user_id=user_id)
    await changed(session, team.hackathon_id)
    return {"team_id": team.id, "member_count": member_count}


async def remove_member(
    session: AsyncSession, team: Team, enrolled: Participant, actor: int,
) -> dict:
    user_id = enrolled.user_id
    member = await session.get(TeamMember, (team.id, user_id))
    if member is None:
        raise HTTPException(404, "Team member not found")
    enrolled.looking = True
    action = "member.left" if user_id == actor else "member.removed"
    record(session, team.hackathon_id, team.id, actor, action, user_id=user_id)

    if team.member_count == 1:
        record(session, team.hackathon_id, team.id, actor, "team.deleted")
        await session.delete(team)
        await changed(session, team.hackathon_id)
        return {"deleted": True, "leader_id": None}

    await session.delete(member)
    await session.flush()
    team.member_count -= 1
    if team.member_count < team.min_size and team.locked_at is not None:
        team.locked_at = None
        record(session, team.hackathon_id, team.id, actor, "team.reopened")

    if team.leader_id == user_id:
        team.leader_id = await session.scalar(
            select(TeamMember.user_id).where(TeamMember.team_id == team.id)
            .order_by(TeamMember.joined_at, TeamMember.user_id).limit(1)
        )
        record(session, team.hackathon_id, team.id, actor, "leader.changed", leader_id=team.leader_id)

    await changed(session, team.hackathon_id)
    return {"deleted": False, "leader_id": team.leader_id}


def team_summary(team: Team) -> dict:
    return {
        "id": team.id, "name": team.name, "description": team.description,
        "hackathon_id": team.hackathon_id, "leader_id": team.leader_id,
        "min_size": team.min_size, "max_size": team.max_size, "member_count": team.member_count,
        "needed_skills": team.needed_skills, "looking": team.looking,
        "locked": team.locked_at is not None,
    }
