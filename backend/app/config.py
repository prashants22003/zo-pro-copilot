from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_ORCH_OLLAMA = "qwen2.5:7b-instruct"
DEFAULT_AGENT_OLLAMA = "qwen2.5-coder:7b-instruct-q4_K_M"
DEFAULT_GEMINI = "gemini-3.6-flash"


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
    orch_provider: str = "gemini"
    orch_model: str = ""
    agent_provider: str = "ollama"
    agent_model: str = ""
    ollama_host: str = "http://host.docker.internal:11434"
    gemini_api_key: str = ""
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
        raw = (self.orch_provider or "gemini").strip().lower()
        return raw or "gemini"

    @property
    def resolved_agent_provider(self) -> str:
        raw = (self.agent_provider or "ollama").strip().lower()
        return raw or "ollama"

    @property
    def resolved_orch_model(self) -> str:
        if self.orch_model.strip():
            return self.orch_model.strip()
        if self.resolved_orch_provider == "gemini":
            return self.llm_model.strip() or DEFAULT_GEMINI
        return DEFAULT_ORCH_OLLAMA

    @property
    def resolved_agent_model(self) -> str:
        if self.agent_model.strip():
            return self.agent_model.strip()
        if self.resolved_agent_provider == "gemini":
            return DEFAULT_GEMINI
        return self.llm_model.strip() or DEFAULT_AGENT_OLLAMA

    @property
    def resolved_llm_model(self) -> str:
        return self.resolved_agent_model


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
