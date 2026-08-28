import datetime
import uuid
from unittest.mock import MagicMock

import pytest

from ace.db.models.alerts import Alert
from ace.db.models.incidents import Incident, IncidentAlert
from ace.ranking.ranker import rank_root_cause_candidates


def test_ranker_no_members():
    db = MagicMock()
    db.query().filter().all.return_value = []

    incident = Incident(id=uuid.uuid4())
    rank_root_cause_candidates(db, incident, datetime.datetime.now(datetime.UTC))

    db.add.assert_not_called()
    db.commit.assert_not_called()
    assert incident.root_cause_component_id is None


def test_ranker_timing_and_direction():
    db = MagicMock()
    incident_id = uuid.uuid4()
    incident = Incident(id=incident_id)

    comp1 = uuid.uuid4()
    comp2 = uuid.uuid4()

    now = datetime.datetime.now(datetime.UTC)

    alert1 = Alert(
        id=uuid.uuid4(), component_id=comp1, starts_at=now - datetime.timedelta(minutes=5)
    )
    alert2 = Alert(
        id=uuid.uuid4(), component_id=comp2, starts_at=now - datetime.timedelta(minutes=2)
    )

    def mock_db_query(model):
        m = MagicMock()
        if model == IncidentAlert:
            m.filter.return_value.all.return_value = [
                IncidentAlert(alert_id=alert1.id),
                IncidentAlert(alert_id=alert2.id),
            ]
        elif model == Alert:
            m.filter.return_value.all.return_value = [alert1, alert2]
        return m

    db.query.side_effect = mock_db_query

    with pytest.MonkeyPatch.context() as monkeypatch:
        from ace.ranking import ranker

        mock_graph = MagicMock()
        mock_graph.neighbours_within.return_value = set()
        monkeypatch.setattr(ranker, "graph_instance", mock_graph)

        mock_reachability = MagicMock()

        def side_effect(source, target):
            if source == target:
                return (0, "self", [source])
            return None

        mock_reachability.get_shortest_path.side_effect = side_effect
        monkeypatch.setattr(ranker, "reachability", mock_reachability)

        rank_root_cause_candidates(db, incident, now)

        assert db.add.call_count == 2
        db.commit.assert_called_once()

        added_candidates = [call.args[0] for call in db.add.call_args_list]
        added_candidates.sort(key=lambda c: c.rank)

        # comp1 is self (2.0 base) + 2.0 (fired) + 5.0 (earliest) = 9.0
        # comp2 is self (2.0 base) + 2.0 (fired) = 4.0

        assert added_candidates[0].component_id == comp1
        assert added_candidates[1].component_id == comp2

        assert added_candidates[0].evidence["is_earliest_alert"] is True
        assert added_candidates[1].evidence["is_earliest_alert"] is False

        assert added_candidates[0].uncertain is True  # self, 0 hops
        assert added_candidates[1].uncertain is True  # self, 0 hops

        assert incident.root_cause_component_id == comp1


def test_ranker_graph_traversal_and_uncertainty():
    db = MagicMock()
    incident_id = uuid.uuid4()
    incident = Incident(id=incident_id)

    comp1 = uuid.uuid4()  # Centroid component (fired alert)
    comp3 = uuid.uuid4()  # Discovered component (upstream cause, no alert)

    now = datetime.datetime.now(datetime.UTC)

    alert1 = Alert(
        id=uuid.uuid4(), component_id=comp1, starts_at=now - datetime.timedelta(minutes=5)
    )

    def mock_db_query(model):
        m = MagicMock()
        if model == IncidentAlert:
            m.filter.return_value.all.return_value = [
                IncidentAlert(alert_id=alert1.id),
            ]
        elif model == Alert:
            m.filter.return_value.all.return_value = [alert1]
        return m

    db.query.side_effect = mock_db_query

    with pytest.MonkeyPatch.context() as monkeypatch:
        from ace.ranking import ranker

        mock_graph = MagicMock()
        mock_graph.neighbours_within.return_value = {comp3}
        monkeypatch.setattr(ranker, "graph_instance", mock_graph)

        mock_reachability = MagicMock()

        def side_effect(source, target):
            if source == target:
                return (0, "self", [source])
            if source == comp3 and target == comp1:
                return (1, "inbound", [comp3, comp1])
            return None

        mock_reachability.get_shortest_path.side_effect = side_effect
        monkeypatch.setattr(ranker, "reachability", mock_reachability)

        rank_root_cause_candidates(db, incident, now)

        assert db.add.call_count == 2

        added_candidates = [call.args[0] for call in db.add.call_args_list]
        added_candidates.sort(key=lambda c: c.rank)

        # comp3 is inbound (20.0 base) - 2.0 (1 hop) = 18.0
        # comp1 is self (2.0 base) + 2.0 (fired) + 5.0 (earliest) = 9.0

        assert added_candidates[0].component_id == comp3
        assert added_candidates[1].component_id == comp1

        assert added_candidates[0].uncertain is False  # Traversed (inbound, 1 hop)
        assert added_candidates[1].uncertain is True  # self, 0 hops

        assert incident.root_cause_component_id == comp3
