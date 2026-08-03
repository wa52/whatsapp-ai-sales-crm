"""Telegram channel admin endpoint: manual poll trigger."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..deps import require_admin
from ..telegram import runtime as telegram_runtime

router = APIRouter(
    prefix="/api/telegram",
    tags=["telegram"],
    dependencies=[Depends(require_admin)],
)


@router.post("/poll")
def poll(request: Request) -> dict:
    """Fetch Telegram updates once and run them through the pipeline.

    Skipped while the background poller thread is running — Telegram allows
    only one long-polling consumer per bot, and a second one gets 409.
    """
    thread = getattr(request.app.state, "poller_thread", None)
    if thread is not None and thread.is_alive():
        return {"handled": 0, "poller_active": True}
    return {"handled": telegram_runtime.build_poller(request.app).poll_once()}
