import re
from typing import Any

from ace.db.models.alerts import Alert


def _extract_strings_from_dict(d: dict[str, Any]) -> set[str]:
    """Recursively extract string values from a dictionary."""
    strings = set()
    for v in d.values():
        if isinstance(v, str):
            strings.add(v)
        elif isinstance(v, dict):
            strings.update(_extract_strings_from_dict(v))
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, str):
                    strings.add(item)
    return strings


def extract_normalised_text(alert: Alert) -> set[str]:
    """
    Extracts and normalises text tokens from an alert's labels and annotations.
    """
    raw_strings = set()
    if alert.labels:
        raw_strings.update(_extract_strings_from_dict(alert.labels))
    if alert.annotations:
        raw_strings.update(_extract_strings_from_dict(alert.annotations))

    # We do NOT include external_id, as it contains meaningless fingerprint hashes
    # (e.g. 035cf03bf9be1598) which pollute the text similarity calculation.

    normalised = set()
    for s in raw_strings:
        norm = normalise_text(s)
        if norm:
            # We treat the entire normalised string value as a "token" in the set,
            # as fuzzy matching will compare these string segments.
            normalised.add(norm.strip())

    # filter out any empty strings
    return {t for t in normalised if t}


def normalise_text(text: str) -> str:
    """
    Normalises a string by lowercasing and stripping:
    - UUIDs
    - IPv4 addresses
    - Timestamps (ISO 8601-ish)
    - Ports (:1234)
    - Standalone numbers
    """
    text = text.lower()

    # 1. Strip UUIDs
    uuid_pattern = r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
    text = re.sub(uuid_pattern, "", text)

    # 2. Strip IPv4 addresses
    ip_pattern = r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
    text = re.sub(ip_pattern, "", text)

    # 3. Strip Timestamps (ISO dates)
    # 2026-08-27T22:28:35Z or 2026-08-27 22:28:35
    iso_date_pattern = (
        r"\b\d{4}-\d{2}-\d{2}(?:[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?\b"
    )
    text = re.sub(iso_date_pattern, "", text, flags=re.IGNORECASE)

    # 4. Strip Ports
    port_pattern = r":\d{2,5}\b"
    text = re.sub(port_pattern, "", text)

    # 5. Strip standalone numeric values (integers or floats)
    number_pattern = r"\b\d+(?:\.\d+)?\b"
    text = re.sub(number_pattern, "", text)

    # Replace multiple spaces with a single space
    text = re.sub(r"\s+", " ", text).strip()

    return text
