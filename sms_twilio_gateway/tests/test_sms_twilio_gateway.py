# Copyright 2025 Ledo Enterprises LLC - Don Kendall
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import urllib.error
from unittest.mock import MagicMock, patch

from odoo.tests.common import TransactionCase

from ..models.sms_api_twilio import SmsApiTwilio

PATCH_URLOPEN = (
    "odoo.addons.sms_twilio_gateway.models.sms_api_twilio" ".urllib.request.urlopen"
)


class TestSmsTwilioGateway(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(
            context=dict(
                cls.env.context,
                mail_create_nosubscribe=True,
                mail_notify_noemail=True,
            )
        )
        # Remove default gateways
        cls.env["ir.sms.gateway"].search([]).unlink()
        cls.gateway = cls.env["ir.sms.gateway"].create(
            {
                "name": "Twilio Test",
                "gateway_type": "twilio",
                "twilio_account_sid": "ACtest123",
                "twilio_auth_token": "test_token",
                "twilio_from_number": "+15005550006",
            }
        )

    @staticmethod
    def _make_messages(number="+15551234567", content="Test message"):
        """Build an Odoo 18 format message batch."""
        return [
            {
                "content": content,
                "numbers": [{"number": number, "uuid": "test-uuid-001"}],
            }
        ]

    @staticmethod
    def _make_twilio_response(sid="SM123", status="queued"):
        """Build a mock Twilio API success response."""
        mock_resp = MagicMock()
        body = f'{{"sid": "{sid}", "status": "{status}"}}'
        mock_resp.read.return_value = body.encode()
        return mock_resp

    @staticmethod
    def _make_twilio_error(code, message, http_code=400, http_msg="Bad Request"):
        """Build a mock Twilio HTTP error response."""
        mock_resp = MagicMock()
        body = f'{{"code": {code}, "message": "{message}"}}'
        mock_resp.read.return_value = body.encode()
        return urllib.error.HTTPError(
            url="", code=http_code, msg=http_msg, hdrs={}, fp=mock_resp
        )

    def test_gateway_type_available(self):
        """Twilio should appear in gateway_type selection."""
        types = dict(self.gateway._compute_gateway_type())
        self.assertIn("twilio", types)

    def test_get_api_class(self):
        """Gateway should return the Twilio API class."""
        self.assertEqual(self.gateway._get_api_class(), SmsApiTwilio)

    # ---------------------------------------------------------------
    # Basic send
    # ---------------------------------------------------------------

    @patch(PATCH_URLOPEN)
    def test_send_sms_success(self, mock_urlopen):
        """Successful Twilio send returns state 'success' with uuid."""
        mock_urlopen.return_value = self._make_twilio_response()

        api = SmsApiTwilio(self.env)
        results = api._send_sms_batch(self._make_messages())
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["state"], "success")
        self.assertEqual(results[0]["uuid"], "test-uuid-001")
        mock_urlopen.assert_called_once()

    @patch(PATCH_URLOPEN)
    def test_send_multiple_numbers_same_body(self, mock_urlopen):
        """Multiple numbers with the same body each get their own result."""
        mock_urlopen.return_value = self._make_twilio_response()

        messages = [
            {
                "content": "Hello",
                "numbers": [
                    {"number": "+15551111111", "uuid": "uuid-1"},
                    {"number": "+15552222222", "uuid": "uuid-2"},
                ],
            }
        ]
        api = SmsApiTwilio(self.env)
        results = api._send_sms_batch(messages)
        self.assertEqual(len(results), 2)
        self.assertEqual(mock_urlopen.call_count, 2)
        self.assertEqual({r["uuid"] for r in results}, {"uuid-1", "uuid-2"})

    # ---------------------------------------------------------------
    # Messaging Service SID (A2P 10DLC)
    # ---------------------------------------------------------------

    @patch(PATCH_URLOPEN)
    def test_send_via_messaging_service(self, mock_urlopen):
        """When Messaging Service SID is set, use it instead of From number."""
        self.gateway.twilio_messaging_service_sid = "MGtest456"
        mock_urlopen.return_value = self._make_twilio_response()

        api = SmsApiTwilio(self.env)
        results = api._send_sms_batch(self._make_messages())
        self.assertEqual(results[0]["state"], "success")

        # Verify the request payload uses MessagingServiceSid, not From
        req = mock_urlopen.call_args[0][0]
        payload = req.data.decode()
        self.assertIn("MessagingServiceSid=MGtest456", payload)
        self.assertNotIn("From=", payload)

    @patch(PATCH_URLOPEN)
    def test_send_without_messaging_service_uses_from(self, mock_urlopen):
        """Without Messaging Service SID, falls back to From number."""
        self.gateway.twilio_messaging_service_sid = False
        mock_urlopen.return_value = self._make_twilio_response()

        api = SmsApiTwilio(self.env)
        api._send_sms_batch(self._make_messages())

        req = mock_urlopen.call_args[0][0]
        payload = req.data.decode()
        self.assertIn("From=%2B15005550006", payload)
        self.assertNotIn("MessagingServiceSid", payload)

    @patch(PATCH_URLOPEN)
    def test_status_callback_url_included(self, mock_urlopen):
        """Status callback URL is included in the request when configured."""
        self.gateway.twilio_status_callback_url = "https://example.com/status"
        mock_urlopen.return_value = self._make_twilio_response()

        api = SmsApiTwilio(self.env)
        api._send_sms_batch(self._make_messages())

        req = mock_urlopen.call_args[0][0]
        payload = req.data.decode()
        self.assertIn("StatusCallback=", payload)
        self.gateway.twilio_status_callback_url = False

    # ---------------------------------------------------------------
    # Authentication
    # ---------------------------------------------------------------

    @patch(PATCH_URLOPEN)
    def test_send_sms_api_key_auth(self, mock_urlopen):
        """API Key auth uses key SID and secret instead of account token."""
        self.gateway.write(
            {
                "twilio_auth_token": False,
                "twilio_api_key_sid": "SKtest123",
                "twilio_api_key_secret": "test_api_secret",
            }
        )
        mock_urlopen.return_value = self._make_twilio_response("SM456")

        api = SmsApiTwilio(self.env)
        results = api._send_sms_batch(self._make_messages())
        self.assertEqual(results[0]["state"], "success")

        # Verify the Authorization header uses API key, not account SID
        req = mock_urlopen.call_args[0][0]
        expected_auth = base64.b64encode(b"SKtest123:test_api_secret").decode()
        self.assertIn(expected_auth, req.get_header("Authorization"))

    # ---------------------------------------------------------------
    # Error handling
    # ---------------------------------------------------------------

    @patch(PATCH_URLOPEN)
    def test_send_sms_http_error(self, mock_urlopen):
        """HTTP error from Twilio returns state 'server_error'."""
        mock_urlopen.side_effect = self._make_twilio_error(
            20003, "Auth error", 401, "Unauthorized"
        )

        api = SmsApiTwilio(self.env)
        results = api._send_sms_batch(self._make_messages())
        self.assertEqual(results[0]["state"], "server_error")
        self.assertEqual(results[0]["uuid"], "test-uuid-001")

    @patch(PATCH_URLOPEN)
    def test_send_sms_invalid_number(self, mock_urlopen):
        """Twilio 21211 error maps to 'wrong_number_format'."""
        mock_urlopen.side_effect = self._make_twilio_error(21211, "Invalid To number")

        api = SmsApiTwilio(self.env)
        results = api._send_sms_batch(self._make_messages())
        self.assertEqual(results[0]["state"], "wrong_number_format")

    @patch(PATCH_URLOPEN)
    def test_landline_number_error(self, mock_urlopen):
        """Twilio 30006 (landline) maps to 'wrong_number_format'."""
        mock_urlopen.side_effect = self._make_twilio_error(
            30006, "Landline or unreachable carrier"
        )

        api = SmsApiTwilio(self.env)
        results = api._send_sms_batch(self._make_messages())
        self.assertEqual(results[0]["state"], "wrong_number_format")

    @patch(PATCH_URLOPEN)
    def test_carrier_blocked_error(self, mock_urlopen):
        """Twilio 30004 (carrier block) maps to 'server_error'."""
        mock_urlopen.side_effect = self._make_twilio_error(30004, "Message blocked")

        api = SmsApiTwilio(self.env)
        results = api._send_sms_batch(self._make_messages())
        self.assertEqual(results[0]["state"], "server_error")

    @patch(PATCH_URLOPEN)
    def test_unregistered_10dlc_error(self, mock_urlopen):
        """Twilio 30034 (unregistered A2P) maps to 'server_error'."""
        mock_urlopen.side_effect = self._make_twilio_error(
            30034, "Message from unregistered number"
        )

        api = SmsApiTwilio(self.env)
        results = api._send_sms_batch(self._make_messages())
        self.assertEqual(results[0]["state"], "server_error")

    @patch(PATCH_URLOPEN)
    def test_opt_out_error(self, mock_urlopen):
        """Twilio 21610 (STOP opt-out) maps to 'unregistered'."""
        mock_urlopen.side_effect = self._make_twilio_error(
            21610, "Recipient unsubscribed"
        )

        api = SmsApiTwilio(self.env)
        results = api._send_sms_batch(self._make_messages())
        self.assertEqual(results[0]["state"], "unregistered")

    # ---------------------------------------------------------------
    # Credential validation
    # ---------------------------------------------------------------

    def test_missing_credentials_returns_error(self):
        """Missing credentials returns server_error for all messages."""
        self.gateway.twilio_account_sid = False

        api = SmsApiTwilio(self.env)
        results = api._send_sms_batch(self._make_messages())
        self.assertEqual(results[0]["state"], "server_error")

    def test_missing_sender_returns_error(self):
        """Missing both Messaging Service and From number is an error."""
        self.gateway.twilio_from_number = False
        self.gateway.twilio_messaging_service_sid = False

        api = SmsApiTwilio(self.env)
        results = api._send_sms_batch(self._make_messages())
        self.assertEqual(results[0]["state"], "server_error")
