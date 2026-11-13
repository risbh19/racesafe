from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from backend.db import Session
from backend.models import JoinRequest, Participant, Team, TeamMember, User
from backend.schemas import Login, ProfileEdit, Register, normalized_skills
from backend.security import CurrentUser, client_ip, hash_password, issue_token, verify_password
from backend.services.audit import changed
from backend.services.teams import participant, team_summary

router = APIRouter(prefix="/api")


def public_profile(user: User) -> dict:
    return {
        "id": user.id, "display_name": user.display_name,
        "skills": user.skills, "utc_offset_minutes": user.utc_offset_minutes,
    }


@router.post("/auth/register", status_code=201)
async def register(data: Register, request: Request, session: Session):
    request.app.state.limiter.take("register", client_ip(request), limit=20)
    password_hash = await hash_password(data.password)
    hackathon_id = request.app.state.settings.hackathon_id
    async with session.begin():
        user_id = await session.scalar(
            insert(User).values(
                email=data.email, password_hash=password_hash, display_name=data.display_name,
                skills=normalized_skills(data.skills), utc_offset_minutes=data.utc_offset_minutes,
            ).on_conflict_do_nothing(index_elements=["email"]).returning(User.id)
        )
        if user_id is None:
            raise HTTPException(409, "An account with this email already exists")
        session.add(Participant(hackathon_id=hackathon_id, user_id=user_id))
        await changed(session, hackathon_id)
    return {"access_token": issue_token(request, user_id), "token_type": "bearer"}


@router.post("/auth/login")
async def login(data: Login, request: Request, session: Session):
    limiter = request.app.state.limiter
    limiter.take("login-ip", client_ip(request), limit=40)
    limiter.take("login-email", data.email, limit=10)
    try:
        # Return the connection before running the expensive password check.
        async with session.begin():
            result = await session.execute(
                select(User.id, User.password_hash).where(User.email == data.email)
            )
            credentials = result.one_or_none()
    except PoolTimeoutError as exc:
        raise HTTPException(
            503, "Sign-in is busy. Try again shortly.", headers={"Retry-After": "1"},
        ) from exc

    user_id, digest = credentials if credentials is not None else (
        None, request.app.state.dummy_password_hash,
    )
    if not await verify_password(data.password, digest) or user_id is None:
        raise HTTPException(401, "Email or password is incorrect")
    return {"access_token": issue_token(request, user_id), "token_type": "bearer"}


@router.get("/me")
async def me(request: Request, actor: CurrentUser, session: Session):
    hackathon_id = request.app.state.settings.hackathon_id
    enrolled = await participant(session, hackathon_id, actor)
    user = await session.get(User, actor)
    team = await session.scalar(
        select(Team).join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.hackathon_id == hackathon_id, TeamMember.user_id == actor)
    )
    requests = await session.execute(
        select(JoinRequest.id, JoinRequest.team_id, Team.name, JoinRequest.status)
        .join(Team, Team.id == JoinRequest.team_id)
        .where(JoinRequest.user_id == actor, Team.hackathon_id == hackathon_id)
        .order_by(JoinRequest.id.desc()).limit(20)
    )
    return {
        **public_profile(user), "email": user.email, "looking": enrolled.looking,
        "hackathon_id": hackathon_id, "team": team_summary(team) if team else None,
        "requests": [
            {"id": rid, "team_id": team_id, "team_name": name, "status": status}
            for rid, team_id, name, status in requests
        ],
    }


@router.patch("/me")
async def edit_profile(data: ProfileEdit, request: Request, actor: CurrentUser, session: Session):
    hackathon_id = request.app.state.settings.hackathon_id
    async with session.begin():
        enrolled = await participant(session, hackathon_id, actor, lock=True)
        user = await session.get(User, actor)
        user.display_name = data.display_name
        user.skills = normalized_skills(data.skills)
        user.utc_offset_minutes = data.utc_offset_minutes
        in_team = await session.scalar(
            select(TeamMember.team_id).where(
                TeamMember.hackathon_id == hackathon_id, TeamMember.user_id == actor,
            )
        )
        enrolled.looking = data.looking and in_team is None
        await changed(session, hackathon_id)
    return {"ok": True}
