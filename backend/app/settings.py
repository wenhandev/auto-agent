from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    llm_provider: str = "openai"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"
    openai_base_url: str | None = None
    google_api_key: str | None = None
    google_model: str = "gemini-2.0-flash"
    google_base_url: str | None = None
    browser_headless: bool = False
    fuzzy_max_steps: int = 8


settings = Settings()
