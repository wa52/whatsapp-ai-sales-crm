"""Telegram channel admin endpoint: manual poll trigger."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..telegram import runtime as telegram_runtime

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


@router.post("/poll")
def poll(request: Request) -> dict[str, int]:
    """Fetch Telegram updates once and run them through the pipeline."""
    return {"handled": telegram_runtime.build_poller(request.app).poll_once()}
