"""Domain models: customers, conversations, and messages."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(UTC)


class Customer(SQLModel, table=True):
    """A WhatsApp customer identified by their E.164 phone number."""

    id: int | None = Field(default=None, primary_key=True)
    wa_id: str = Field(index=True, unique=True)
    name: str | None = None
    country_code: str | None = None
    source_channel: str = "whatsapp"
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Conversation(SQLModel, table=True):
    """A chat thread between one customer and this business."""

    id: int | None = Field(default=None, primary_key=True)
    customer_id: int = Field(foreign_key="customer.id", index=True)
    status: str = Field(default="active", index=True)
    handler: str = Field(default="ai", index=True)
    last_message_at: datetime | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Message(SQLModel, table=True):
    """A single message in a conversation."""

    id: int | None = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversation.id", index=True)
    role: str = Field(index=True)  # "inbound" | "outbound"
    provider_message_id: str | None = Field(default=None, index=True)
    content: str
    status: str = Field(default="received", index=True)
    created_at: datetime = Field(default_factory=_now)


class Product(SQLModel, table=True):
    """A product whose knowledge is searchable by the RAG pipeline."""

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    sku: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_now)


class KnowledgeChunk(SQLModel, table=True):
    """A labeled slice of product knowledge, the unit RAG retrieves."""

    id: int | None = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    section: str = Field(index=True)
    content: str
    created_at: datetime = Field(default_factory=_now)
