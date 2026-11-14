# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

import requests

from odoo.addons.sms.tools.sms_api import SmsApiBase

from .telnyx import TELNYX_MESSAGES_URL, get_from_number

_logger = logging.getLogger(__name__)

# Telnyx error code -> provider state. The provider states are mapped onto core
# `sms.sms.failure_type` values by PROVIDER_TO_SMS_FAILURE_TYPE below, and every
# one of those targets already exists in core. That is deliberate: this module
# adds no `selection_add` to sms.sms or mail.notification, so it cannot break a
# database by extending a selection that another module also extends. The human
# detail Telnyx returns is preserved in `failure_reason` instead.
TELNYX_CODE_TO_PROVIDER_STATE = {
    "40001": "wrong_number_format",  # not E.164
    "40002": "sms_number_missing",  # missing required field
    "40300": "sms_acc",  # `from` number not assigned to a messaging profile
    "42201": "wrong_number_format",  # invalid `to`
}


class SmsApiTelnyx(SmsApiBase):
    PROVIDER_TO_SMS_FAILURE_TYPE = SmsApiBase.PROVIDER_TO_SMS_FAILURE_TYPE | {
        "sms_acc": "sms_acc",
        "sms_credit": "sms_credit",
        "sms_server": "sms_server",
    }

    def _telnyx_send_request(self, session, to_number, body):
        """POST one message to Telnyx. Returns the response, None on transport error.

        Unlike Twilio there is no per-message status callback URL: Telnyx
        webhooks are configured on the messaging profile, so delivery receipts
        come back keyed by the Telnyx message id and are reconciled through
        `sms.tracker.sms_telnyx_id`.
        """
        company_sudo = (self.company or self.env.company).sudo()
        from_number = get_from_number(company_sudo, to_number)
        payload = {
            # Empty rather than "False", so a missing sender produces Telnyx's
            # own clear error instead of a nonsense number.
            "from": from_number.number or "",
            "to": to_number,
            "text": body,
        }
        if company_sudo.sms_telnyx_messaging_profile_id:
            payload["messaging_profile_id"] = (
                company_sudo.sms_telnyx_messaging_profile_id
            )
        try:
            return session.post(
                TELNYX_MESSAGES_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {company_sudo.sms_telnyx_api_key or ''}",
                    "Content-Type": "application/json",
                },
                timeout=10,
            )
        except requests.exceptions.RequestException as err:
            # Never log the payload: it carries the recipient and the message body.
            _logger.warning("Telnyx SMS API transport error: %s", err)
        return None

    def _send_sms_batch(self, messages, delivery_reports_url=False):
        """Send a batch of SMS through Telnyx.

        See params and returns in the original ``sms/tools/sms_api.py``. In
        addition to uuid and state, each result carries ``sms_telnyx_id`` so
        ``sms.sms._handle_call_result_hook`` can persist it on the tracker
        before the sms.sms record is deleted.
        """
        session = requests.Session()
        results = []
        for message in messages:
            body = message.get("content") or ""
            for number_info in message.get("numbers") or []:
                response = self._telnyx_send_request(
                    session, number_info["number"], body
                )
                values = {
                    "failure_reason": self.env._(
                        "Unknown failure at sending, please contact your administrator"
                    ),
                    "state": "server_error",
                    "uuid": number_info["uuid"],
                }
                if response is not None:
                    values.update(self._telnyx_parse_response(response))
                results.append(values)
        return results

    def _telnyx_parse_response(self, response):
        try:
            response_json = response.json()
        except ValueError:
            return {
                "state": "sms_server",
                "failure_reason": self.env._(
                    "Telnyx returned a non-JSON response (HTTP %s)",
                    response.status_code,
                ),
            }
        if response.ok and not response_json.get("errors"):
            return {
                "failure_reason": False,
                "failure_type": False,
                "sms_telnyx_id": (response_json.get("data") or {}).get("id"),
                "state": "sent",
            }
        error = (response_json.get("errors") or [{}])[0]
        state = self._telnyx_error_to_provider_state(response.status_code, error)
        return {
            "failure_reason": error.get("detail") or error.get("title") or False,
            "failure_type": state,
            "state": state,
        }

    def _telnyx_error_to_provider_state(self, status_code, error):
        code = str(error.get("code") or "")
        if code in TELNYX_CODE_TO_PROVIDER_STATE:
            return TELNYX_CODE_TO_PROVIDER_STATE[code]
        if status_code in (401, 403):
            return "sms_acc"
        if status_code == 402:
            return "sms_credit"
        if status_code == 429 or status_code >= 500:
            # Retryable at the carrier; surfaced as a server error so an
            # operator can re-queue rather than treating it as a bad number.
            return "sms_server"
        _logger.warning(
            "Telnyx SMS: unmapped error (HTTP %s, code %s): %s",
            status_code,
            code or "-",
            error.get("title") or "",
        )
        return "unknown"

    def _get_sms_api_error_messages(self):
        error_dict = super()._get_sms_api_error_messages()
        error_dict.update(
            {
                "sms_acc": self.env._(
                    "Telnyx rejected the request: check the API key and that "
                    "the sending number is assigned to the messaging profile"
                ),
                "sms_credit": self.env._("Insufficient Telnyx balance"),
                "sms_number_missing": self.env._("A 'To' phone number is required"),
                "sms_server": self.env._(
                    "Telnyx is temporarily unavailable, please retry"
                ),
                "wrong_number_format": self.env._(
                    "The number you're trying to reach is not correctly formatted"
                ),
                "unknown": self.env._(
                    "Unknown Telnyx error, see the server log for details"
                ),
            }
        )
        return error_dict
