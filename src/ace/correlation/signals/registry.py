from ace.correlation.signals.base import Signal
from ace.correlation.signals.same_component import SameComponentSignal


def get_active_signals() -> list[Signal]:
    """
    Returns the list of active signals for the correlation engine.
    Adding a signal here will automatically include it in the correlation process.
    """
    return [
        SameComponentSignal(),
    ]
