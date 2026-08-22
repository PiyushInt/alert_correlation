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

    def fuzzy_search(self, query: str, threshold: float) -> tuple[Any, float | None]:
        from rapidfuzz import fuzz, process

        from ace.db.models.components import Component

        components = self.session.query(Component).all()
        if not components:
            return None, None

        choices = {c.id: c.canonical_name for c in components}

        # We need a list of strings to search against, rapidfuzz process.extractOne can take a dict
        result = process.extractOne(query, choices, scorer=fuzz.WRatio)
        if result:
            match_str, score, comp_id = result
            if score >= threshold:
                matched_comp = self.session.query(Component).filter_by(id=comp_id).first()
                return matched_comp, score

        return None, None

    def add_alias(
        self,
        component_id: Any,
        alias_name: str,
        source_tool: str,
        match_method: str = "manual",
        confidence: float = 1.0,
    ) -> None:
        from ace.db.models.components import ComponentAlias

        new_alias = ComponentAlias(
            component_id=component_id,
            alias=alias_name,
            source_tool=source_tool,
            match_method=match_method,
            confidence=confidence,
        )
        self.session.add(new_alias)
        self.session.commit()
