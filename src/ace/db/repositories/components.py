from typing import Any

from sqlalchemy.orm import Session


class ComponentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_name(self, canonical_name: str) -> Any:
        from ace.db.models.components import Component

        return self.session.query(Component).filter_by(canonical_name=canonical_name).first()

    def get_by_alias(self, alias_str: str, source_tool: str) -> Any:
        from ace.db.models.components import Component, ComponentAlias

        alias = (
            self.session.query(ComponentAlias)
            .filter_by(alias=alias_str, source_tool=source_tool)
            .first()
        )
        if alias:
            return self.session.query(Component).filter_by(id=alias.component_id).first()
        return None
