from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import any_, select

from backend.db import Session
from backend.models import Participant, Team, TeamMember, User
from backend.schemas import ID
from backend.security import CurrentUser
from backend.services.suggestions import score_candidate
from backend.services.teams import participant, require_leader, team_summary

router = APIRouter(prefix="/api")
Limit = Annotated[int, Query(ge=1, le=100)]
SkillFilter = Annotated[str | None, Query(min_length=1, max_length=30)]


def looking_users(hackathon_id: int):
    return (
        select(User.id, User.display_name, User.skills, User.utc_offset_minutes)
        .join(Participant, Participant.user_id == User.id)
        .where(Participant.hackathon_id == hackathon_id, Participant.looking.is_(True))
        .where(~select(TeamMember.team_id).where(
            TeamMember.hackathon_id == hackathon_id, TeamMember.user_id == User.id,
        ).exists())
    )


@router.get("/hackathons/{hackathon_id}/board")
async def board(
    hackathon_id: ID, request: Request, actor: CurrentUser,
    limit: Limit = 20, before: ID | None = None, skill: SkillFilter = None,
):
    cache = request.app.state.board_cache
    sessions = request.app.state.sessions

    async def authorize(session: Session):
        if not cache.has_enrollment(hackathon_id, actor):
            await participant(session, hackathon_id, actor)
            cache.remember_enrollment(hackathon_id, actor)

    if before is not None or skill is not None:
        async with sessions() as session:
            await authorize(session)
            return await board_snapshot(session, hackathon_id, limit, before, skill)

    cached = cache.get(hackathon_id, limit)
    if cached is not None and cache.has_enrollment(hackathon_id, actor):
        return cached
    async with cache.loading:
        async with sessions() as session:
            await authorize(session)
            cached = cache.get(hackathon_id, limit)
            if cached is not None:
                return cached
            generation = cache.generation
            snapshot = await board_snapshot(session, hackathon_id, limit, None, None)
            cache.store(hackathon_id, limit, snapshot, generation)
            return snapshot


async def board_snapshot(session: Session, hackathon_id: int, limit: int, before, skill):
    query = (
        select(Team)
        .where(Team.hackathon_id == hackathon_id, Team.looking,
               Team.locked_at.is_(None), Team.member_count < Team.max_size)
        .order_by(Team.id.desc()).limit(limit + 1)
    )
    if before is not None:
        query = query.where(Team.id < before)
    if skill:
        query = query.where(skill.strip().lower() == any_(Team.needed_skills))
    rows = (await session.scalars(query)).all()
    return JSONResponse({
        "teams": [team_summary(team) for team in rows[:limit]],
        "next_before": rows[limit - 1].id if len(rows) > limit else None,
    }, headers={"Cache-Control": "no-store"})


@router.get("/hackathons/{hackathon_id}/people")
async def people(
    hackathon_id: ID, actor: CurrentUser, session: Session,
    limit: Limit = 20, after: ID | None = None, skill: SkillFilter = None,
):
    await participant(session, hackathon_id, actor)
    query = looking_users(hackathon_id).where(User.id != actor).order_by(User.id).limit(limit + 1)
    if after is not None:
        query = query.where(User.id > after)
    if skill:
        query = query.where(skill.strip().lower() == any_(User.skills))
    rows = (await session.execute(query)).mappings().all()
    return {
        "people": [dict(row) for row in rows[:limit]],
        "next_after": rows[limit - 1]["id"] if len(rows) > limit else None,
    }


@router.get("/teams/{team_id}/suggestions")
async def suggestions(team_id: ID, actor: CurrentUser, session: Session, limit: Limit = 10):
    team = await session.get(Team, team_id)
    if team is None:
        raise HTTPException(404, "Team not found")
    require_leader(team, actor)
    members = await session.execute(
        select(User.skills, User.utc_offset_minutes)
        .join(TeamMember, TeamMember.user_id == User.id).where(TeamMember.team_id == team_id)
    )
    member_rows = members.all()
    current_skills = {skill for skills, _ in member_rows for skill in skills}
    offsets = [offset for _, offset in member_rows]
    needed = set(team.needed_skills)
    candidates = (await session.execute(looking_users(team.hackathon_id))).mappings().all()
    ranked = [
        {**row, **score_candidate(
            row["skills"], row["utc_offset_minutes"], needed, current_skills, offsets,
        )}
        for row in candidates
    ]
    ranked.sort(key=lambda candidate: (-candidate["score"], candidate["id"]))
    return {
        "weights": {"skills": 0.7, "time_zone": 0.3},
        "explanation": "Skills score measures coverage of missing skills, or new skills when there is no gap. Time zone score falls linearly to zero at eight hours of average circular UTC offset distance.",
        "suggestions": ranked[:limit],
    }
