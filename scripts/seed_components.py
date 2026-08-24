#!/usr/bin/env python3
import sys
from pathlib import Path

import yaml

# Add src to pythonpath so we can import ace
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ace.api.deps import SessionLocal
from ace.db.models.components import Component, ComponentAlias


def main():
    inventory_path = Path(__file__).parent.parent / "estate" / "inventory" / "components.yaml"
    with open(inventory_path) as f:
        data = yaml.safe_load(f)

    db = SessionLocal()

    components = data.get("components", [])
    print(f"Seeding {len(components)} components...")

    try:
        for comp_data in components:
            canonical_name = comp_data["canonical_name"]

            # Upsert component
            comp = db.query(Component).filter_by(canonical_name=canonical_name).first()
            if not comp:
                from datetime import UTC, datetime

                comp = Component(
                    canonical_name=canonical_name,
                    type=comp_data.get("type", "service"),
                    environment=comp_data.get("environment", "production"),
                    tenant=comp_data.get("tenant", "default"),
                    service_tier=comp_data.get("service_tier", "tier-1"),
                    first_seen=datetime.now(UTC),
                    last_seen=datetime.now(UTC),
                )
                db.add(comp)
                db.commit()
                db.refresh(comp)

            # Upsert aliases
            aliases = comp_data.get("aliases", [])
            for alias_data in aliases:
                alias_name = alias_data["alias"]
                source_tool = alias_data["source_tool"]

                alias = (
                    db.query(ComponentAlias)
                    .filter_by(alias=alias_name, source_tool=source_tool)
                    .first()
                )

                if not alias:
                    alias = ComponentAlias(
                        component_id=comp.id,
                        alias=alias_name,
                        source_tool=source_tool,
                        match_method="manual",
                        confidence=1.0,
                    )
                    db.add(alias)

        db.commit()
        print("Done.")
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
