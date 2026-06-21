"""The LLM commentary is an optional enrichment layer. These tests pin the two
ways it must degrade without taking the whole workflow down: no API key, and a
runtime API failure."""
import workflows._shared as shared


def test_commentary_skipped_when_unconfigured(monkeypatch):
    monkeypatch.setattr(shared.settings, "is_llm_commentary_enabled", lambda: False)

    insights, stats = shared.generate_optional_commentary(
        "sales-pipeline-health", "Total Opportunities: 10", [])

    assert insights == ""
    assert stats == {"tokens": 0, "cost": 0.0}


def test_commentary_skipped_when_skip_ai_set(monkeypatch):
    monkeypatch.setenv("SKIP_AI", "1")
    monkeypatch.setattr(shared.settings, "is_gemini_configured", lambda: True)
    monkeypatch.setattr(shared.settings, "is_llm_commentary_enabled", lambda: False)

    insights, stats = shared.generate_optional_commentary(
        "sales-pipeline-health", "Total Opportunities: 10", [])

    assert insights == ""
    assert stats == {"tokens": 0, "cost": 0.0}


def test_commentary_degrades_on_api_error(monkeypatch):
    monkeypatch.delenv("SKIP_AI", raising=False)
    monkeypatch.setattr(shared.settings, "is_llm_commentary_enabled", lambda: True)

    def _raise(*args, **kwargs):
        raise shared.GeminiAPIError("model unavailable")

    monkeypatch.setattr(shared, "GeminiClient", _raise)

    insights, stats = shared.generate_optional_commentary(
        "sales-pipeline-health", "Total Opportunities: 10", [])

    assert insights == ""
    assert stats == {"tokens": 0, "cost": 0.0}


def test_commentary_returns_model_output_when_configured(monkeypatch):
    monkeypatch.delenv("SKIP_AI", raising=False)
    monkeypatch.setattr(shared.settings, "is_llm_commentary_enabled", lambda: True)

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def generate_insights(self, prompt, chart_paths):
            return {"insights": "Finding: X", "total_tokens": 1234, "cost": 0.0012}

    monkeypatch.setattr(shared, "GeminiClient", FakeClient)

    insights, stats = shared.generate_optional_commentary(
        "sales-pipeline-health", "Total Opportunities: 10", [])

    assert insights == "Finding: X"
    assert stats == {"tokens": 1234, "cost": 0.0012}
