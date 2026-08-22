import logging
from typing import Any

import redis
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class StreamMessage(BaseModel):
    message_id: str
    data: dict[str, Any]


def ensure_consumer_group(r: redis.Redis, stream: str, group: str) -> None:
    """Creates a consumer group idempotently. If the stream doesn't exist, mkstream creates it."""
    try:
        r.xgroup_create(stream, group, id="0", mkstream=True)
        logger.info(f"Created consumer group '{group}' on stream '{stream}'")
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" in str(e):
            logger.debug(f"Consumer group '{group}' already exists on '{stream}'")
        else:
            raise


def read_batch(
    r: redis.Redis, stream: str, group: str, consumer: str, count: int, block_ms: int
) -> list[StreamMessage]:
    """Reads a batch of new messages using XREADGROUP."""
    try:
        # > means read new messages never delivered to other consumers
        streams = {stream: ">"}
        result = r.xreadgroup(group, consumer, streams, count=count, block=block_ms)  # type: ignore
        if not result:
            return []

        messages = []
        for _stream_name, stream_messages in result:  # type: ignore
            for message_id, data in stream_messages:  # type: ignore
                # Redis returns bytes for keys/values
                decoded_data: dict[str, Any] = {}
                for k, v in data.items():  # type: ignore
                    k_str = k.decode("utf-8") if isinstance(k, bytes) else str(k)
                    v_str = v.decode("utf-8") if isinstance(v, bytes) else str(v)
                    decoded_data[k_str] = v_str

                msg_id_str = (
                    message_id.decode("utf-8") if isinstance(message_id, bytes) else str(message_id)
                )

                messages.append(
                    StreamMessage(
                        message_id=msg_id_str,
                        data=decoded_data,
                    )
                )
        return messages
    except redis.RedisError as e:
        logger.error(f"Error reading from stream '{stream}': {e}")
        return []


def ack_message(r: redis.Redis, stream: str, group: str, message_id: str) -> bool:
    """Acknowledges a message so it's removed from PEL."""
    try:
        result = r.xack(stream, group, message_id)
        return result > 0
    except redis.RedisError as e:
        logger.error(f"Failed to ACK message {message_id} in {stream}: {e}")
        return False


def reclaim_pending(
    r: redis.Redis, stream: str, group: str, consumer: str, min_idle_ms: int, count: int = 10
) -> list[StreamMessage]:
    """Claims pending messages from crashed consumers."""
    try:
        # returns: (next_start_id, list of claimed messages, list of deleted message ids) in Redis 7
        result = r.xautoclaim(stream, group, consumer, min_idle_ms, start_id="0-0", count=count)
        claimed = result[1]
        if not claimed:
            return []

        messages = []
        for message_id, data in claimed:
            if not data:
                # Message was deleted from the stream but not acked?
                continue
            decoded_data = {k.decode("utf-8"): v.decode("utf-8") for k, v in data.items()}
            messages.append(
                StreamMessage(
                    message_id=message_id.decode("utf-8"),
                    data=decoded_data,
                )
            )
        if messages:
            logger.info(f"Reclaimed {len(messages)} pending messages on '{stream}'")
        return messages
    except redis.RedisError as e:
        logger.error(f"Failed to reclaim pending messages on '{stream}': {e}")
        return []


def dead_letter(r: redis.Redis, message: StreamMessage, dead_stream: str = "alerts.dead") -> bool:
    """Moves an unprocessable message to a dead letter stream."""
    try:
        # Cast data dict values to strings to satisfy redis type checker
        safe_data = {k: str(v) for k, v in message.data.items()}
        r.xadd(dead_stream, safe_data)  # type: ignore[arg-type]
        return True
    except redis.RedisError as e:
        logger.error(f"Failed to dead-letter message {message.message_id}: {e}")
        return False
