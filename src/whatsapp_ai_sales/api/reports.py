"""CRM dashboard report API."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..config import Settings
from ..deps import SessionDep
from ..reporting import ReportService

router = APIRouter(prefix="/api/reports", tags=["reports"])


class ReportOut(BaseModel):
    total_customers: int
    new_customers: int
    high_intent: int
    quotes_sent: int
    handoffs: int
    reply_rate: float
    ai_reply_success_rate: float
    countries: dict[str, int]


@router.get("/summary", response_model=ReportOut)
def summary(request: Request, session: SessionDep) -> ReportOut:
    settings: Settings = request.app.state.settings
    result = ReportService(session, fallback_reply=settings.fallback_reply).summary()
    return ReportOut(**result.__dict__)
