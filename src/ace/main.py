import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ace.api.health import router as health_router
from ace.api.webhooks.alertmanager import router as alertmanager_router
from ace.bypass.canary import run_canary_loop
from ace.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    canary_task = None
    if settings.CANARY_ENABLED:
        canary_task = asyncio.create_task(run_canary_loop())

    yield

    if canary_task:
        canary_task.cancel()
        try:
            await canary_task
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    app = FastAPI(title="Alert Correlation Engine", version="0.1.0", lifespan=lifespan)

    app.include_router(health_router)
    app.include_router(alertmanager_router, prefix="/webhooks/alertmanager")

    return app


app = create_app()
