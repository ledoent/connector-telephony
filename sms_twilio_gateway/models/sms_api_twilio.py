# Copyright 2025 Ledo Enterprises LLC - Don Kendall
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import json
import logging
import urllib.parse
import urllib.request

from odoo.addons.sms_alternative_provider.models.sms_api import SmsApiBase

_logger = logging.getLogger(__name__)

# Twilio error code → Odoo sms.sms state mapping.
# See https://www.twilio.com/docs/api/errors for full reference.
#
# "wrong_number_format" – the destination number is invalid or cannot receive SMS.
# "unregistered" – recipient has opted out (STOP) or the sender is not registered.
# "server_error" – everything else (auth failures, content filtering, etc.).
_TWILIO_ERROR_MAP = {
    # API-level number validation errors (HTTP 400)
    21211: "wrong_number_format",  # Invalid 'To' phone number
    21214: "wrong_number_format",  # 'To' number not reachable
    21217: "wrong_number_format",  # Invalid 'To' number for region
    21614: "wrong_number_format",  # Invalid mobile number
    # Delivery errors — permanent number issues (HTTP 200, delivery callback)
    30003: "wrong_number_format",  # Unreachable destination handset
    30005: "wrong_number_format",  # Unknown destination handset
    30006: "wrong_number_format",  # Landline or unreachable carrier
    # Carrier filtering / content policy
    30004: "server_error",  # Message blocked by carrier
    30007: "server_error",  # Message filtered (spam/policy)
    # Sender registration / compliance
    30024: "server_error",  # Numeric Sender ID not provisioned
    30032: "server_error",  # Toll-Free number not verified
    30034: "server_error",  # A2P 10DLC — unregistered number
    # Opt-out / consent
    21610: "unregistered",  # Recipient unsubscribed (STOP)
}


class SmsApiTwilio(SmsApiBase):
    KEY = "twilio"
    NAME = "Twilio"
    DESCRIPTION = (
        "Send SMS via the Twilio REST API using A2P 10DLC compliant "
        "Messaging Services. Supports Account Auth Token and API Key "
        "authentication. No external pip packages required."
    )

    def _send_sms_batch(self, messages, delivery_reports_url=False):
        """Send SMS messages one-by-one via Twilio REST API.

        Twilio does not support batch sending in a single request,
        so each message is sent individually.

        When a Messaging Service SID is configured the message is routed
        through the registered A2P campaign which is **required** for US
        10DLC delivery since December 2024.

        Odoo 18 message format::

            [{'content': str, 'numbers': [{'number': str, 'uuid': str}]}]

        Returns::

            [{'uuid': str, 'state': str}]
        """
        gateway = self._get_gateway()
        sid = gateway.twilio_account_sid
        from_number = gateway.twilio_from_number
        messaging_service_sid = gateway.twilio_messaging_service_sid
        status_callback_url = gateway.twilio_status_callback_url

        # Support both Auth Token and API Key authentication.
        # API Keys (SK…) are recommended for production — they can be
        # revoked individually without rotating the master Auth Token.
        if gateway.twilio_api_key_sid and gateway.twilio_api_key_secret:
            auth_user = gateway.twilio_api_key_sid
            auth_pass = gateway.twilio_api_key_secret
        else:
            auth_user = sid
            auth_pass = gateway.twilio_auth_token

        if not sid or not auth_pass:
            _logger.error("Twilio gateway %s missing credentials", gateway.name)
            return self._error_all(messages, "server_error")

        if not messaging_service_sid and not from_number:
            _logger.error(
                "Twilio gateway %s needs a Messaging Service SID or From Number",
                gateway.name,
            )
            return self._error_all(messages, "server_error")

        results = []
        for msg in messages:
            body = msg["content"]
            for num in msg["numbers"]:
                state = self._send_one(
                    sid=sid,
                    auth_user=auth_user,
                    auth_pass=auth_pass,
                    from_number=from_number,
                    messaging_service_sid=messaging_service_sid,
                    to_number=num["number"],
                    body=body,
                    status_callback_url=status_callback_url,
                )
                results.append({"uuid": num["uuid"], "state": state})
        return results

    def _get_gateway(self):
        """Find the active Twilio gateway record."""
        return (
            self.env["ir.sms.gateway"]
            .sudo()
            .search(
                [("gateway_type", "=", "twilio"), ("active", "=", True)],
                limit=1,
            )
        )

    @staticmethod
    def _error_all(messages, state):
        """Return *state* for every number across all messages."""
        return [
            {"uuid": num["uuid"], "state": state}
            for msg in messages
            for num in msg["numbers"]
        ]

    @staticmethod
    def _send_one(
        sid,
        auth_user,
        auth_pass,
        from_number,
        messaging_service_sid,
        to_number,
        body,
        status_callback_url=None,
    ):
        """Send a single SMS via Twilio REST API using stdlib only.

        Uses ``MessagingServiceSid`` when available so that the message is
        routed through the registered A2P 10DLC campaign.  Falls back to
        a direct ``From`` number when no Messaging Service is configured.
        """
        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"

        # Build request payload — prefer Messaging Service for A2P compliance.
        payload = {"To": to_number, "Body": body}
        if messaging_service_sid:
            payload["MessagingServiceSid"] = messaging_service_sid
        else:
            payload["From"] = from_number

        if status_callback_url:
            payload["StatusCallback"] = status_callback_url

        data = urllib.parse.urlencode(payload).encode()
        auth = base64.b64encode(f"{auth_user}:{auth_pass}".encode()).decode()
        req = urllib.request.Request(url, data=data)
        req.add_header("Authorization", f"Basic {auth}")

        try:
            resp = urllib.request.urlopen(req, timeout=15)
            result = json.loads(resp.read())
            _logger.info(
                "Twilio SMS sent to %s (SID %s, status %s)",
                to_number,
                result.get("sid"),
                result.get("status"),
            )
            return "success"
        except urllib.error.HTTPError as exc:
            return _handle_http_error(exc, to_number)
        except Exception:
            _logger.exception("Twilio error sending to %s", to_number)
            return "server_error"


def _handle_http_error(exc, to_number):
    """Map a Twilio HTTP error to an Odoo SMS state string."""
    error_body = exc.read().decode()
    _logger.error(
        "Twilio HTTP %s sending to %s: %s",
        exc.code,
        to_number,
        error_body,
    )
    try:
        err = json.loads(error_body)
        code = err.get("code", 0)
        state = _TWILIO_ERROR_MAP.get(code)
        if state:
            _logger.info("Twilio error %s mapped to Odoo state '%s'", code, state)
            return state
    except (json.JSONDecodeError, KeyError):
        _logger.debug("Could not parse Twilio error body")
    return "server_error"
