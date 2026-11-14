# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging

from odoo.http import Controller, request, route

from ..tools.telnyx import verify_webhook_signature

_logger = logging.getLogger(__name__)

# Telnyx per-recipient delivery status -> core `sms.sms` state. Every value
# here is a key of `sms.tracker.SMS_STATE_TO_NOTIFICATION_STATUS`; anything
# absent from this map is ignored rather than guessed at, because an unknown
# status written as a state would raise a KeyError inside the tracker.
TELNYX_STATUS_TO_SMS_STATE = {
    "queued": "outgoing",
    "sending": "process",
    "sent": "pending",
    "delivered": "sent",
    "delivery_unconfirmed": "pending",
    "delivery_failed": "error",
    "sending_failed": "error",
    "expired": "error",
}
TELNYX_ERROR_STATUSES = frozenset({"delivery_failed", "sending_failed", "expired"})


class SmsTelnyxController(Controller):
    """Single webhook endpoint for the Telnyx messaging profile.

    Telnyx configures webhooks per messaging profile rather than per message, so
    one URL receives inbound messages and delivery receipts alike and dispatches
    on `data.event_type`.

    Budget: Telnyx expects a 2xx within **2 seconds** on API v2 and retries
    otherwise, so everything here stays inline and cheap -- a partner lookup and
    one `message_post`. There is no job queue in this deployment to defer to.
    """

    @route(
        "/sms_telnyx/webhook",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
        sitemap=False,
    )
    def telnyx_webhook(self, **kwargs):
        # Read the body BEFORE anything parses it: the signature covers the raw
        # bytes, and re-serialised JSON does not round-trip.
        raw_body = request.httprequest.get_data()
        companies = self._verify_signature(raw_body, request.httprequest.headers)
        if not companies:
            # One uniform rejection for every failure mode, so a prober learns
            # nothing about which check failed.
            _logger.warning("Telnyx webhook: rejected, signature verification failed")
            raise request.not_found()

        try:
            document = json.loads(raw_body)
            if not isinstance(document, dict):
                raise TypeError("Expected an object")
            event = document.get("data") or {}
            if not isinstance(event, dict) or not isinstance(
                event.get("payload", {}), dict
            ):
                raise TypeError("Expected an event object")
        except (TypeError, ValueError):
            _logger.warning("Telnyx webhook: rejected, body is not valid JSON")
            # `from None`: the JSON failure is the cause, not an error while
            # handling one, and the client must not learn which check failed.
            raise request.not_found() from None

        event_type = event.get("event_type")
        if event_type == "message.received":
            request.env["sms.telnyx.inbound"].sudo()._record_event(event, companies)
        elif event_type in ("message.sent", "message.finalized"):
            self._update_delivery(event, companies)
        else:
            _logger.info("Telnyx webhook: ignoring event type %s", event_type)
        return request.make_response("", headers=[("Content-Type", "text/plain")])

    def _verify_signature(self, raw_body, headers):
        """Verify against every configured Telnyx public key.

        The payload cannot be trusted to tell us which company -- and therefore
        which key -- to use, because that would mean parsing unverified input to
        decide how to verify it. With a handful of companies, trying each key is
        both safe and cheap: Ed25519 verification is microseconds, and a wrong
        key simply fails.

        No key configured means no verification is possible, so the request is
        rejected. Failing closed is the only safe default for a public route.
        """
        signature = headers.get("telnyx-signature-ed25519")
        timestamp = headers.get("telnyx-timestamp")
        if not (signature and timestamp):
            return request.env["res.company"].browse()
        companies = (
            request.env["res.company"]
            .sudo()
            .search(
                [
                    ("sms_telnyx_public_key", "!=", False),
                    ("sms_provider", "=", "telnyx"),
                ]
            )
        )
        if not companies:
            _logger.warning(
                "Telnyx webhook: no Telnyx public key configured, rejecting"
            )
            return companies
        return companies.filtered(
            lambda company: verify_webhook_signature(
                company.sms_telnyx_public_key, signature, timestamp, raw_body
            )
        )

    def _update_delivery(self, event, companies):
        """Apply a delivery receipt to the tracker that owns the Telnyx message id."""
        payload = event.get("payload") or {}
        message_id = payload.get("id")
        if not message_id:
            return
        tracker = (
            request.env["sms.tracker"]
            .sudo()
            .search(
                [
                    ("sms_telnyx_id", "=", message_id),
                    ("sms_telnyx_company_id", "in", companies.ids),
                ],
                limit=1,
            )
        )
        if not tracker:
            # Normal for anything this database did not send -- e.g. a message
            # sent from the Telnyx portal by hand.
            _logger.info("Telnyx webhook: no tracker for message %s", message_id)
            return
        to_entries = payload.get("to") or []
        status = (to_entries[0].get("status") if to_entries else None) or payload.get(
            "status"
        )
        state = TELNYX_STATUS_TO_SMS_STATE.get(status)
        if not state:
            _logger.info("Telnyx webhook: unmapped delivery status %s", status)
            return
        if status in TELNYX_ERROR_STATUSES:
            errors = payload.get("errors") or []
            error = errors[0] if errors else {}
            tracker._action_update_from_sms_state(
                "error",
                failure_type="unknown",
                failure_reason=error.get("detail") or error.get("title") or False,
            )
        else:
            tracker._action_update_from_sms_state(state)
