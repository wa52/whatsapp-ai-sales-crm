from whatsapp_ai_sales.messaging.handling import HandoffSignals, should_handoff
from whatsapp_ai_sales.messaging.notification import NotificationEvent, RecordingNotifier


def test_no_signals_no_handoff() -> None:
    assert should_handoff(HandoffSignals()) is False


def test_fall_back_triggers_handoff() -> None:
    assert should_handoff(HandoffSignals(fell_back=True)) is True


def test_need_human_triggers_handoff() -> None:
    assert should_handoff(HandoffSignals(need_human=True)) is True


def test_human_verdict_triggers_handoff() -> None:
    assert should_handoff(HandoffSignals(verdict_human=True)) is True


def test_recording_notifier_captures_events() -> None:
    notifier = RecordingNotifier()

    notifier.notify(NotificationEvent(kind="handoff", wa_id="4912345678", details="x"))

    assert len(notifier.events) == 1
    assert notifier.events[0].kind == "handoff"
    assert notifier.events[0].wa_id == "4912345678"
