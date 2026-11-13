import hashlib
import logging
import secrets
from datetime import timedelta

import httpx

from backend.config import Settings

logger = logging.getLogger(__name__)
TOKEN_LIFETIME = timedelta(minutes=30)


class VerificationDeliveryError(Exception):
    """The mail provider could not accept a verification message."""


def new_token() -> str:
    return secrets.token_urlsafe(32)


def digest_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


async def send_verification(settings: Settings, email: str, token: str) -> None:
    link = str(settings.public_app_url).rstrip("/") + "/#verify-email=" + token
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.resend_api_key.get_secret_value()}"},
                json={
                    "from": settings.verification_from_email,
                    "to": [email],
                    "subject": "Verify your RaceSafe email",
                    "text": (
                        "Open this link and enter the password you chose when signing up:\n\n"
                        f"{link}\n\n"
                        "The link expires in 30 minutes and can only be used once. "
                        "If you did not sign up for RaceSafe, ignore this email."
                    ),
                },
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Verification delivery failed (%s)", type(exc).__name__)
        raise VerificationDeliveryError from exc
