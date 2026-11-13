import asyncio
import secrets
from contextlib import suppress
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.config import Settings, get_settings
from backend.db import make_engine
from backend.routers import auth, board, events, join_requests, teams
from backend.security import RateLimiter, hash_password
from backend.services.board_cache import BoardCache


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.dummy_password_hash = await hash_password(secrets.token_hex(16))
    listener = asyncio.create_task(app.state.events.listen())
    try:
        yield
    finally:
        listener.cancel()
        with suppress(asyncio.CancelledError):
            await listener
        await app.state.engine.dispose()


async def health(request: Request):
    try:
        async with request.app.state.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError) as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ok", "database": "connected"}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="RaceSafe API", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = make_engine(settings)
    app.state.sessions = async_sessionmaker(app.state.engine, expire_on_commit=False)
    app.state.secret = settings.jwt_secret.get_secret_value() if settings.jwt_secret else secrets.token_hex(32)
    app.state.limiter = RateLimiter()
    app.state.login_slots = asyncio.Semaphore(min(settings.login_concurrency, settings.database_pool_size - 1))
    app.state.board_cache = BoardCache()
    app.state.events = events.Events(settings.listener_dsn(), app.state.board_cache.invalidate)
    app.add_api_route("/api/health", health, methods=["GET"])
    for router in (auth.router, teams.router, join_requests.router, board.router, events.router):
        app.include_router(router)

    @app.exception_handler(IntegrityError)
    async def constraint_error(_request: Request, exc: IntegrityError):
        if getattr(exc.orig, "sqlstate", None) == "23505":
            return JSONResponse(status_code=409, content={"detail": "This change conflicts with existing data"})
        raise exc

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"detail": [
            {"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
            for error in exc.errors()
        ]})

    dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    if (dist / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        async def frontend():
            return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
