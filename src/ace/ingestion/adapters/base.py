from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.orm import Session

from ace.ingestion.models import NormalisedAlert


class BaseAdapter(ABC):
    """Base interface for all ingestion adapters."""

    @abstractmethod
    def normalize(self, payload: Any, session: Session) -> list[NormalisedAlert]:
        """
        Normalize a tool-specific payload into a list of canonical NormalisedAlerts.
        Component resolution (EXACT and ALIAS lookup) occurs here using the provided db_conn.
        """
        pass
