from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from backend.db import Session
from backend.models import JoinRequest, Participant, PendingRegistration, Team, TeamMember, User
from backend.schemas import Login, ProfileEdit, Register, VerifyEmail, normalized_skills
from backend.security import CurrentUser, client_ip, hash_password, issue_token, verify_password
from backend.services import verification
from backend.services.audit import changed
from backend.services.teams import participant, team_summary

router = APIRouter(prefix="/api")


def public_profile(user: User) -> dict:
    return {
        "id": user.id, "display_name": user.display_name,
        "skills": user.skills, "utc_offset_minutes": user.utc_offset_minutes,
    }


async def create_account(session: Session, hackathon_id: int, email: str, registration: dict):
    user_id = await session.scalar(
        insert(User).values(email=email, **registration)
        .on_conflict_do_nothing(index_elements=["email"]).returning(User.id)
    )
    if user_id is not None:
        session.add(Participant(hackathon_id=hackathon_id, user_id=user_id))
        await changed(session, hackathon_id)
    return user_id


@router.post("/auth/register", status_code=201)
async def register(data: Register, request: Request, session: Session):
    state = request.app.state
    settings = state.settings
    state.limiter.take("register", client_ip(request), limit=20)
    if settings.require_email_verification:
        state.limiter.take("register-email", data.email, limit=3, seconds=900)

    async with state.login_slots:
        registration = {
            "password_hash": await hash_password(data.password),
            "display_name": data.display_name,
            "skills": normalized_skills(data.skills),
            "utc_offset_minutes": data.utc_offset_minutes,
        }
        if not settings.require_email_verification:
            async with session.begin():
                user_id = await create_account(session, settings.hackathon_id, data.email, registration)
            if user_id is None:
                raise HTTPException(409, "An account with this email already exists")
            return {"access_token": issue_token(request, user_id), "token_type": "bearer"}

        token = verification.new_token()
        token_hash = verification.digest_token(token)
        async with session.begin():
            exists = await session.scalar(select(User.id).where(User.email == data.email))
            if exists is None:
                await session.execute(delete(PendingRegistration).where(
                    PendingRegistration.expires_at <= func.clock_timestamp(),
                ))
                await session.execute(insert(PendingRegistration).values(
                    email=data.email, token_hash=token_hash,
                    expires_at=datetime.now(timezone.utc) + verification.TOKEN_LIFETIME,
                    registration=registration,
                ))

    if exists is None:
        try:
            await verification.send_verification(settings, data.email, token)
        except verification.VerificationDeliveryError:
            async with session.begin():
                await session.execute(delete(PendingRegistration).where(
                    PendingRegistration.token_hash == token_hash,
                ))
            raise HTTPException(503, "Verification email could not be sent. Please try again.") from None
    return JSONResponse({"verification_required": True}, status_code=202)


@router.post("/auth/verify-email")
async def verify_email(data: VerifyEmail, request: Request, session: Session):
    state = request.app.state
    if not state.settings.require_email_verification:
        raise HTTPException(404, "Email verification is unavailable")
    state.limiter.take("verify-email-ip", client_ip(request), limit=40)
    token_hash = verification.digest_token(data.token)
    state.limiter.take("verify-email-token", token_hash, limit=10)
    invalid = "This link or signup password is invalid. Request a new link if it expired."
    active_link = (
        PendingRegistration.token_hash == token_hash,
        PendingRegistration.expires_at > func.clock_timestamp(),
    )
    async with state.login_slots:
        async with session.begin():
            registration = await session.scalar(select(PendingRegistration.registration).where(*active_link))
        digest = registration["password_hash"] if registration else state.dummy_password_hash
        if not await verify_password(data.password, digest) or registration is None:
            raise HTTPException(400, invalid)

        async with session.begin():
            email = await session.scalar(
                delete(PendingRegistration).where(*active_link).returning(PendingRegistration.email)
            )
            if email is None:
                raise HTTPException(400, invalid)
            user_id = await create_account(session, state.settings.hackathon_id, email, registration)
        if user_id is None:
            raise HTTPException(400, invalid)
    return {"access_token": issue_token(request, user_id), "token_type": "bearer"}


@router.post("/auth/login")
async def login(data: Login, request: Request, session: Session):
    limiter = request.app.state.limiter
    limiter.take("login-ip", client_ip(request), limit=40)
    limiter.take("login-email", data.email, limit=10)
    async with request.app.state.login_slots:
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
