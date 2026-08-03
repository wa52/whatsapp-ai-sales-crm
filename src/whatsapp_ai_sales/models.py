"""Domain models: customers, conversations, and messages."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel

from .messaging.handling import HANDLER_AI

ROLE_INBOUND = "inbound"
ROLE_OUTBOUND = "outbound"

STATUS_RECEIVED = "received"
STATUS_SENT = "sent"
STATUS_ACTIVE = "active"


def _now() -> datetime:
    return datetime.now(UTC)


class Customer(SQLModel, table=True):
    """A WhatsApp customer identified by their E.164 phone number."""

    id: int | None = Field(default=None, primary_key=True)
    wa_id: str = Field(index=True, unique=True)
    name: str | None = None
    country_code: str | None = None
    source_channel: str = "whatsapp"
    interested_product: str | None = None
    quantity: int | None = None
    budget: float | None = None
    purchase_time: str | None = None
    customer_type: str | None = None
    lead_score: int | None = None
    lead_level: str | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Conversation(SQLModel, table=True):
    """A chat thread between one customer and this business."""

    id: int | None = Field(default=None, primary_key=True)
    customer_id: int = Field(foreign_key="customer.id", index=True)
    status: str = Field(default=STATUS_ACTIVE, index=True)
    handler: str = Field(default=HANDLER_AI, index=True)
    dnd: bool = Field(default=False)
    followups_sent: int = Field(default=0)
    quote_sent: bool = Field(default=False)
    last_message_at: datetime | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Message(SQLModel, table=True):
    """A single message in a conversation."""

    id: int | None = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversation.id", index=True)
    role: str = Field(index=True)  # ROLE_INBOUND | ROLE_OUTBOUND
    provider_message_id: str | None = Field(default=None, index=True)
    content: str
    status: str = Field(default=STATUS_RECEIVED, index=True)
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


class PricingRule(SQLModel, table=True):
    """Program-authoritative pricing for one product (LLM never computes these)."""

    id: int | None = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id", unique=True, index=True)
    currency: str = "USD"
    standard_price: float
    min_price: float
    auto_deal_price: float
    sample_price: float | None = None
    discount_allowed: bool = True


class PriceTier(SQLModel, table=True):
    """Quantity-tier unit pricing belonging to a pricing rule."""

    id: int | None = Field(default=None, primary_key=True)
    rule_id: int = Field(foreign_key="pricingrule.id", index=True)
    min_quantity: int
    unit_price: float
