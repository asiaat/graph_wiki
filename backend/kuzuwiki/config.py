"""Pydantic Settings configuration for KuzuWiki-OSINT backend."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # OpenRouter free models. Model ids go stale quickly: the previously
    # configured slugs (nemotron-3-8b-32k-instruct, gemma-3-27b-it, flint-8b,
    # minimax-01) now return "not a valid model ID" / "paid only".
    jev_primary_model: str = "nvidia/nemotron-3.5-lightning:free"
    jev_fallback_models: str = (
        "recursive/flint-v1.0:free,google/gemma-4-26b-a4b-it:free,"
        "nvidia/nemotron-3.5-lightning:free"
    )
    jev_nli_model: str = "MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli"
    jev_embedding_model: str = "BAAI/bge-m3"

    #: KùzuDB requires a *file* path; it manages the surrounding directory
    #: itself. Pointing this at a directory makes the database refuse to open.
    kuzu_db_path: str = "/data/kuzudb/graph.kuzu"
    wiki_vault_path: str = "/data/wiki"
    raw_vault_path: str = "/data/raw_vault"
    quarantine_path: str = "/quarantine/slop"

    redis_url: str = "redis://localhost:6379/0"
    searxng_url: str = "http://localhost:8080"

    host: str = "0.0.0.0"
    port: int = 8000

    @property
    def fallback_models_list(self) -> list[str]:
        return [f.strip() for f in self.jev_fallback_models.split(",") if f.strip()]


settings = Settings()
