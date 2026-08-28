import json
import os
from typing import Any


class JsonFileAdapter:
    def create(self, incident_id: str, data: dict[str, Any]) -> str:
        os.makedirs("itsm", exist_ok=True)
        ext_id = f"ITSM-{incident_id[:8]}"
        filename = f"itsm/{ext_id}.json"
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)
        return ext_id

    def update(self, external_id: str, data: dict[str, Any]) -> None:
        filename = f"itsm/{external_id}.json"
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)
