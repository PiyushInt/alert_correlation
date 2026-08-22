from typing import Any

from fastapi import APIRouter, Response

from ace.bypass.health import evaluate_state

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(response: Response) -> dict[str, Any]:
    state, pipeline_lag = evaluate_state()

    status_msg = "ready" if state != "BYPASS" else "not_ready"
    if status_msg == "not_ready":
        response.status_code = 503

    return {
        "status": status_msg,
        "state": state,
        "pipeline_lag_seconds": pipeline_lag,
        "bypass_active": state == "BYPASS",
    }
