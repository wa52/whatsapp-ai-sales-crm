"""Wiring the Telegram poller into a running app."""

from __future__ import annotations

import threading

from fastapi import FastAPI
from sqlmodel import Session

from ..deps import build_ingestion
from .bot import TelegramBot
from .poller import TelegramPoller


def build_poller(app: FastAPI) -> TelegramPoller:
    """A poller that runs inbound Telegram messages through the ingestion pipeline."""
    settings = app.state.settings

    def handle(inbound) -> None:
        with Session(app.state.engine) as session:
            build_ingestion(app, session).handle_inbound(inbound)

    return TelegramPoller(
        app.state.provider, handle, interval=settings.telegram_poll_interval
    )


def start_telegram_polling(app: FastAPI) -> TelegramPoller:
    """Start the poller in a daemon thread (stops when the process exits)."""
    poller = build_poller(app)
    thread = threading.Thread(target=poller.run_forever, daemon=True)
    thread.start()
    app.state.poller_thread = thread
    return poller


def is_telegram_enabled(app: FastAPI) -> bool:
    settings = app.state.settings
    return bool(settings.telegram_token and settings.telegram_poll_enabled
                and isinstance(app.state.provider, TelegramBot))


__all__ = ["build_poller", "start_telegram_polling", "is_telegram_enabled", "TelegramBot"]
