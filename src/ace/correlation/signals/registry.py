from ace.correlation.signals.base import Signal
from ace.correlation.signals.cooccurrence import CooccurrenceSignal
from ace.correlation.signals.dependency_proximity import DependencyProximitySignal
from ace.correlation.signals.same_component import SameComponentSignal
from ace.correlation.signals.text_similarity import TextSimilaritySignal


def get_active_signals() -> list[Signal]:
    """
    Returns the list of active signals for the correlation engine.
    Adding a signal here will automatically include it in the correlation process.
    """
    return [
        SameComponentSignal(),
        DependencyProximitySignal(),
        TextSimilaritySignal(),
        CooccurrenceSignal(),
    ]
