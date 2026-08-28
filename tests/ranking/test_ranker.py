import datetime
import uuid
from unittest.mock import MagicMock

import pytest

from ace.db.models.alerts import Alert
from ace.db.models.incidents import Incident, IncidentAlert, RootCauseCandidate
from ace.ranking.ranker import rank_root_cause_candidates


def test_ranker_no_members():
    db = MagicMock()
    db.query().filter().all.return_value = []
    
    incident = Incident(id=uuid.uuid4())
    rank_root_cause_candidates(db, incident, datetime.datetime.now(datetime.UTC))
    
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_ranker_logic():
    db = MagicMock()
    incident_id = uuid.uuid4()
    incident = Incident(id=incident_id)
    
    comp1 = uuid.uuid4()
    comp2 = uuid.uuid4()
    comp3 = uuid.uuid4()
    
    now = datetime.datetime.now(datetime.UTC)
    
    # 2 members, components comp1 and comp2
    alert1 = Alert(id=uuid.uuid4(), component_id=comp1, starts_at=now - datetime.timedelta(minutes=5))
    alert2 = Alert(id=uuid.uuid4(), component_id=comp2, starts_at=now - datetime.timedelta(minutes=2))
    
    def mock_db_query(model):
        m = MagicMock()
        if model == IncidentAlert:
            m.filter.return_value.all.return_value = [
                IncidentAlert(alert_id=alert1.id),
                IncidentAlert(alert_id=alert2.id)
            ]
        elif model == Alert:
            m.filter.return_value.all.return_value = [alert1, alert2]
        return m
        
    db.query.side_effect = mock_db_query
    
    with pytest.MonkeyPatch.context() as monkeypatch:
        from ace.ranking import ranker
        
        mock_graph = MagicMock()
        # Neighbors of comp1 include comp3
        mock_graph.neighbours_within.return_value = {comp3}
        mock_graph.get_edge_count.return_value = 5
        monkeypatch.setattr(ranker, "graph_instance", mock_graph)
        
        mock_reachability = MagicMock()
        def side_effect(source, target):
            if source == target:
                return (0, "self", [source])
            if source == comp3 and target == comp1:
                return (1, "inbound", [comp3, comp1])
            if source == comp3 and target == comp2:
                return (2, "outbound", [comp3, comp1, comp2])
            return None
            
        mock_reachability.get_shortest_path.side_effect = side_effect
        monkeypatch.setattr(ranker, "reachability", mock_reachability)
        
        rank_root_cause_candidates(db, incident, now)
        
        # Verify db.add is called for candidates
        assert db.add.call_count == 3
        db.commit.assert_called_once()
        
        added_candidates = [call.args[0] for call in db.add.call_args_list]
        added_candidates.sort(key=lambda c: c.rank)
        
        # comp3 is inbound (10.0 base) - 2.0 (1 hop) = 8.0
        # comp1 is self (8.0 base) - 0.0 + 2.0 (fired) + 5.0 (earliest) = 15.0
        # comp2 is self (8.0 base) - 0.0 + 2.0 (fired) = 10.0
        
        assert added_candidates[0].component_id == comp1
        assert added_candidates[1].component_id == comp2
        assert added_candidates[2].component_id == comp3
        
        assert added_candidates[0].evidence["is_earliest_alert"] is True
        assert added_candidates[1].evidence["is_earliest_alert"] is False
        assert added_candidates[2].evidence["fired_alert"] is False
        
        for cand in added_candidates:
            assert cand.uncertain is True  # edge count is 5
