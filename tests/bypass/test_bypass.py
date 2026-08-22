from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import ace.bypass.canary as canary
from ace.bypass.health import evaluate_state


@patch("ace.bypass.health.psycopg.connect")
@patch("ace.bypass.health.redis.from_url")
def test_evaluate_state_ok(mock_redis, mock_postgres):
    mock_postgres.return_value.__enter__.return_value = True
    mock_redis.return_value.ping.return_value = True

    # Mock lag to be 0
    with patch("ace.bypass.health.get_pipeline_lag", return_value=0):
        # Disable canary check for this test
        with patch("ace.bypass.health.settings.CANARY_ENABLED", False):
            state, lag = evaluate_state()
            assert state == "OK"
            assert lag == 0


@patch("ace.bypass.health.psycopg.connect")
@patch("ace.bypass.health.redis.from_url")
def test_evaluate_state_redis_down(mock_redis, mock_postgres):
    mock_postgres.return_value.__enter__.return_value = True
    mock_redis.side_effect = Exception("Connection refused")

    with patch("ace.bypass.health.settings.CANARY_ENABLED", False):
        state, lag = evaluate_state()
        assert state == "BYPASS"
        assert lag is None


@patch("ace.bypass.health.psycopg.connect")
@patch("ace.bypass.health.redis.from_url")
def test_evaluate_state_pipeline_lag_exceeded(mock_redis, mock_postgres):
    mock_postgres.return_value.__enter__.return_value = True
    mock_redis.return_value.ping.return_value = True

    with patch("ace.bypass.health.get_pipeline_lag", return_value=400):
        with patch("ace.bypass.health.settings.MAX_PIPELINE_LAG", 300):
            with patch("ace.bypass.health.settings.CANARY_ENABLED", False):
                state, lag = evaluate_state()
                assert state == "BYPASS"
                assert lag == 400


@patch("ace.bypass.health.psycopg.connect")
@patch("ace.bypass.health.redis.from_url")
def test_evaluate_state_canary_stale(mock_redis, mock_postgres):
    mock_postgres.return_value.__enter__.return_value = True
    mock_redis.return_value.ping.return_value = True

    with patch("ace.bypass.health.get_pipeline_lag", return_value=0):
        with patch("ace.bypass.health.settings.CANARY_ENABLED", True):
            with patch("ace.bypass.health.settings.CANARY_TIMEOUT", 120):
                canary.last_canary_time = datetime.now(UTC) - timedelta(seconds=150)
                state, lag = evaluate_state()
                assert state == "BYPASS"
