import secrets
from time import perf_counter

from fastapi import HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from starlette.types import ASGIApp, Receive, Scope, Send


class Metrics:
    def __init__(self):
        self.registry = CollectorRegistry()
        self.requests = Counter(
            "racesafe_http_requests", "API responses by route and HTTP status",
            ("method", "route", "status"), registry=self.registry,
        )
        self.latency = Histogram(
            "racesafe_http_response_start_seconds", "Time until the API sends response headers",
            ("method", "route"), registry=self.registry,
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10),
        )
        self.subscribers = Gauge("racesafe_sse_subscribers", "Open live update streams",
                                 registry=self.registry)


class RequestMetrics:
    def __init__(self, app: ASGIApp, metrics: Metrics):
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            await self.app(scope, receive, send)
            return
        started = perf_counter()
        recorded = False

        def record(status: int) -> None:
            nonlocal recorded
            recorded = True
            route = getattr(scope.get("route"), "path", "")
            method = scope["method"]
            if route and method in {"GET", "POST", "PATCH", "DELETE"}:
                self.metrics.requests.labels(method, route, str(status)).inc()
                self.metrics.latency.labels(method, route).observe(perf_counter() - started)

        async def observe(message):
            if message["type"] == "http.response.start":
                record(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, observe)
        except Exception:
            if not recorded:
                record(500)
            raise


async def scrape(request: Request):
    state = request.app.state
    token = state.settings.metrics_token
    if token is not None:
        supplied = request.headers.get("Authorization", "").encode()
        expected = ("Bearer " + token.get_secret_value()).encode()
        if not secrets.compare_digest(supplied, expected):
            raise HTTPException(401, "Metrics token required", {"WWW-Authenticate": "Bearer"})
    elif state.settings.require_jwt_secret:
        raise HTTPException(404)
    metrics = state.metrics
    metrics.subscribers.set(sum(len(queues) for queues in state.events.subscribers.values()))
    return Response(generate_latest(metrics.registry), media_type=CONTENT_TYPE_LATEST,
                    headers={"Cache-Control": "no-store"})
