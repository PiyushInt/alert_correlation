from ace.correlation.signals.base import IncidentCentroid, SignalContext
from ace.correlation.signals.text_similarity import TextSimilaritySignal
from ace.db.models.alerts import Alert
from ace.db.models.incidents import Incident


def test_text_similarity_no_text():
    signal = TextSimilaritySignal()
    # Alert with no labels/annotations that produce text
    alert = Alert(labels={}, annotations={}, external_id="")
    centroid = IncidentCentroid(normalised_text={"some text"})
    context = SignalContext(None, None, None)

    result = signal.score(alert, Incident(), centroid, context)
    assert result.score == 0.0
    assert result.evidence["match"] is False

    # Centroid with no text
    alert2 = Alert(labels={"name": "foo"}, annotations={}, external_id="")
    centroid2 = IncidentCentroid(normalised_text=set())
    result2 = signal.score(alert2, Incident(), centroid2, context)
    assert result2.score == 0.0


def test_text_similarity_match():
    signal = TextSimilaritySignal()
    alert = Alert(
        labels={"alertname": "HighCPU", "pod": "frontend-123"}, annotations={}, external_id=""
    )
    # The normaliser lowercases and strips "123"
    centroid = IncidentCentroid(normalised_text={"highcpu", "frontend-"})
    context = SignalContext(None, None, None)

    result = signal.score(alert, Incident(), centroid, context)
    # The tokens exactly match the centroid's tokens when stringified
    # "frontend- highcpu" vs "frontend- highcpu" -> ratio should be 100
    assert result.score == 1.0
    assert result.evidence["match"] is True


def test_text_similarity_raw_score():
    signal = TextSimilaritySignal()

    alert = Alert(labels={"alertname": "HighMemory"}, annotations={}, external_id="")
    centroid = IncidentCentroid(normalised_text={"highcpu", "frontend-"})
    context = SignalContext(None, None, None)

    result = signal.score(alert, Incident(), centroid, context)
    assert result.score > 0.0
    assert result.evidence["match"] is True


def test_text_similarity_transitivity():
    """
    Test that chaining A-B and B-C does NOT produce a match for A-C.
    Alert A: "Database is down"
    Alert B: "Database is slow and API is failing"
    Alert C: "API is failing"
    """
    signal = TextSimilaritySignal()

    # Let's mock the extract_normalised_text indirectly by passing alerts that will
    # normalize to these exact strings.
    # (Since the normalizer splits values, we'll just use one label).
    alert_c = Alert(labels={"msg": "API is failing"}, annotations={}, external_id="")

    # Centroid for incident containing only A
    centroid_a = IncidentCentroid(normalised_text={"database is down"})

    context = SignalContext(None, None, None)

    # A vs C
    result = signal.score(alert_c, Incident(), centroid_a, context)
    # They should have very low similarity (WRatio)
    assert result.score < 0.5  # or 0.0 if below threshold
