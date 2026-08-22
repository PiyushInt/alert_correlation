from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.orm import Session

from ace.ingestion.models import Candidate, NormalisedAlert


class BaseAdapter(ABC):
    """Base interface for all ingestion adapters."""

    @abstractmethod
    def normalize(self, payload: Any, session: Session) -> list[NormalisedAlert]:
        """
        Normalize a tool-specific payload into a list of canonical NormalisedAlerts.
        Component resolution occurs here via the Resolver.
        """
        pass

    @abstractmethod
    def extract_identifiers(self, alert: dict[str, Any]) -> list[Candidate]:
        """
        Extract candidate component identifiers from a tool-specific alert payload,
        ordered from most-specific to least-specific.
        """
        pass
