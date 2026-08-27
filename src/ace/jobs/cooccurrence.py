import datetime
import logging
from collections import defaultdict

from sqlalchemy.orm import Session

from ace.config import settings
from ace.correlation.signals.cooccurrence import get_alert_type
from ace.db.models.alerts import Alert, AlertTypeStat

logger = logging.getLogger(__name__)


def refresh_cooccurrence_stats(db: Session, window_days: int = 30) -> None:
    """
    Analyzes historical alerts over the given window and populates
    alert_type_stats with co-occurrence counts.

    Excludes alerts with source_tool='constructed' to avoid data contamination.
    """
    logger.info(f"Starting co-occurrence stats refresh for last {window_days} days.")
    now = datetime.datetime.now(datetime.UTC)
    cutoff = now - datetime.timedelta(days=window_days)

    # 1. Fetch all valid alerts in the window, ordered by starts_at
    alerts = (
        db.query(Alert)
        .filter(Alert.starts_at >= cutoff, Alert.source_tool != "constructed")
        .order_by(Alert.starts_at)
        .all()
    )

    if not alerts:
        logger.info("No alerts found in window for co-occurrence analysis.")
        return

    logger.info(f"Loaded {len(alerts)} alerts for co-occurrence analysis.")

    # 2. Calculate co-occurrences using a sliding window
    # co_occurrence_count: how many times A and B fired within CORRELATION_WINDOW
    # confirmed_count: how many times they ended up in the same incident
    co_occurrences: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"co_occurrence_count": 0, "confirmed_count": 0}
    )
    # To avoid double-counting the same pair of alerts, track evaluated pairs
    evaluated_pairs = set()

    for i in range(len(alerts)):
        a1 = alerts[i]
        type1 = get_alert_type(a1)

        # Look ahead for alerts within the correlation window
        for j in range(i + 1, len(alerts)):
            a2 = alerts[j]
            type2 = get_alert_type(a2)

            # Same type co-occurrence is not meaningful for merging different alerts
            if type1 == type2:
                continue

            time_diff = (a2.starts_at - a1.starts_at).total_seconds()
            if time_diff > settings.CORRELATION_WINDOW:
                # Since alerts are ordered by starts_at, we can break early
                break

            pair_id = tuple(sorted([str(a1.id), str(a2.id)]))
            if pair_id in evaluated_pairs:
                continue
            evaluated_pairs.add(pair_id)

            s_type = sorted([type1, type2])
            type_key = (s_type[0], s_type[1])

            co_occurrences[type_key]["co_occurrence_count"] += 1
            if a1.incident_id and a2.incident_id and a1.incident_id == a2.incident_id:
                co_occurrences[type_key]["confirmed_count"] += 1

    # 3. Update database
    # Truncate and rewrite is simplest for this scale, or update existing.
    # Since it's a small table, we can just clear and rewrite for the window.
    db.query(AlertTypeStat).delete()

    stats_objects = []
    for (type_a, type_b), counts in co_occurrences.items():
        if counts["co_occurrence_count"] > 0:
            stat = AlertTypeStat(
                alert_type_a=type_a,
                alert_type_b=type_b,
                co_occurrence_count=counts["co_occurrence_count"],
                confirmed_count=counts["confirmed_count"],
                window_days=window_days,
                updated_at=now,
            )
            stats_objects.append(stat)

    if stats_objects:
        db.add_all(stats_objects)

    db.commit()
    logger.info(f"Finished co-occurrence stats refresh. Inserted {len(stats_objects)} pair stats.")


if __name__ == "__main__":
    from ace.api.deps import SessionLocal

    with SessionLocal() as db_session:
        refresh_cooccurrence_stats(db_session)
