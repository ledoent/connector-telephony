# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import json
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from requests import Response

# Fictional messaging profile and example DID; tests need no Telnyx account.
PROFILE_ID = "40000000-0000-4000-8000-000000000001"
TEST_DID = "+12025550100"

# Every number in these tests must satisfy `phonenumbers.is_valid_number`, or
# `phone_sanitized` silently computes to False and nothing matches. The reserved
# ranges are exactly the trap: +1555xxxxxxx and the UK +441632/+447700 drama
# ranges all parse and are all INVALID, which cost four failing tests to learn.
TENANT_NUMBER = "+12202154155"
STRANGER_NUMBER = "+13125550001"
UK_NUMBER = "+442079460958"


class TelnyxCommon:
    """Shared fixtures: a throwaway Ed25519 key pair and a fake Telnyx API.

    The key pair is generated per test class rather than checked in, so the
    tests exercise real signature verification without a real account and
    without a secret in the repository.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.telnyx_private_key = Ed25519PrivateKey.generate()
        cls.telnyx_public_key = base64.b64encode(
            cls.telnyx_private_key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        ).decode()
        cls.telnyx_message_id = "40385f64-5717-4562-b3fc-2c963f66afa6"
        # Controls what the fake API returns; see _request_handler.
        cls.telnyx_api_status = 200
        cls.telnyx_api_body = {
            "data": {"id": cls.telnyx_message_id, "status": "queued"}
        }

    @classmethod
    def _setup_telnyx(cls, company, number=TEST_DID, country_xmlid="base.us"):
        company.sudo().write(
            {
                "sms_provider": "telnyx",
                "sms_telnyx_api_key": "KEY0123456789",
                "sms_telnyx_public_key": cls.telnyx_public_key,
                "sms_telnyx_messaging_profile_id": PROFILE_ID,
                "sms_telnyx_number_ids": [
                    (5, 0),
                    (
                        0,
                        0,
                        {
                            "number": number,
                            "country_id": cls.env.ref(country_xmlid).id,
                            "sequence": 1,
                        },
                    ),
                ],
            }
        )

    @classmethod
    def _request_handler(cls, session, request, **kwargs):
        """Intercept outbound calls to Telnyx; let everything else through."""
        if request.url.startswith("https://api.telnyx.com/v2/messages"):
            response = Response()
            response.status_code = cls.telnyx_api_status
            body = cls.telnyx_api_body
            response.json = lambda: body
            return response
        return super()._request_handler(session, request, **kwargs)

    # ------------------------------------------------------------------
    # Webhook helpers
    # ------------------------------------------------------------------

    def _telnyx_sign(self, raw_body, timestamp=None):
        timestamp = str(timestamp or int(time.time()))
        signature = base64.b64encode(
            self.telnyx_private_key.sign(timestamp.encode() + b"|" + raw_body)
        ).decode()
        return {
            "telnyx-signature-ed25519": signature,
            "telnyx-timestamp": timestamp,
        }

    def _inbound_event(self, from_number, to_number, text, event_id="evt-0001"):
        return {
            "data": {
                "event_type": "message.received",
                "id": event_id,
                "occurred_at": "2026-11-10T20:16:07.588+00:00",
                "record_type": "event",
                "payload": {
                    "direction": "inbound",
                    "from": {"phone_number": from_number, "carrier": "T-Mobile USA"},
                    "id": "84cca175-9755-4859-b67f-4730d7f58aa3",
                    "messaging_profile_id": PROFILE_ID,
                    "record_type": "message",
                    "text": text,
                    # `to` is a LIST inbound, unlike the plain string used when
                    # sending. Keep the shape honest so the test would catch a
                    # regression that assumed a string.
                    "to": [{"phone_number": to_number, "status": "webhook_delivered"}],
                    "type": "SMS",
                },
            },
            "meta": {"attempt": 1},
        }

    def _post_webhook(self, event, headers=None, mangle=False):
        raw_body = json.dumps(event).encode()
        signed = self._telnyx_sign(raw_body)
        if mangle:
            raw_body = raw_body.replace(b"message.received", b"message.rec3ived")
        return self.url_open(
            "/sms_telnyx/webhook",
            data=raw_body,
            headers={"Content-Type": "application/json", **signed, **(headers or {})},
        )
