from ace.pipeline.fingerprint import compute_fingerprint


def test_fingerprint_same_identity_same_hash() -> None:
    h1 = compute_fingerprint("prometheus", "comp-123", "HighCpu", {"severity": "warning"})
    h2 = compute_fingerprint("prometheus", "comp-123", "HighCpu", {"severity": "critical"})
    assert h1 == h2


def test_fingerprint_different_component_different_hash() -> None:
    h1 = compute_fingerprint("prometheus", "comp-123", "HighCpu", {})
    h2 = compute_fingerprint("prometheus", "comp-456", "HighCpu", {})
    assert h1 != h2


def test_fingerprint_different_source_tool_different_hash() -> None:
    """Cross-tool dedup is a non-goal, preserves cross-tool signal."""
    h1 = compute_fingerprint("prometheus", "comp-123", "HighCpu", {})
    h2 = compute_fingerprint("zabbix", "comp-123", "HighCpu", {})
    assert h1 != h2


def test_fingerprint_null_component_fallback() -> None:
    """Null component_id uses identifying labels as fallback."""
    # Same identifying labels -> same hash
    h1 = compute_fingerprint("prometheus", None, "HighCpu", {"instance": "host-A", "env": "prod"})
    h2 = compute_fingerprint(
        "prometheus", None, "HighCpu", {"instance": "host-A", "env": "staging"}
    )
    assert h1 == h2

    # Different identifying labels -> different hash
    h3 = compute_fingerprint("prometheus", None, "HighCpu", {"instance": "host-B", "env": "prod"})
    assert h1 != h3
