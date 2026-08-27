from ace.correlation.text_normalise import extract_normalised_text, normalise_text
from ace.db.models.alerts import Alert


def test_normalise_text_strips_uuids():
    text = "Error in pod backend-5c9b7f8c-4a3b-11eb-b378-0242ac130002"
    norm = normalise_text(text)
    assert norm == "error in pod backend-"


def test_normalise_text_strips_ips():
    text = "Connection refused to 192.168.1.10"
    norm = normalise_text(text)
    assert norm == "connection refused to"


def test_normalise_text_strips_ports():
    text = "Target node-exporter:9100 is down"
    norm = normalise_text(text)
    assert norm == "target node-exporter is down"


def test_normalise_text_strips_timestamps():
    text = "Event occurred at 2026-08-27T22:28:35Z in production"
    norm = normalise_text(text)
    assert norm == "event occurred at in production"


def test_normalise_text_strips_numbers():
    text = "CPU usage is at 98.5 percent for 10 minutes"
    norm = normalise_text(text)
    assert norm == "cpu usage is at percent for minutes"


def test_normalise_text_preserves_keywords():
    text = "OOMKilled in namespace cart"
    norm = normalise_text(text)
    assert norm == "oomkilled in namespace cart"


def test_extract_normalised_text():
    alert = Alert(
        labels={"alertname": "HighCPU", "pod": "frontend-123", "ip": "10.0.0.1"},
        annotations={"description": "CPU usage > 90% at 2026-08-27T10:00:00Z"},
        external_id="event-12345",
    )
    tokens = extract_normalised_text(alert)
    # 10.0.0.1 -> stripped completely, might be empty, filtered out
    # "HighCPU" -> "highcpu"
    # "frontend-123" -> "frontend-"
    # "event-12345" -> ignored (external_id)

    assert "highcpu" in tokens
    assert "frontend-" in tokens
    assert "cpu usage > % at" in tokens
    assert "event-" not in tokens
