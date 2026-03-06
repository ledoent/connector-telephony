# Copyright 2025 Ledo Enterprises LLC - Don Kendall
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import json
import logging
import urllib.parse
import urllib.request

from odoo.addons.sms_alternative_provider.models.sms_api import SmsApiBase

_logger = logging.getLogger(__name__)


class SmsApiTwilio(SmsApiBase):
    KEY = "twilio"
    NAME = "Twilio"
    DESCRIPTION = (
        "Send SMS via the Twilio REST API. "
        "Requires an Account SID, Auth Token, and a Twilio phone number."
    )

    def _send_sms_batch(self, messages, delivery_reports_url=False):
        """Send SMS messages one-by-one via Twilio REST API.

        Twilio does not support batch sending in a single request,
        so each message is sent individually.

        Odoo 18 message format::

            [{'content': str, 'numbers': [{'number': str, 'uuid': str}]}]

        Returns::

            [{'uuid': str, 'state': str}]
        """
        gateway = self._get_gateway()
        sid = gateway.twilio_account_sid
        token = gateway.twilio_auth_token
        from_number = gateway.twilio_from_number
        if not all([sid, token, from_number]):
            _logger.error("Twilio gateway %s missing credentials", gateway.name)
            return [
                {"uuid": num["uuid"], "state": "server_error"}
                for msg in messages
                for num in msg["numbers"]
            ]
        results = []
        for msg in messages:
            body = msg["content"]
            for num in msg["numbers"]:
                state = self._send_one(sid, token, from_number, num["number"], body)
                results.append({"uuid": num["uuid"], "state": state})
        return results

    def _get_gateway(self):
        """Find the Twilio gateway record."""
        return (
            self.env["ir.sms.gateway"]
            .sudo()
            .search(
                [("gateway_type", "=", "twilio"), ("active", "=", True)],
                limit=1,
            )
        )

    @staticmethod
    def _send_one(sid, token, from_number, to_number, body):
        """Send a single SMS via Twilio REST API using stdlib only."""
        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
        data = urllib.parse.urlencode(
            {"From": from_number, "To": to_number, "Body": body}
        ).encode()
        auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
        req = urllib.request.Request(url, data=data)
        req.add_header("Authorization", f"Basic {auth}")
        try:
            resp = urllib.request.urlopen(req, timeout=15)
            result = json.loads(resp.read())
            _logger.info("Twilio SMS sent to %s (SID %s)", to_number, result.get("sid"))
            return "success"
        except urllib.error.HTTPError as exc:
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
                # 21211/21614 = invalid number, 21608 = unverified
                if code in (21211, 21614, 21217):
                    return "wrong_number_format"
            except (json.JSONDecodeError, KeyError):
                _logger.debug("Could not parse Twilio error body")
            return "server_error"
        except Exception:
            _logger.exception("Twilio error sending to %s", to_number)
            return "server_error"
