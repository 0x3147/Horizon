from src.setup import wizard


def test_configure_ai_writes_inline_api_key_without_env_field(monkeypatch):
    answers = iter(["openai", "gpt-4", "", "sk-local", "zh,en"])

    def fake_ask(*args, **kwargs):  # type: ignore[no-untyped-def]
        return next(answers)

    monkeypatch.setattr(wizard.Prompt, "ask", fake_ask)

    config = wizard.configure_ai()

    assert config is not None
    assert config.api_key == "sk-local"
    assert config.api_key_env is None
    assert config.languages == ["zh", "en"]
