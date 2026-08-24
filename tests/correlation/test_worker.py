import time
import uuid

import fakeredis

from ace.correlation.window import add_open_incident, get_open_incidents


def test_window_state_survives_worker_restart():
    """
    Test: If correlation_worker restarts mid-window, do open incidents survive?
    Yes, because they are held in a Redis Sorted Set.
    """
    r = fakeredis.FakeRedis()

    incident_1 = uuid.uuid4()
    incident_2 = uuid.uuid4()

    # Add incidents using worker 1
    add_open_incident(r, incident_1)
    add_open_incident(r, incident_2)

    # "Restart" worker (we use the same Redis instance but pretend it's a new worker)
    # The new worker calls get_open_incidents()
    open_incidents = get_open_incidents(r)

    assert len(open_incidents) == 2
    assert incident_1 in open_incidents
    assert incident_2 in open_incidents

    # Test expiration
    # We artificially change the score of incident_1 to be in the past
    r.zadd("ace_open_incidents", {str(incident_1): time.time() - 100})

    open_incidents_after_expiry = get_open_incidents(r)
    assert len(open_incidents_after_expiry) == 1
    assert incident_2 in open_incidents_after_expiry
