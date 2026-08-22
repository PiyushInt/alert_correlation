import xxhash

IDENTITY_LABELS = ("component", "instance", "host", "mountpoint", "pod", "service")


def compute_fingerprint(
    source_tool: str, component_id: str | None, alertname: str, labels: dict[str, str]
) -> str:
    """
    Computes a deterministic identity fingerprint for an alert.

    The fingerprint is computed over (source_tool, component_stand_in, alertname).
    - If component_id is known, component_stand_in is str(component_id).
    - If component_id is None, component_stand_in is a sorted hash of identifying labels.
    - Timestamp, metric values, and severity are EXCLUDED.
    - source_tool is INCLUDED: cross-tool dedup is a non-goal. Prometheus and Zabbix
      reporting the same fault are corroborating evidence, not duplicates.
    """
    if component_id is not None:
        component_stand_in = str(component_id)
    else:
        # Fallback for unresolved components: use identifying labels
        identifying_values = [f"{k}={labels[k]}" for k in sorted(IDENTITY_LABELS) if k in labels]
        component_stand_in = "|".join(identifying_values)

    hasher = xxhash.xxh64()
    hasher.update(source_tool.encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update(component_stand_in.encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update(alertname.encode("utf-8"))

    return hasher.hexdigest()
