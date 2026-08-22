import json
from datetime import UTC, datetime
from unittest.mock import patch

from sqlalchemy.orm import Session

from ace.ingestion.adapters.zabbix import ZabbixAdapter


def test_zabbix_webhook_unknown_severity(db_session: Session) -> None:
    adapter = ZabbixAdapter()

    payload = {
        "value": json.dumps(
            {
                "host": "docker-host-01",
                "trigger_name": "High disk usage on /mnt/valkey-data",
                "severity": "unknown_sev",
                "item_key": "vfs.fs.size[/mnt/valkey-data,pused]",
                "item_value": "92.206438",
                "event_time": "2026.08.21T06:04:34Z",
            }
        )
    }

    with (
        patch("ace.ingestion.resolver.Resolver.resolve", return_value=(None, True)),
        patch("ace.ingestion.adapters.zabbix.logger.warning") as mock_warning,
    ):
        alerts = adapter.normalize(payload, db_session)
        assert len(alerts) == 1
        assert alerts[0].severity == "medium"

        # Verify the warning was logged
        warning_calls = [call.args[0] for call in mock_warning.call_args_list]
        assert any(
            "Unknown severity 'unknown_sev' mapped to medium" in arg for arg in warning_calls
        )


def test_zabbix_timestamp_parsing(db_session: Session) -> None:
    adapter = ZabbixAdapter()

    payload = {
        "value": json.dumps(
            {
                "host": "docker-host-01",
                "trigger_name": "High disk usage on /mnt/valkey-data",
                "severity": "High",
                "item_key": "vfs.fs.size[/mnt/valkey-data,pused]",
                "item_value": "92.206438",
                "event_time": "2026.08.21T06:04:34Z",
            }
        )
    }

    with patch("ace.ingestion.resolver.Resolver.resolve", return_value=(None, True)):
        alerts = adapter.normalize(payload, db_session)
        assert len(alerts) == 1
        # The dot should be replaced by hyphen and parsed
        expected_time = datetime(2026, 8, 21, 6, 4, 34, tzinfo=UTC)
        assert alerts[0].starts_at == expected_time


def test_zabbix_identifier_extraction() -> None:
    adapter = ZabbixAdapter()

    alert_data = {
        "host": "docker-host-01",
        "trigger_name": "High disk usage on /mnt/valkey-data",
        "severity": "High",
        "item_key": "vfs.fs.size[/mnt/valkey-data,pused]",
        "item_value": "92.206438",
        "event_time": "2026.08.21T06:04:34Z",
    }

    candidates = adapter.extract_identifiers(alert_data)

    assert len(candidates) == 3
    # Most specific to least specific
    assert candidates[0].value == "/mnt/valkey-data"
    assert candidates[0].field_name == "item_key_arg"
    assert candidates[1].value == "docker-host-01"
    assert candidates[1].field_name == "host"
    assert candidates[2].value == "vfs.fs.size[/mnt/valkey-data,pused]"
    assert candidates[2].field_name == "item_key"
