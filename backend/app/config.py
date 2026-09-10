from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_ORCH_OLLAMA = "qwen2.5:7b-instruct"
DEFAULT_AGENT_OLLAMA = "qwen2.5-coder:7b-instruct-q4_K_M"
DEFAULT_AGENT_NVIDIA = "nvidia/nemotron-3.5-lightning-30b-a3b"
DEFAULT_GEMINI = "gemini-3.6-flash"
DEFAULT_NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://zopro:zopro_local_dev@localhost:5433/zopro"
    sales_database_url: str = (
        "postgresql://sales_agent_role:sales_agent_local@localhost:5433/zopro"
    )
    purchase_database_url: str = (
        "postgresql://purchase_agent_role:purchase_agent_local@localhost:5433/zopro"
    )
    insight_database_url: str = (
        "postgresql://insight_role:insight_agent_local@localhost:5433/zopro"
    )

    llm_provider: str = "ollama"
    llm_model: str = ""
    orch_provider: str = "nvidia"
    orch_model: str = ""
    agent_provider: str = "nvidia"
    agent_model: str = ""
    ollama_host: str = "http://host.docker.internal:11434"
    gemini_api_key: str = ""
    nvidia_api_key: str = ""
    nvidia_base_url: str = DEFAULT_NVIDIA_BASE
    insight_narrate: str = "template"
    cors_origins: str = "http://localhost:8080,http://localhost:5173,http://127.0.0.1:8080,http://127.0.0.1:5173"
    query_row_cap: int = 500
    query_timeout_ms: int = 5000
    docs_dir: str = ""

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def resolved_orch_provider(self) -> str:
        raw = (self.orch_provider or "nvidia").strip().lower()
        return raw or "nvidia"

    @property
    def resolved_agent_provider(self) -> str:
        raw = (self.agent_provider or "nvidia").strip().lower()
        return raw or "nvidia"

    @property
    def resolved_orch_model(self) -> str:
        if self.orch_model.strip():
            return self.orch_model.strip()
        if self.resolved_orch_provider == "gemini":
            return self.llm_model.strip() or DEFAULT_GEMINI
        if self.resolved_orch_provider == "nvidia":
            return DEFAULT_AGENT_NVIDIA
        return DEFAULT_ORCH_OLLAMA

    @property
    def resolved_agent_model(self) -> str:
        if self.agent_model.strip():
            return self.agent_model.strip()
        if self.resolved_agent_provider == "gemini":
            return DEFAULT_GEMINI
        if self.resolved_agent_provider == "nvidia":
            return self.llm_model.strip() or DEFAULT_AGENT_NVIDIA
        return self.llm_model.strip() or DEFAULT_AGENT_OLLAMA

    @property
    def resolved_llm_model(self) -> str:
        return self.resolved_agent_model


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
