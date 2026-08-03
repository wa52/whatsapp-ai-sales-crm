"""Scheduled follow-up runner: manual trigger endpoint and APScheduler wiring."""

from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI, Request
from sqlmodel import Session

from ..config import Settings
from ..deps import ProviderDep, SessionDep, require_admin
from ..messaging.audit import AuditLogger
from ..messaging.followup import FollowUpRunner
from ..messaging.outbound import retry_failed_outbound
from ..whatsapp.base import WhatsAppProvider

router = APIRouter(
    prefix="/api/followups",
    tags=["followups"],
    dependencies=[Depends(require_admin)],
)


@router.post("/run")
def run_followups(
    request: Request,
    session: SessionDep,
    provider: ProviderDep,
) -> dict[str, int]:
    """Manually trigger a follow-up scan (useful for demos and testing)."""
    settings: Settings = request.app.state.settings
    runner = _runner(session, provider, settings, request.app.state.audit)
    retried = retry_failed_outbound(session, provider)
    return {"sent": runner.run_due(), "retried": retried}


def _runner(
    session: Session,
    provider: WhatsAppProvider,
    settings: Settings,
    audit: AuditLogger | None,
) -> FollowUpRunner:
    return FollowUpRunner(
        session,
        provider,
        no_reply_hours=settings.followup_no_reply_hours,
        quote_hours=settings.followup_quote_hours,
        max_followups=settings.followup_max,
        no_reply_message=settings.followup_no_reply_message,
        quote_followup_message=settings.followup_quote_message,
        audit=audit,
    )


def start_followup_scheduler(app: FastAPI) -> None:
    """Start the periodic follow-up scan. Call explicitly from a worker entrypoint."""
    from apscheduler.schedulers.background import BackgroundScheduler

    settings: Settings = app.state.settings

    def job() -> None:
        with Session(app.state.engine) as session:
            retry_failed_outbound(session, app.state.provider)
            _runner(session, app.state.provider, settings, app.state.audit).run_due()

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
