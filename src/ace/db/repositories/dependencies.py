import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ace.db.models.components import Component, Dependency


class DependencyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def dependents_of(self, dependency_id: uuid.UUID) -> Sequence[Component]:
        """
        Returns all components that depend on `dependency_id`.
        Since the semantics is `from_component_id` DEPENDS ON `to_component_id`,
        we query where `to_component_id == dependency_id` to find what depends on it
        (the dependents).
        """
        stmt = (
            select(Component)
            .join(Dependency, Dependency.from_component_id == Component.id)
            .where(Dependency.to_component_id == dependency_id)
        )
        return self.session.scalars(stmt).all()
