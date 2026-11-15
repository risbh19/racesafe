import asyncio
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

PASSWORDS = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
BEARER = HTTPBearer(auto_error=False)
INVITE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
TOKEN_ISSUER = "racesafe"


async def hash_password(password: str) -> str:
    return await asyncio.to_thread(PASSWORDS.hash, password)


async def verify_password(password: str, digest: str) -> bool:
    try:
        return await asyncio.to_thread(PASSWORDS.verify, digest, password)
    except (VerificationError, InvalidHashError):
        return False


def issue_token(request: Request, user_id: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id), "iss": TOKEN_ISSUER, "iat": now,
            "exp": now + timedelta(minutes=request.app.state.settings.token_minutes),
        },
        request.app.state.secret, algorithm="HS256",
    )


def authenticate(request: Request, credentials: HTTPAuthorizationCredentials | None):
    try:
        if credentials is None:
            raise ValueError
        claims = jwt.decode(
            credentials.credentials, request.app.state.secret,
            algorithms=["HS256"], issuer=TOKEN_ISSUER,
            options={"require": ["sub", "iss", "exp", "iat"]},
        )
        user_id = int(claims["sub"])
        if not 0 < user_id <= 9223372036854775807:
            raise ValueError
        return user_id, int(claims["exp"])
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(401, "Sign in to continue", {"WWW-Authenticate": "Bearer"}) from None


async def current_user(request: Request, credentials=Depends(BEARER)) -> int:
    return authenticate(request, credentials)[0]


CurrentUser = Annotated[int, Depends(current_user)]


def new_invite() -> str:
    return "".join(secrets.choice(INVITE_ALPHABET) for _ in range(12))


def invite_hash(secret: str, code: str) -> str:
    return hmac.new(secret.encode(), code.encode(), hashlib.sha256).hexdigest()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
