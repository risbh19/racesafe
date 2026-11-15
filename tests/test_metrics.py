import pytest
from pydantic import SecretStr


@pytest.mark.asyncio
async def test_metrics_token_and_bounded_route_labels(race):
    secret = "metrics-test-token-with-at-least-32-characters"
    race.app.state.settings.metrics_token = SecretStr(secret)
    (_, actor), = await race.users()
    await race.client.get("/api/teams/99887766", headers=actor)
    assert (await race.client.get("/metrics")).status_code == 401
    response = await race.client.get("/metrics", headers={"Authorization": f"Bearer {secret}"})
    assert response.status_code == 200
    assert 'racesafe_http_requests_total{method="GET",route="/api/teams/{team_id}",status="404"} 1.0' in response.text
    assert 'racesafe_http_response_start_seconds_count' in response.text
    assert 'racesafe_sse_subscribers 0.0' in response.text
    assert "99887766" not in response.text
