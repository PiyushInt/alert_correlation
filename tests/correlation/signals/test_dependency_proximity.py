import uuid
from unittest.mock import MagicMock

import pytest

from ace.config import settings
from ace.correlation.signals.base import IncidentCentroid
from ace.correlation.signals.dependency_proximity import DependencyProximitySignal
from ace.db.models.alerts import Alert


def test_null_component_id():
    alert = Alert(component_id=None)
    signal = DependencyProximitySignal()
    result = signal.score(alert, MagicMock(), MagicMock(), MagicMock())

    assert result.score == 0.0
    assert not result.evidence["match"]
    assert result.evidence["reason"] == "alert component is null"


def test_stale_map():
    alert = Alert(component_id=uuid.uuid4())
    context = MagicMock()
    context.graph.get_edge_count.return_value = 0

    signal = DependencyProximitySignal()
    result = signal.score(alert, MagicMock(), MagicMock(), context)

    assert result.score == 0.0
    assert not result.evidence["match"]
    assert result.evidence["reason"] == "map is stale/empty"


@pytest.mark.parametrize(
    "direction, expected_weight",
    [
        ("outbound", 1.0),
        ("inbound", 0.6),
    ],
)
def test_direction_weighting_1_hop(direction, expected_weight):
    alert_comp = uuid.uuid4()
    incident_comp = uuid.uuid4()

    alert = Alert(component_id=alert_comp)
    centroid = IncidentCentroid(component_ids={incident_comp})
    context = MagicMock()
    context.graph.get_edge_count.return_value = 5

    # Mock reachability inside the signal module
    with pytest.MonkeyPatch.context() as m:
        from ace.correlation.signals import dependency_proximity

        mock_reach = MagicMock()
        path = (
            [alert_comp, incident_comp] if direction == "outbound" else [incident_comp, alert_comp]
        )
        mock_reach.get_shortest_path.return_value = (1, direction, path)
        m.setattr(dependency_proximity, "reachability", mock_reach)

        # We need to mock get_edge_data to return some path type
        context.graph.get_edge_data.return_value = {"source": "inventory"}

        # Override config weights temporarily
        m.setattr(settings, "PROXIMITY_WEIGHT_OUTBOUND", 1.0)
        m.setattr(settings, "PROXIMITY_WEIGHT_INBOUND", 0.6)

        signal = DependencyProximitySignal()
        result = signal.score(alert, MagicMock(), centroid, context)

        assert result.score == expected_weight
        assert result.evidence["hops"] == 1
        assert result.evidence["direction"] == direction
        assert result.evidence["path_type"] == "inventory"


def test_hop_decay():
    alert_comp = uuid.uuid4()
    incident_comp = uuid.uuid4()

    alert = Alert(component_id=alert_comp)
    centroid = IncidentCentroid(component_ids={incident_comp})
    context = MagicMock()
    context.graph.get_edge_count.return_value = 5

    with pytest.MonkeyPatch.context() as m:
        from ace.correlation.signals import dependency_proximity

        mock_reach = MagicMock()
        mock_reach.get_shortest_path.return_value = (
            2,
            "outbound",
            [alert_comp, uuid.uuid4(), incident_comp],
        )
        m.setattr(dependency_proximity, "reachability", mock_reach)

        context.graph.get_edge_data.return_value = {"source": "inventory"}

        m.setattr(settings, "PROXIMITY_WEIGHT_OUTBOUND", 1.0)
        m.setattr(settings, "PROXIMITY_DECAY_RATE", 0.5)
        m.setattr(settings, "MAX_INCIDENT_HOPS", 3)

        signal = DependencyProximitySignal()
        result = signal.score(alert, MagicMock(), centroid, context)

        # 2 hops -> decay^1 -> 1.0 * 0.5 = 0.5
        assert result.score == 0.5


def test_beyond_max_hops():
    alert_comp = uuid.uuid4()
    incident_comp = uuid.uuid4()

    alert = Alert(component_id=alert_comp)
    centroid = IncidentCentroid(component_ids={incident_comp})
    context = MagicMock()
    context.graph.get_edge_count.return_value = 5

    with pytest.MonkeyPatch.context() as m:
        from ace.correlation.signals import dependency_proximity

        mock_reach = MagicMock()
        mock_reach.get_shortest_path.return_value = (4, "outbound", [alert_comp] * 5)
        m.setattr(dependency_proximity, "reachability", mock_reach)

        m.setattr(settings, "MAX_INCIDENT_HOPS", 3)

        signal = DependencyProximitySignal()
        result = signal.score(alert, MagicMock(), centroid, context)

        assert result.score == 0.0
        assert not result.evidence["match"]
        assert result.evidence["reason"] == "path exceeds max hops"


def test_distance_0_collinearity():
    alert_comp = uuid.uuid4()
    alert = Alert(component_id=alert_comp)
    centroid = IncidentCentroid(component_ids={alert_comp})
    context = MagicMock()
    context.graph.get_edge_count.return_value = 5

    with pytest.MonkeyPatch.context() as m:
        from ace.correlation.signals import dependency_proximity

        mock_reach = MagicMock()
        mock_reach.get_shortest_path.return_value = (0, "self", [alert_comp])
        m.setattr(dependency_proximity, "reachability", mock_reach)

        signal = DependencyProximitySignal()
        result = signal.score(alert, MagicMock(), centroid, context)

        assert result.score == 0.0
        assert not result.evidence["match"]
        assert result.evidence["reason"] == "same component; deferred to same_component signal"
