import pytest
import redis

from ace.config import settings
from ace.queue.consumer import (
    ack_message,
    dead_letter,
    ensure_consumer_group,
    read_batch,
    reclaim_pending,
)


@pytest.fixture
def redis_client() -> redis.Redis:
    r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
    r.flushdb()
    return r


def test_ensure_consumer_group_idempotent(redis_client: redis.Redis) -> None:
    stream = "test.stream"
    group = "test.group"

    # First time creates it
    ensure_consumer_group(redis_client, stream, group)
    groups = redis_client.xinfo_groups(stream)
    assert len(groups) == 1
    assert groups[0]["name"].decode("utf-8") == group

    # Second time shouldn't raise error
    ensure_consumer_group(redis_client, stream, group)


def test_read_and_ack(redis_client: redis.Redis) -> None:
    stream = "test.stream"
    group = "test.group"
    consumer = "c1"

    ensure_consumer_group(redis_client, stream, group)

    # Add messages
    redis_client.xadd(stream, {"k1": "v1"})
    redis_client.xadd(stream, {"k2": "v2"})

    # Read them
    msgs = read_batch(redis_client, stream, group, consumer, 10, 1)
    assert len(msgs) == 2

    # They should be in PEL
    pel = redis_client.xpending(stream, group)
    assert pel["pending"] == 2

    # Ack them
    for msg in msgs:
        ack_message(redis_client, stream, group, msg.message_id)

    pel = redis_client.xpending(stream, group)
    assert pel["pending"] == 0


def test_reclaim_pending(redis_client: redis.Redis) -> None:
    stream = "test.stream"
    group = "test.group"

    ensure_consumer_group(redis_client, stream, group)
    redis_client.xadd(stream, {"k1": "v1"})

    # Consumer 1 reads it but crashes (doesn't ack)
    read_batch(redis_client, stream, group, "c1", 10, 1)

    # Consumer 2 reclaims it
    # Use 0 for min_idle_ms in test
    reclaimed = reclaim_pending(redis_client, stream, group, "c2", 0)
    assert len(reclaimed) == 1
    assert reclaimed[0].data["k1"] == "v1"


def test_dead_letter(redis_client: redis.Redis) -> None:
    stream = "test.stream"
    group = "test.group"

    ensure_consumer_group(redis_client, stream, group)
    redis_client.xadd(stream, {"bad": "data"})

    msgs = read_batch(redis_client, stream, group, "c1", 10, 1)

    dead_letter(redis_client, msgs[0], "dead.stream")

    dead = redis_client.xread({"dead.stream": "0-0"})
    assert len(dead) == 1
    assert b"bad" in dead[0][1][0][1]
