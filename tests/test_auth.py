import asyncio

import pytest
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.routers import auth

pytestmark = pytest.mark.asyncio
ACCOUNT = {"email": "builder@example.test", "password": "long-enough-password", "display_name": "Builder"}


async def test_health(race):
    response = await race.client.get("/api/health")
    assert response.json() == {"status": "ok", "database": "connected"}


async def test_register_and_read_profile(race):
    registered = await race.client.post("/api/auth/register", json=ACCOUNT)
    assert registered.status_code == 201
    token = registered.json()["access_token"]
    me = await race.client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == ACCOUNT["email"]
    assert "password_hash" not in me.json()


async def test_duplicate_email_is_case_insensitive(race):
    assert (await race.client.post("/api/auth/register", json=ACCOUNT)).status_code == 201
    second = await race.client.post("/api/auth/register", json={**ACCOUNT, "email": ACCOUNT["email"].upper()})
    assert second.status_code == 409


async def test_login(race):
    await race.client.post("/api/auth/register", json=ACCOUNT)
    response = await race.client.post("/api/auth/login", json={
        "email": ACCOUNT["email"], "password": ACCOUNT["password"],
    })
    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_login_releases_connection_before_password_check(race, monkeypatch):
    assert (await race.client.post("/api/auth/register", json=ACCOUNT)).status_code == 201
    verify_password = auth.verify_password

    async def verify_without_connection(password, digest):
        assert race.app.state.engine.pool.checkedout() == 0
        return await verify_password(password, digest)

    monkeypatch.setattr(auth, "verify_password", verify_without_connection)
    response = await race.client.post("/api/auth/login", json={
        "email": ACCOUNT["email"], "password": ACCOUNT["password"],
    })
    assert response.status_code == 200


async def test_login_pool_timeout_returns_retryable_response(race, monkeypatch):
    async def time_out(_session, _statement):
        raise PoolTimeoutError("Test pool timeout")

    monkeypatch.setattr(AsyncSession, "execute", time_out)
    response = await race.client.post("/api/auth/login", json={
        "email": ACCOUNT["email"], "password": ACCOUNT["password"],
    })
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    assert response.json() == {"detail": "Sign-in is busy. Try again shortly."}


async def test_login_bounds_simultaneous_password_checks(race, monkeypatch):
    assert (await race.client.post("/api/auth/register", json=ACCOUNT)).status_code == 201
    limit = race.app.state.settings.login_concurrency
    saturated = asyncio.Event()
    release = asyncio.Event()
    active = peak = 0

    async def verify(_password, _digest):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        if active == limit:
            saturated.set()
        try:
            await release.wait()
            return True
        finally:
            active -= 1

    monkeypatch.setattr(auth, "verify_password", verify)
    payload = {"email": ACCOUNT["email"], "password": ACCOUNT["password"]}
    requests = [
        asyncio.create_task(race.client.post("/api/auth/login", json=payload))
        for _ in range(limit + 1)
    ]
    try:
        await asyncio.wait_for(saturated.wait(), timeout=5)
        assert peak == limit
    finally:
        release.set()
        results = await asyncio.gather(*requests, return_exceptions=True)
    assert all(result.status_code == 200 for result in results)
    assert peak == limit


async def test_bad_login(race):
    await race.client.post("/api/auth/register", json=ACCOUNT)
    response = await race.client.post("/api/auth/login", json={
        "email": ACCOUNT["email"], "password": "wrong",
    })
    assert response.status_code == 401


async def test_bad_registration_does_not_echo_password(race):
    response = await race.client.post("/api/auth/register", json={**ACCOUNT, "password": "bad123"})
    assert response.status_code == 422
    assert "bad123" not in response.text


async def test_authentication_required(race):
    assert (await race.client.get("/api/me")).status_code == 401


async def test_update_profile(race):
    (_, headers), = await race.users()
    response = await race.client.patch("/api/me", headers=headers, json={
        "display_name": "Updated", "skills": [" PYTHON ", "python"],
        "utc_offset_minutes": 330, "looking": False,
    })
    assert response.status_code == 200
    profile = (await race.client.get("/api/me", headers=headers)).json()
    assert (profile["skills"], profile["utc_offset_minutes"], profile["looking"]) == (["python"], 330, False)
