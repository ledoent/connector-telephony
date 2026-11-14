# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from .common import TENANT_NUMBER, TelnyxCommon


@tagged("post_install", "-at_install", "telnyx")
class TestTelnyxAccountManage(TelnyxCommon, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_telnyx(cls.env.company)

    def test_settings_opens_modal_for_selected_company(self):
        other = self.env["res.company"].create({"name": "Selected company"})
        settings = self.env["res.config.settings"].create({"company_id": other.id})
        action = settings.action_open_sms_telnyx_account_manage()
        self.assertEqual(action["target"], "new")
        wizard = (
            self.env[action["res_model"]].with_context(**action["context"]).create({})
        )
        self.assertEqual(wizard.company_id, other)
        self.assertTrue(wizard.webhook_url.endswith("/sms_telnyx/webhook"))

    def test_credentials_update_selected_company(self):
        other = self.env["res.company"].create({"name": "Configured company"})
        wizard = self.env["sms.telnyx.account.manage"].create(
            {
                "company_id": other.id,
                "sms_telnyx_api_key": "another-test-key",
            }
        )
        wizard.action_save()
        self.assertEqual(other.sms_telnyx_api_key, "another-test-key")
        self.assertEqual(self.env.company.sms_telnyx_api_key, "KEY0123456789")

    def test_test_sms_uses_telnyx_before_provider_selection_is_saved(self):
        self.env.company.sms_provider = "iap"
        wizard = self.env["sms.telnyx.account.manage"].create(
            {
                "company_id": self.env.company.id,
                "test_number": TENANT_NUMBER,
            }
        )
        result = wizard.action_send_test()
        self.assertEqual(result["params"]["type"], "success")
        self.assertIn("Telnyx accepted", result["params"]["message"])
        self.assertEqual(self.env.company.sms_provider, "iap")

    def test_test_sms_requires_a_recipient(self):
        wizard = self.env["sms.telnyx.account.manage"].create(
            {
                "company_id": self.env.company.id,
            }
        )
        with self.assertRaises(UserError):
            wizard.action_send_test()

    def test_test_sms_honors_opt_out(self):
        self.env["phone.blacklist"].sudo()._add([TENANT_NUMBER])
        wizard = self.env["sms.telnyx.account.manage"].create(
            {
                "company_id": self.env.company.id,
                "test_number": TENANT_NUMBER,
            }
        )
        with self.assertRaises(UserError):
            wizard.action_send_test()

    def test_test_sms_reports_provider_rejection(self):
        type(self).telnyx_api_status = 403
        type(self).telnyx_api_body = {
            "errors": [{"code": "40300", "detail": "Wrong profile"}]
        }
        self.addCleanup(self._reset_api_mock)
        wizard = self.env["sms.telnyx.account.manage"].create(
            {
                "company_id": self.env.company.id,
                "test_number": TENANT_NUMBER,
            }
        )
        result = wizard.action_send_test()
        self.assertEqual(result["params"]["type"], "danger")
        self.assertEqual(result["params"]["message"], "Wrong profile")

    def _reset_api_mock(self):
        type(self).telnyx_api_status = 200
        type(self).telnyx_api_body = {
            "data": {"id": self.telnyx_message_id, "status": "queued"}
        }
