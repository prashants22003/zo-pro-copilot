import json

from app.llm import GenerateResult, generate, llm_available, model_for_role, provider_for_role, unavailable_message
from app.providers import openai_compat


class _Settings:
    resolved_orch_provider = "gemini"
    resolved_orch_model = "gemini-3.6-flash"
    resolved_agent_provider = "ollama"
    resolved_agent_model = "qwen2.5-coder:7b-instruct-q4_K_M"
    gemini_api_key = "test-key"
    nvidia_api_key = ""
    ollama_host = "http://localhost:11434"


class _NvidiaSettings:
    resolved_orch_provider = "gemini"
    resolved_orch_model = "gemini-3.6-flash"
    resolved_agent_provider = "nvidia"
    resolved_agent_model = "nvidia/nemotron-3.5-lightning-30b-a3b"
    gemini_api_key = "test-key"
    nvidia_api_key = "nvapi-test"
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


def test_generate_dispatches_nvidia_agent_not_ollama(monkeypatch) -> None:
    recorded: list[tuple[str, str | None]] = []

    def fake_gemini(system, messages, tools=None, model=None):
        recorded.append(("gemini", model))
        return GenerateResult(text="from-gemini")

    def fake_nvidia(system, messages, tools=None, model=None):
        recorded.append(("nvidia", model))
        return GenerateResult(text="from-nvidia")

    def fake_ollama(system, messages, tools=None, model=None):
        recorded.append(("ollama", model))
        return GenerateResult(text="from-ollama")

    monkeypatch.setattr("app.llm.get_settings", lambda: _NvidiaSettings())
    monkeypatch.setattr("app.llm.gemini_provider.generate", fake_gemini)
    monkeypatch.setattr("app.llm.openai_compat_provider.generate", fake_nvidia)
    monkeypatch.setattr("app.llm.ollama_provider.generate", fake_ollama)

    orch = generate("sys", [], role="orchestrator")
    agent = generate("sys", [], role="agent")
    assert orch.text == "from-gemini"
    assert agent.text == "from-nvidia"
    assert recorded == [
        ("gemini", "gemini-3.6-flash"),
        ("nvidia", "nvidia/nemotron-3.5-lightning-30b-a3b"),
    ]


class _NvidiaBothSettings:
    resolved_orch_provider = "nvidia"
    resolved_orch_model = "nvidia/nemotron-3.5-lightning-30b-a3b"
    resolved_agent_provider = "nvidia"
    resolved_agent_model = "nvidia/nemotron-3.5-lightning-30b-a3b"
    gemini_api_key = ""
    nvidia_api_key = "nvapi-test"
    ollama_host = "http://localhost:11434"


def test_generate_dispatches_nvidia_orchestrator(monkeypatch) -> None:
    recorded: list[tuple[str, str | None]] = []

    def fake_gemini(system, messages, tools=None, model=None):
        recorded.append(("gemini", model))
        return GenerateResult(text="from-gemini")

    def fake_nvidia(system, messages, tools=None, model=None):
        recorded.append(("nvidia", model))
        return GenerateResult(text="from-nvidia")

    monkeypatch.setattr("app.llm.get_settings", lambda: _NvidiaBothSettings())
    monkeypatch.setattr("app.llm.gemini_provider.generate", fake_gemini)
    monkeypatch.setattr("app.llm.openai_compat_provider.generate", fake_nvidia)

    orch = generate("sys", [], role="orchestrator")
    agent = generate("sys", [], role="agent")
    assert orch.text == "from-nvidia"
    assert agent.text == "from-nvidia"
    assert recorded == [
        ("nvidia", "nvidia/nemotron-3.5-lightning-30b-a3b"),
        ("nvidia", "nvidia/nemotron-3.5-lightning-30b-a3b"),
    ]


def test_nvidia_available_without_ollama_ping(monkeypatch) -> None:
    def boom() -> bool:
        raise AssertionError("Ollama must not be pinged for NVIDIA")

    monkeypatch.setattr("app.llm.get_settings", lambda: _NvidiaSettings())
    monkeypatch.setattr("app.llm.ollama_provider.ping", boom)
    assert llm_available("agent") is True


def test_nvidia_unavailable_without_key(monkeypatch) -> None:
    settings = _NvidiaSettings()
    settings.nvidia_api_key = ""
    monkeypatch.setattr("app.llm.get_settings", lambda: settings)
    monkeypatch.setattr("app.llm.ollama_provider.ping", lambda: True)
    assert llm_available("agent") is False
    assert "NVIDIA_API_KEY" in unavailable_message("agent")


def test_openai_compat_parses_tool_calls(monkeypatch) -> None:
    class _S:
        nvidia_api_key = "nvapi-test"
        nvidia_base_url = "https://integrate.api.nvidia.com/v1"
        resolved_agent_model = "nvidia/nemotron-3.5-lightning-30b-a3b"

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "call_abc",
                                        "function": {
                                            "name": "execute_sql",
                                            "arguments": '{"query": "SELECT 1"}',
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            ).encode()

    monkeypatch.setattr(openai_compat, "get_settings", lambda: _S())
    monkeypatch.setattr(
        openai_compat.urllib.request, "urlopen", lambda *a, **k: FakeResp()
    )
    result = openai_compat.generate("sys", [])
    assert result.tool_calls[0].name == "execute_sql"
    assert result.tool_calls[0].args["query"] == "SELECT 1"
    assert result.tool_calls[0].id == "call_abc"
