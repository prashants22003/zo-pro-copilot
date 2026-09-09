from app.llm import GenerateResult, generate, model_for_role, provider_for_role


class _Settings:
    resolved_orch_provider = "gemini"
    resolved_orch_model = "gemini-3.6-flash"
    resolved_agent_provider = "ollama"
    resolved_agent_model = "qwen2.5-coder:7b-instruct-q4_K_M"
    gemini_api_key = "test-key"
    ollama_host = "http://localhost:11434"


def test_provider_for_role(monkeypatch) -> None:
    monkeypatch.setattr("app.llm.get_settings", lambda: _Settings())
    assert provider_for_role("orchestrator") == "gemini"
    assert provider_for_role("agent") == "ollama"
    assert model_for_role("orchestrator") == "gemini-3.6-flash"
    assert "coder" in model_for_role("agent")


def test_generate_dispatches_by_role(monkeypatch) -> None:
    recorded: list[tuple[str, str | None]] = []

    def fake_gemini(system, messages, tools=None, model=None):
        recorded.append(("gemini", model))
        return GenerateResult(text="from-gemini")

    def fake_ollama(system, messages, tools=None, model=None):
        recorded.append(("ollama", model))
        return GenerateResult(text="from-ollama")

    monkeypatch.setattr("app.llm.get_settings", lambda: _Settings())
    monkeypatch.setattr("app.llm.gemini_provider.generate", fake_gemini)
    monkeypatch.setattr("app.llm.ollama_provider.generate", fake_ollama)

    orch = generate("sys", [], role="orchestrator")
    agent = generate("sys", [], role="agent")
    assert orch.text == "from-gemini"
    assert agent.text == "from-ollama"
    assert recorded[0] == ("gemini", "gemini-3.6-flash")
    assert recorded[1][0] == "ollama"
    assert "coder" in (recorded[1][1] or "")
