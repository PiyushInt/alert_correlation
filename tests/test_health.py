from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

from ace.main import app

client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@patch("ace.api.health.psycopg.connect")
@patch("ace.api.health.redis.from_url")
def test_ready_check_dependencies_down(mock_redis: Any, mock_conn: Any) -> None:
    mock_conn.side_effect = Exception("DB down")
    mock_redis.side_effect = Exception("Redis down")

    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["dependencies"] == {"postgres": "down", "redis": "down"}


@patch("ace.api.health.psycopg.connect")
@patch("ace.api.health.redis.from_url")
def test_ready_check_dependencies_up(mock_redis: Any, mock_conn: Any) -> None:
    mock_cursor = mock_conn.return_value.__enter__.return_value.cursor
    mock_cursor.return_value.__enter__.return_value.execute.return_value = None
    mock_redis.return_value.ping.return_value = True

    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["dependencies"] == {"postgres": "up", "redis": "up"}
