from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

from ace.main import app

client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@patch("ace.api.health.evaluate_state")
def test_ready_check_dependencies_down(mock_evaluate_state: Any) -> None:
    mock_evaluate_state.return_value = ("BYPASS", None)

    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["state"] == "BYPASS"
    assert response.json()["bypass_active"] is True


@patch("ace.api.health.evaluate_state")
def test_ready_check_dependencies_up(mock_evaluate_state: Any) -> None:
    mock_evaluate_state.return_value = ("OK", 0)

    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["state"] == "OK"
    assert response.json()["pipeline_lag_seconds"] == 0
    assert response.json()["bypass_active"] is False
