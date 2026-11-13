from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, field_validator

def validate_database_text(value: str) -> str:
    if "\0" in value:
        raise ValueError("Text cannot contain a NUL character")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("Text must be valid UTF-8") from exc
    return value


DatabaseText = Annotated[str, AfterValidator(validate_database_text)]
ID = Annotated[int, Field(ge=1, le=9223372036854775807)]
Skill = Annotated[DatabaseText, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
Skills = Annotated[list[Skill], Field(max_length=10)]
TimeOffset = Annotated[int, Field(ge=-720, le=840)]
TeamName = Annotated[DatabaseText, StringConstraints(strip_whitespace=True, min_length=3, max_length=40)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Input):
    email: DatabaseText = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class Register(Login):
    password: str = Field(min_length=10, max_length=128)
    display_name: DatabaseText = Field(min_length=2, max_length=60)
    skills: Skills = Field(default_factory=list)
    utc_offset_minutes: TimeOffset = 0

    @field_validator("display_name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class VerifyEmail(Input):
    token: str = Field(min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]{43}$")
    password: str = Field(min_length=10, max_length=128)


class ProfileEdit(Input):
    display_name: Annotated[DatabaseText, StringConstraints(strip_whitespace=True, min_length=2, max_length=60)]
    skills: Skills
    utc_offset_minutes: TimeOffset
    looking: bool


class TeamInput(Input):
    name: TeamName
    description: DatabaseText = Field(default="", max_length=500)
    needed_skills: Skills = Field(default_factory=list)
    looking: bool = True


class InviteInput(Input):
    code: str = Field(pattern=r"^[A-Z2-7]{12}$")

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value):
        return value.strip().upper() if isinstance(value, str) else value


class JoinInput(Input):
    message: DatabaseText = Field(default="", max_length=300)


def normalized_skills(skills: list[str]) -> list[str]:
    return sorted({skill.lower() for skill in skills})
