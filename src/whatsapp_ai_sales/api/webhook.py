"""WhatsApp webhook endpoints: verification handshake and inbound delivery."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse

from ..config import settings
from ..deps import IngestionDep
from ..whatsapp.webhook import parse_meta_payload

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.get("/whatsapp", response_class=PlainTextResponse)
def verify_webhook(
    hub_mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    hub_verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    hub_challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> str:
    """Meta's webhook verification handshake. Echoes the challenge on success."""
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        return hub_challenge or ""
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/whatsapp")
def receive_webhook(
    payload: dict[str, Any],
    ingestion: IngestionDep,
    x_hub_signature_256: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    """Accept a Meta webhook delivery and process each inbound text message."""
    for inbound in parse_meta_payload(payload):
        ingestion.handle_inbound(inbound)
    return {"status": "ok"}
