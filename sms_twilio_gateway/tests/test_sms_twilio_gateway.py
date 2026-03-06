# Copyright 2025 Ledo Enterprises LLC - Don Kendall
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import MagicMock, patch

from odoo.tests.common import TransactionCase

from ..models.sms_api_twilio import SmsApiTwilio


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

    def test_gateway_type_available(self):
        """Twilio should appear in gateway_type selection."""
        types = dict(self.gateway._compute_gateway_type())
        self.assertIn("twilio", types)

    def test_get_api_class(self):
        """Gateway should return the Twilio API class."""
        self.assertEqual(self.gateway._get_api_class(), SmsApiTwilio)

    @patch(
        "odoo.addons.sms_twilio_gateway.models.sms_api_twilio" ".urllib.request.urlopen"
    )
    def test_send_sms_success(self, mock_urlopen):
        """Successful Twilio send returns state 'success' with uuid."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"sid": "SM123", "status": "queued"}'
        mock_urlopen.return_value = mock_resp

        api = SmsApiTwilio(self.env)
        results = api._send_sms_batch(self._make_messages())
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["state"], "success")
        self.assertEqual(results[0]["uuid"], "test-uuid-001")
        mock_urlopen.assert_called_once()

    @patch(
        "odoo.addons.sms_twilio_gateway.models.sms_api_twilio" ".urllib.request.urlopen"
    )
    def test_send_sms_http_error(self, mock_urlopen):
        """HTTP error from Twilio returns state 'server_error'."""
        import urllib.error

        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"code": 20003, "message": "Auth error"}'
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="", code=401, msg="Unauthorized", hdrs={}, fp=mock_resp
        )

        api = SmsApiTwilio(self.env)
        results = api._send_sms_batch(self._make_messages())
        self.assertEqual(results[0]["state"], "server_error")
        self.assertEqual(results[0]["uuid"], "test-uuid-001")

    @patch(
        "odoo.addons.sms_twilio_gateway.models.sms_api_twilio" ".urllib.request.urlopen"
    )
    def test_send_sms_invalid_number(self, mock_urlopen):
        """Twilio 21211 error maps to 'wrong_number_format'."""
        import urllib.error

        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"code": 21211, "message": "Invalid To number"}'
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="", code=400, msg="Bad Request", hdrs={}, fp=mock_resp
        )

        api = SmsApiTwilio(self.env)
        results = api._send_sms_batch(self._make_messages())
        self.assertEqual(results[0]["state"], "wrong_number_format")

    def test_missing_credentials_returns_error(self):
        """Missing credentials returns server_error for all messages."""
        self.gateway.twilio_account_sid = False

        api = SmsApiTwilio(self.env)
        results = api._send_sms_batch(self._make_messages())
        self.assertEqual(results[0]["state"], "server_error")

    @patch(
        "odoo.addons.sms_twilio_gateway.models.sms_api_twilio" ".urllib.request.urlopen"
    )
    def test_send_multiple_numbers_same_body(self, mock_urlopen):
        """Multiple numbers with the same body each get their own result."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"sid": "SM123", "status": "queued"}'
        mock_urlopen.return_value = mock_resp

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
