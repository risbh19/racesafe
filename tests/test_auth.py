import pytest

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
