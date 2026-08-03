from __future__ import annotations

from typing import Any

from whatsapp_ai_sales.whatsapp.webhook import parse_meta_payload


class TestParseMetaPayload:
    def test_single_text_message(self) -> None:
        payload: dict[str, Any] = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "WABA_ID",
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "15551234567",
                                    "phone_number_id": "PHONE_NUMBER_ID",
                                },
                                "contacts": [
                                    {"profile": {"name": "John Doe"}, "wa_id": "16315551234"}
                                ],
                                "messages": [
                                    {
                                        "from": "16315551234",
                                        "id": "wamid.ABC123",
                                        "timestamp": "1700000000",
                                        "type": "text",
                                        "text": {
                                            "body": "I need 500 pieces shipped to Germany."
                                        },
                                    }
                                ],
                            }
                        }
                    ],
                }
            ],
        }

        parsed = parse_meta_payload(payload)

        assert len(parsed) == 1
        msg = parsed[0]
        assert msg.wa_id == "16315551234"
        assert msg.profile_name == "John Doe"
        assert msg.message_id == "wamid.ABC123"
        assert msg.text == "I need 500 pieces shipped to Germany."
        assert msg.timestamp == 1700000000

    def test_multiple_messages_in_one_entry(self) -> None:
        payload: dict[str, Any] = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "WABA_ID",
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "15551234567",
                                    "phone_number_id": "PHONE_NUMBER_ID",
                                },
                                "contacts": [
                                    {"profile": {"name": "John Doe"}, "wa_id": "16315551234"}
                                ],
                                "messages": [
                                    {
                                        "from": "16315551234",
                                        "id": "wamid.1",
                                        "timestamp": "1700000000",
                                        "type": "text",
                                        "text": {"body": "Hello"},
                                    },
                                    {
                                        "from": "16315551234",
                                        "id": "wamid.2",
                                        "timestamp": "1700000001",
                                        "type": "text",
                                        "text": {"body": "What is the price?"},
                                    },
                                ],
                            }
                        }
                    ],
                }
            ],
        }

        parsed = parse_meta_payload(payload)

        assert [m.message_id for m in parsed] == ["wamid.1", "wamid.2"]

    def test_non_text_message_is_skipped(self) -> None:
        payload: dict[str, Any] = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "WABA_ID",
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "15551234567",
                                    "phone_number_id": "PHONE_NUMBER_ID",
                                },
                                "contacts": [
                                    {"profile": {"name": "John Doe"}, "wa_id": "16315551234"}
                                ],
                                "messages": [
                                    {
                                        "from": "16315551234",
                                        "id": "wamid.image",
                                        "timestamp": "1700000000",
                                        "type": "image",
                                        "image": {"id": "MEDIA_ID", "mime_type": "image/jpeg"},
                                    },
                                    {
                                        "from": "16315551234",
                                        "id": "wamid.text",
                                        "timestamp": "1700000001",
                                        "type": "text",
                                        "text": {"body": "Please send a catalog"},
                                    },
                                ],
                            }
                        }
                    ],
                }
            ],
        }

        parsed = parse_meta_payload(payload)

        assert [m.message_id for m in parsed] == ["wamid.text"]

    def test_empty_payload_yields_no_messages(self) -> None:
        assert parse_meta_payload({}) == []
        assert parse_meta_payload({"object": "whatsapp_business_account", "entry": []}) == []
