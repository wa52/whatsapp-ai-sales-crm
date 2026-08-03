"""Application settings loaded from environment / .env."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="WAS_", extra="ignore")

    database_url: str = "sqlite:///./was.db"

    llm_model: str = "deepseek/deepseek-chat"
    llm_api_key: str | None = None
    llm_base_url: str | None = None

    reply_window: int = 10
    whatsapp_verify_token: str = "verify-me"
    fallback_reply: str = (
        "Thank you for your message. I need to confirm this with our sales team "
        "and will get back to you shortly."
    )
    system_prompt: str = (
        "You are a friendly foreign-trade sales assistant. Answer only from the "
        "product knowledge you are given. Never invent prices, stock levels, "
        "lead times, or product capabilities. If you do not know the answer, "
        "say you will confirm with the sales team and reply shortly."
    )


settings = Settings()
