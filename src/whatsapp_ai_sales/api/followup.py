"""Scheduled follow-up runner: manual trigger endpoint and APScheduler wiring."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, Request
from sqlmodel import Session

from ..config import Settings
from ..deps import ProviderDep, SessionDep
from ..messaging.followup import FollowUpRunner
from ..whatsapp.base import WhatsAppProvider

router = APIRouter(prefix="/api/followups", tags=["followups"])


@router.post("/run")
def run_followups(
    request: Request,
    session: SessionDep,
    provider: ProviderDep,
) -> dict[str, int]:
    """Manually trigger a follow-up scan (useful for demos and testing)."""
    settings: Settings = request.app.state.settings
    runner = _runner(session, provider, settings)
    return {"sent": runner.run_due()}


def _runner(session: Session, provider: WhatsAppProvider, settings: Settings) -> FollowUpRunner:
    return FollowUpRunner(
        session,
        provider,
        no_reply_hours=settings.followup_no_reply_hours,
        quote_hours=settings.followup_quote_hours,
        max_followups=settings.followup_max,
        no_reply_message=settings.followup_no_reply_message,
        quote_followup_message=settings.followup_quote_message,
    )


def start_followup_scheduler(app: FastAPI) -> None:
    """Start the periodic follow-up scan. Call explicitly from a worker entrypoint."""
    from apscheduler.schedulers.background import BackgroundScheduler

    settings: Settings = app.state.settings

    def job() -> None:
        with Session(app.state.engine) as session:
            _runner(session, app.state.provider, settings).run_due()

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        job,
        "interval",
        seconds=settings.followup_interval_seconds,
        id="followup_job",
        max_instances=1,
    )
    scheduler.start()
    app.state.scheduler = scheduler
