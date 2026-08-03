"""CRM read + human-handling APIs."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import select

from ..deps import ProviderDep, SessionDep, require_admin
from ..messaging.audit import (
    AUDIT_MANUAL_MESSAGE,
    AUDIT_RELEASE,
    AUDIT_TAKEOVER,
)
from ..messaging.handling import HANDLER_AI, HANDLER_HUMAN
from ..models import Conversation, Customer
from ..repos import get_conversation_messages, send_outbound_message, touch

router = APIRouter(
    prefix="/api/crm",
    tags=["crm"],
    dependencies=[Depends(require_admin)],
)


class ConversationOut(BaseModel):
    id: int
    customer_id: int
    wa_id: str
    customer_name: str | None = None
    country_code: str | None = None
    handler: str
    status: str
    last_message_at: datetime | None = None
    interested_product: str | None = None
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
            interested_product=cu.interested_product,
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


class ManualMessageIn(BaseModel):
    content: str


class DndIn(BaseModel):
    enabled: bool


class ConversationStateOut(BaseModel):
    id: int
    handler: str


class DndOut(BaseModel):
    id: int
    dnd: bool


@router.post("/conversations/{conversation_id}/dnd", response_model=DndOut)
def set_dnd(conversation_id: int, payload: DndIn, session: SessionDep) -> DndOut:
    """Mute/unmute automated replies and follow-ups for a conversation."""
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conversation.dnd = payload.enabled
    session.commit()
    return DndOut(id=conversation.id, dnd=conversation.dnd)


@router.post("/conversations/{conversation_id}/takeover", response_model=ConversationStateOut)
def takeover(conversation_id: int, session: SessionDep, request: Request) -> ConversationStateOut:
    """A human takes over the conversation; the AI stops auto-replying."""
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conversation.handler = HANDLER_HUMAN
    touch(conversation)
    request.app.state.audit.log(AUDIT_TAKEOVER, conversation_id=conversation_id)
    session.commit()
    return ConversationStateOut(id=conversation.id, handler=conversation.handler)


@router.post("/conversations/{conversation_id}/release", response_model=ConversationStateOut)
def release(conversation_id: int, session: SessionDep, request: Request) -> ConversationStateOut:
    """Return the conversation to the AI."""
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conversation.handler = HANDLER_AI
    touch(conversation)
    request.app.state.audit.log(AUDIT_RELEASE, conversation_id=conversation_id)
    session.commit()
    return ConversationStateOut(id=conversation.id, handler=conversation.handler)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=201,
)
def send_manual_message(
    conversation_id: int,
    payload: ManualMessageIn,
    session: SessionDep,
    provider: ProviderDep,
    request: Request,
) -> MessageOut:
    """A human sends a message to the customer on behalf of the business."""
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    customer = session.get(Customer, conversation.customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    message = send_outbound_message(session, provider, conversation, customer, payload.content)
    touch(conversation)
    request.app.state.audit.log(AUDIT_MANUAL_MESSAGE, conversation_id=conversation_id)
    session.commit()
    return MessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        status=message.status,
        created_at=message.created_at,
    )
