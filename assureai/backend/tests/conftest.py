import pytest


@pytest.fixture(autouse=True)
def _deterministic_environment(monkeypatch):
    """Tests must never call an external AI service or depend on the machine's
    own settings, so any key or switch set on this laptop is ignored.

    Condensing is switched OFF here so the extraction/voice/assessment tests keep
    exercising the full documented wording; tests of the condensed output turn it
    on explicitly (or delete the variable to check the product default)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.setenv("ASSUREAI_CONDENSE", "0")
