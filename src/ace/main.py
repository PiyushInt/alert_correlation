import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ace.api.components import router as components_router
from ace.api.dependency_map import router as dependency_map_router
from ace.api.health import router as health_router
from ace.api.incidents import router as incidents_router
from ace.api.metrics import router as metrics_router
from ace.api.webhooks.alertmanager import router as alertmanager_router
from ace.api.webhooks.zabbix import router as zabbix_router
from ace.bypass.canary import run_canary_loop
from ace.config import settings
from ace.dependency.otlp import router as otlp_router
from ace.jobs.graph_refresh import graph_refresh_loop
from ace.logging import setup_logging

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Initialize components if not exist (using the first-seen timestamp logic in the repo)
    # Placeholder for any synchronous init if needed
    pass

    # Start background jobs
    canary_task = None
    if settings.CANARY_ENABLED:
        canary_task = asyncio.create_task(run_canary_loop())

    graph_task = asyncio.create_task(graph_refresh_loop())

    yield

    if canary_task:
        canary_task.cancel()
        try:
            await canary_task
        except asyncio.CancelledError:
            pass

    if graph_task:
        graph_task.cancel()
        try:
            await graph_task
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    app = FastAPI(title="Alert Correlation Engine", version="0.1.0", lifespan=lifespan)

    app.include_router(health_router)
    app.include_router(alertmanager_router, prefix="/webhooks/alertmanager")
    app.include_router(zabbix_router, prefix="/webhooks/zabbix")
    app.include_router(components_router, prefix="/components", tags=["components"])
    app.include_router(dependency_map_router, prefix="/dependencies", tags=["dependencies"])
    app.include_router(incidents_router, prefix="/incidents", tags=["incidents"])
    app.include_router(metrics_router, tags=["metrics"])
    app.include_router(otlp_router)  # mounted at /v1/traces natively

    return app


app = create_app()
