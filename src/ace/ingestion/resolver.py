import logging
from uuid import UUID

from sqlalchemy.orm import Session

from ace.config import settings
from ace.db.repositories.components import ComponentRepository
from ace.ingestion.models import Candidate

logger = logging.getLogger(__name__)


class Resolver:
    """
    Cross-tool component identity resolver.
    Resolution Order:
    1. Exact canonical name match
    2. Alias match
    3. Fuzzy match (above threshold) -> Unresolved
    """

    def __init__(self, session: Session):
        self.session = session
        self.repo = ComponentRepository(session)

    def resolve(self, candidates: list[Candidate], source_tool: str) -> tuple[UUID | None, bool]:
        """
        Attempts to resolve a component ID based on a list of candidates.
        Returns (component_id, component_unresolved).
        """
        if not candidates:
            return None, True

        # Pass 1: Exact match and Alias match
        for candidate in candidates:
            if not candidate.value:
                continue

            # Exact
            component = self.repo.get_by_name(candidate.value)
            if component:
                from ace.metrics import registry

                registry.inc_counter(f"resolution_exact_{source_tool}")
                return component.id, False

            # Alias
            component = self.repo.get_by_alias(candidate.value, source_tool)
            if component:
                from ace.metrics import registry

                registry.inc_counter(f"resolution_alias_{source_tool}")
                return component.id, False

        # Pass 2: Fuzzy match
        for candidate in candidates:
            if not candidate.value:
                continue

            # fuzzy_search should return (Component, confidence) or (None, None)
            component, confidence = self.repo.fuzzy_search(
                candidate.value, settings.FUZZY_MATCH_THRESHOLD
            )
            if component:
                # On fuzzy match, WRITE the alias with match_method='fuzzy' and its confidence
                self.repo.add_alias(
                    component_id=component.id,
                    alias_name=candidate.value,
                    source_tool=source_tool,
                    match_method="fuzzy",
                    confidence=confidence or 0.0,
                )
                from ace.metrics import registry

                registry.inc_counter(f"resolution_fuzzy_{source_tool}")
                return component.id, False

        from ace.metrics import registry

        registry.inc_counter(f"resolution_unresolved_{source_tool}")
        return None, True
