"""CRM read APIs: conversations and their message history."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from ..deps import SessionDep
from ..models import Conversation, Customer
from ..repos import get_conversation_messages

router = APIRouter(prefix="/api/crm", tags=["crm"])


class ConversationOut(BaseModel):
    id: int
    customer_id: int
    wa_id: str
    customer_name: str | None = None
    country_code: str | None = None
    handler: str
    status: str
    last_message_at: datetime | None = None
    lead_score: int | None = None
    lead_level: str | None = None


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    status: str
    created_at: datetime


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(session: SessionDep) -> list[ConversationOut]:
    rows = session.exec(
        select(Conversation, Customer)
        .join(Customer)
        .order_by(Conversation.last_message_at.desc(), Conversation.id.desc())
    ).all()
    return [
        ConversationOut(
            id=c.id,
            customer_id=c.customer_id,
            wa_id=cu.wa_id,
            customer_name=cu.name,
            country_code=cu.country_code,
            handler=c.handler,
            status=c.status,
            last_message_at=c.last_message_at,
            lead_score=cu.lead_score,
            lead_level=cu.lead_level,
        )
        for c, cu in rows
    ]


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(conversation_id: int, session: SessionDep) -> list[MessageOut]:
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = get_conversation_messages(session, conversation_id)
    return [
        MessageOut(
            id=m.id, role=m.role, content=m.content, status=m.status, created_at=m.created_at
        )
        for m in messages
    ]
