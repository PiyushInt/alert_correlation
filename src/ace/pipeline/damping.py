import logging
import time
from dataclasses import dataclass

import redis

from ace.config import settings
from ace.metrics import registry

logger = logging.getLogger(__name__)


@dataclass
class DampingResult:
    suppress_notification: bool
    forward_to_clean: bool


def check_damping(r: redis.Redis, fingerprint: str, status: str) -> DampingResult:
    """
    Evaluates flap damping using a sliding window.

    Tracks status transitions (flips).
    If flip_count > FLAP_THRESHOLD within FLAP_WINDOW, suppresses notification.
    Always forwards to alerts.clean (correlation needs all events).
    Auto-unsuppresses when the quiet period elapses.
    """
    # Key for the last known status
    status_key = f"damping:status:{fingerprint}"
    # Sorted set key for flip timestamps
    flips_key = f"damping:flips:{fingerprint}"
    # Key indicating if currently suppressed
    suppressed_key = f"damping:suppressed:{fingerprint}"

    now = time.time()

    # 1. Check for state transition
    last_status = r.get(status_key)
    if last_status:
        last_status = (
            last_status.decode("utf-8") if isinstance(last_status, bytes) else str(last_status)
        )

    is_flip = False
    if last_status and last_status != status:
        is_flip = True

    if last_status != status:
        r.set(status_key, status)

    # 2. Record flip if applicable
    if is_flip:
        # value must be unique, so use microsecond timestamp
        member = str(now)
        r.zadd(flips_key, {member: now})

    # 3. Clean up sliding window
    window_start = now - settings.FLAP_WINDOW
    r.zremrangebyscore(flips_key, "-inf", window_start)

    # 4. Count remaining flips in window
    flip_count = r.zcard(flips_key)

    # Set TTL on keys to clean up eventually
    r.expire(status_key, settings.FLAP_WINDOW * 2)
    r.expire(flips_key, settings.FLAP_WINDOW * 2)

    # 5. Evaluate suppression
    currently_suppressed = r.exists(suppressed_key)

    if flip_count > settings.FLAP_THRESHOLD:
        if not currently_suppressed:
            logger.warning(f"Alert flapping detected for {fingerprint} ({flip_count} flips)")
            # Suppress notification for FLAP_WINDOW
            # The TTL naturally handles auto-unsuppress
            r.set(suppressed_key, "1", ex=settings.FLAP_WINDOW)
            currently_suppressed = True
        else:
            # Extend suppression window
            r.expire(suppressed_key, settings.FLAP_WINDOW)

    if currently_suppressed:
        registry.inc_counter("worker_suppressed")
        return DampingResult(suppress_notification=True, forward_to_clean=True)

    return DampingResult(suppress_notification=False, forward_to_clean=True)
