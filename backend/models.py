from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey,
    ForeignKeyConstraint, Identity, Index, Integer, String,
    UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="ck_users_email_lowercase"),
        CheckConstraint(
            "utc_offset_minutes BETWEEN -720 AND 840",
            name="ck_users_utc_offset",
        ),
    )

    id = mapped_column(BigInteger, Identity(), primary_key=True)
    email = mapped_column(String(254), nullable=False, unique=True)
    password_hash = mapped_column(String(255), nullable=False)
    display_name = mapped_column(String(60), nullable=False)
    skills = mapped_column(ARRAY(String(30)), nullable=False, server_default=text("'{}'"))
    utc_offset_minutes = mapped_column(Integer, nullable=False, server_default=text("0"))


class Hackathon(Base):
    __tablename__ = "hackathons"
    __table_args__ = (
        CheckConstraint(
            "min_team_size >= 1 AND max_team_size >= min_team_size",
            name="ck_hackathons_team_size",
        ),
    )

    id = mapped_column(BigInteger, Identity(), primary_key=True)
    name = mapped_column(String(100), nullable=False)
    min_team_size = mapped_column(Integer, nullable=False, server_default=text("2"))
    max_team_size = mapped_column(Integer, nullable=False, server_default=text("4"))


class Participant(Base):
    __tablename__ = "participants"

    hackathon_id = mapped_column(BigInteger, ForeignKey("hackathons.id"), primary_key=True)
    user_id = mapped_column(BigInteger, ForeignKey("users.id"), primary_key=True)
    looking = mapped_column(Boolean, nullable=False, server_default=text("true"))


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("id", "hackathon_id", name="uq_teams_id_hackathon"),
        UniqueConstraint("hackathon_id", "name", name="uq_teams_hackathon_name"),
        ForeignKeyConstraint(
            ["hackathon_id", "leader_id"],
            ["participants.hackathon_id", "participants.user_id"],
            name="fk_teams_leader_participant",
        ),
        CheckConstraint("min_size >= 1 AND max_size >= min_size", name="ck_teams_size"),
        CheckConstraint("member_count BETWEEN 1 AND max_size", name="ck_teams_capacity"),
        CheckConstraint(
            "locked_at IS NULL OR member_count >= min_size",
            name="ck_teams_locked_minimum",
        ),
        Index(
            "ix_teams_board", "hackathon_id", "id",
            postgresql_where=text("looking AND locked_at IS NULL AND member_count < max_size"),
        ),
    )

    id = mapped_column(BigInteger, Identity(), primary_key=True)
    hackathon_id = mapped_column(BigInteger, ForeignKey("hackathons.id"), nullable=False)
    leader_id = mapped_column(BigInteger, nullable=False)
    name = mapped_column(String(40), nullable=False)
    description = mapped_column(String(500), nullable=False, server_default="")
    needed_skills = mapped_column(ARRAY(String(30)), nullable=False, server_default=text("'{}'"))
    min_size = mapped_column(Integer, nullable=False)
    max_size = mapped_column(Integer, nullable=False)
    member_count = mapped_column(Integer, nullable=False, server_default=text("1"))
    looking = mapped_column(Boolean, nullable=False, server_default=text("true"))
    locked_at = mapped_column(DateTime(timezone=True))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (
        UniqueConstraint("hackathon_id", "user_id", name="uq_members_one_team_per_hackathon"),
        ForeignKeyConstraint(
            ["team_id", "hackathon_id"],
            ["teams.id", "teams.hackathon_id"],
            name="fk_members_team_hackathon",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["hackathon_id", "user_id"],
            ["participants.hackathon_id", "participants.user_id"],
            name="fk_members_participant",
        ),
    )

    team_id = mapped_column(BigInteger, primary_key=True)
    user_id = mapped_column(BigInteger, primary_key=True)
    hackathon_id = mapped_column(BigInteger, nullable=False)
    joined_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class InviteCode(Base):
    __tablename__ = "invite_codes"
    __table_args__ = (
        Index("ix_invite_team", "team_id", unique=True, postgresql_where=text("revoked_at IS NULL")),
    )

    code_hash = mapped_column(String(64), primary_key=True)
    team_id = mapped_column(BigInteger, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    created_by = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    expires_at = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at = mapped_column(DateTime(timezone=True))


class JoinRequest(Base):
    __tablename__ = "join_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'cancelled')",
            name="ck_join_request_status",
        ),
        Index("ix_join_pending", "team_id", "user_id", unique=True,
              postgresql_where=text("status = 'pending'")),
        Index("ix_join_user", "user_id", "id"),
    )

    id = mapped_column(BigInteger, Identity(), primary_key=True)
    team_id = mapped_column(BigInteger, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    user_id = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    message = mapped_column(String(300), nullable=False, server_default="")
    status = mapped_column(String(10), nullable=False, server_default="pending")
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    decided_at = mapped_column(DateTime(timezone=True))
    decided_by = mapped_column(BigInteger, ForeignKey("users.id"))


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    user_id = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    key = mapped_column(String(100), primary_key=True)
    request_hash = mapped_column(String(64), nullable=False)
    response = mapped_column(JSONB)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_team", "hackathon_id", "team_id", "id"),)

    id = mapped_column(BigInteger, Identity(), primary_key=True)
    hackathon_id = mapped_column(BigInteger, nullable=False)
    team_id = mapped_column(BigInteger, nullable=False)
    actor_id = mapped_column(BigInteger, nullable=False)
    action = mapped_column(String(40), nullable=False)
    details = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
