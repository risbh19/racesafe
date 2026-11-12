import pytest

pytestmark = pytest.mark.asyncio


async def test_board_filters_and_paginates(race):
    (_, first), (_, second), (_, third), (_, reader) = await race.users(4)
    oldest = await race.team(first, "First Team", needed_skills=["Python"])
    await race.team(second, "Second Team", needed_skills=["React"])
    newest = await race.team(third, "Third Team", needed_skills=["Python"])
    path = "/api/hackathons/1/board?skill=python&limit=1"
    first_page = (await race.client.get(path, headers=reader)).json()
    second_page = (await race.client.get(path + f"&before={first_page['next_before']}", headers=reader)).json()
    assert [team["id"] for team in first_page["teams"]] == [newest]
    assert [team["id"] for team in second_page["teams"]] == [oldest]
    assert second_page["next_before"] is None


async def test_people_hides_participants_in_teams(race):
    (leader_id, leader), (available, _), (_, reader) = await race.users(3)
    await race.team(leader)
    response = await race.client.get("/api/hackathons/1/people", headers=reader)
    ids = {person["id"] for person in response.json()["people"]}
    assert available in ids and leader_id not in ids


async def test_suggestions_cover_skill_gap_and_explain_score(race):
    (_, leader), = await race.users(skills=["react"], offset=-720)
    (match, _), = await race.users(skills=["python"], offset=840)
    (_, _), = await race.users(skills=[], offset=0)
    team_id = await race.team(leader, needed_skills=["python"])
    result = (await race.client.get(f"/api/teams/{team_id}/suggestions", headers=leader)).json()
    best = result["suggestions"][0]
    assert best["id"] == match
    assert best["matched_skills"] == ["python"]
    assert 0 <= best["timezone_score"] <= 1
    assert 0 <= best["score"] <= 100
    assert result["weights"] == {"skills": 0.7, "time_zone": 0.3}


async def test_suggestions_find_novel_skills_without_gap(race):
    (_, leader), = await race.users(skills=["react"])
    (candidate, _), = await race.users(skills=["python"])
    team_id = await race.team(leader, needed_skills=["react"])
    result = (await race.client.get(f"/api/teams/{team_id}/suggestions", headers=leader)).json()
    assert result["suggestions"][0]["id"] == candidate
    assert result["suggestions"][0]["matched_skills"] == ["python"]
