from unittest.mock import patch

import pytest
import redis

from ace.config import settings
from ace.pipeline.damping import check_damping


@pytest.fixture
def redis_client() -> redis.Redis:
    r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
    r.flushdb()
    return r


def test_damping_below_threshold_forwards_unsuppressed(redis_client: redis.Redis) -> None:
    fp = "test-damp-1"

    # Init state (firing)
    res = check_damping(redis_client, fp, "firing")
    assert not res.suppress_notification
    assert res.forward_to_clean

    # 1 flip (resolved)
    res = check_damping(redis_client, fp, "resolved")
    assert not res.suppress_notification

    # 2 flips (firing)
    res = check_damping(redis_client, fp, "firing")
    assert not res.suppress_notification


def test_damping_above_threshold_suppresses(redis_client: redis.Redis) -> None:
    fp = "test-damp-2"

    # Force threshold
    threshold = settings.FLAP_THRESHOLD

    # Init firing
    check_damping(redis_client, fp, "firing")

    for i in range(threshold):
        status = "resolved" if i % 2 == 0 else "firing"
        res = check_damping(redis_client, fp, status)

    # The next flip should exceed threshold
    next_status = "firing" if status == "resolved" else "resolved"
    res = check_damping(redis_client, fp, next_status)

    assert res.suppress_notification
    assert res.forward_to_clean  # ALWAYS forward to clean


@patch("ace.pipeline.damping.time")
def test_damping_sliding_window_clears(mock_time, redis_client: redis.Redis) -> None:
    fp = "test-damp-3"

    threshold = settings.FLAP_THRESHOLD
    current_time = 1000.0
    mock_time.time.return_value = current_time

    # Init firing
    check_damping(redis_client, fp, "firing")

    # Do threshold - 1 flips
    for i in range(threshold - 1):
        status = "resolved" if i % 2 == 0 else "firing"
        current_time += 1.0
        mock_time.time.return_value = current_time
        res = check_damping(redis_client, fp, status)
        assert not res.suppress_notification

    # Advance time past FLAP_WINDOW
    current_time += settings.FLAP_WINDOW + 10.0
    mock_time.time.return_value = current_time

    # Do 2 more flips. If sliding window works, it shouldn't suppress
    next_status = "firing" if status == "resolved" else "resolved"
    res = check_damping(redis_client, fp, next_status)
    assert not res.suppress_notification

    next_status2 = "resolved" if next_status == "firing" else "firing"
    res = check_damping(redis_client, fp, next_status2)
    assert not res.suppress_notification
