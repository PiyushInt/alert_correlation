import logging

from rapidfuzz import fuzz

from ace.correlation.signals.base import IncidentCentroid, Signal, SignalContext, SignalResult
from ace.correlation.text_normalise import extract_normalised_text
from ace.db.models.alerts import Alert
from ace.db.models.incidents import Incident

logger = logging.getLogger(__name__)


class TextSimilaritySignal(Signal):
    @property
    def name(self) -> str:
        return "text_similarity"

    def score(
        self, alert: Alert, incident: Incident, centroid: IncidentCentroid, context: SignalContext
    ) -> SignalResult:

        # 1. Extract normalised tokens for incoming alert
        incoming_tokens = extract_normalised_text(alert)

        if not incoming_tokens:
            return SignalResult(
                score=0.0, evidence={"match": False, "reason": "no text tokens on alert"}
            )

        if not centroid.normalised_text:
            return SignalResult(
                score=0.0, evidence={"match": False, "reason": "no text tokens on centroid"}
            )

        # 2. Join sets into strings for RapidFuzz
        # Sorting ensures stable comparison but WRatio handles order anyway.
        incoming_str = " ".join(sorted(list(incoming_tokens)))
        centroid_str = " ".join(sorted(list(centroid.normalised_text)))

        # 3. Compute score using WRatio
        raw_score = fuzz.WRatio(incoming_str, centroid_str)

        return SignalResult(
            score=raw_score / 100.0,
            evidence={
                "match": True,
                "raw_score": raw_score,
                "incoming_text": incoming_str,
                "centroid_text": centroid_str,
            },
        )
