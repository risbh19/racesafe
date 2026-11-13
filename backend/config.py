from functools import lru_cache

from pydantic import Field, HttpUrl, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    database_url: str = "postgresql+asyncpg://racesafe:racesafe_dev@127.0.0.1:5432/racesafe"
    direct_database_url: str | None = None
    jwt_secret: SecretStr | None = Field(default=None, min_length=32)
    require_jwt_secret: bool = False
    database_pool_size: int = Field(default=12, ge=2, le=64)
    login_concurrency: int = Field(default=4, ge=1, le=32)
    token_minutes: int = Field(default=60, ge=5, le=1440)
    hackathon_id: int = Field(default=1, ge=1)
    require_email_verification: bool = False
    public_app_url: HttpUrl | None = None
    resend_api_key: SecretStr | None = None
    verification_from_email: str | None = None

    @model_validator(mode="after")
    def check_required_settings(self):
        if self.require_jwt_secret and self.jwt_secret is None:
            raise ValueError("JWT_SECRET is required")
        if self.require_email_verification:
            url = self.public_app_url
            key = self.resend_api_key
            if not url or not key or not key.get_secret_value().strip() or not (self.verification_from_email or "").strip():
                raise ValueError("Email verification requires PUBLIC_APP_URL, RESEND_API_KEY and VERIFICATION_FROM_EMAIL")
            if url.path not in ("", "/") or url.query or url.fragment or url.username or url.password:
                raise ValueError("PUBLIC_APP_URL must be the app origin")
            if url.scheme != "https" and url.host not in ("localhost", "127.0.0.1"):
                raise ValueError("PUBLIC_APP_URL must use HTTPS outside local development")
        return self

    def database_connection(self, *, direct: bool = False):
        url = make_url(
            (self.direct_database_url or self.database_url) if direct else self.database_url
        ).set(drivername="postgresql+asyncpg")
        sslmode = url.query.get("sslmode")
        args = {"ssl": sslmode} if sslmode else {}
        return url.difference_update_query(["sslmode", "channel_binding"]), args

    def listener_dsn(self) -> str:
        return make_url(self.direct_database_url or self.database_url).set(
            drivername="postgresql"
        ).difference_update_query(["channel_binding"]).render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
