# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from uuid import uuid4

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..tools.sms_api import SmsApiTelnyx
from ..tools.telnyx import get_from_number


class SmsTelnyxAccountManage(models.TransientModel):
    _name = "sms.telnyx.account.manage"
    _description = "SMS Telnyx Connection Wizard"

    company_id = fields.Many2one(
        "res.company",
        required=True,
        readonly=True,
        default=lambda self: self.env.company,
    )
    sms_telnyx_api_key = fields.Char(
        related="company_id.sms_telnyx_api_key", readonly=False
    )
    sms_telnyx_public_key = fields.Char(
        related="company_id.sms_telnyx_public_key", readonly=False
    )
    sms_telnyx_messaging_profile_id = fields.Char(
        related="company_id.sms_telnyx_messaging_profile_id", readonly=False
    )
    sms_telnyx_number_ids = fields.One2many(
        related="company_id.sms_telnyx_number_ids", readonly=False
    )
    webhook_url = fields.Char(compute="_compute_webhook_url")
    test_number = fields.Char()

    @api.depends("company_id")
    def _compute_webhook_url(self):
        for wizard in self:
            wizard.webhook_url = (
                wizard.company_id.get_base_url().rstrip("/") + "/sms_telnyx/webhook"
            )

    def action_send_test(self):
        self.ensure_one()
        self.company_id._assert_telnyx_configured()
        number = (
            self.env.user.with_company(self.company_id)._phone_format(
                number=self.test_number
            )
            if self.test_number
            else False
        )
        if not number:
            raise UserError(
                self.env._("Enter a valid test number in international format.")
            )
        if self.env["phone.blacklist"].sudo().search_count([("number", "=", number)]):
            raise UserError(self.env._("This number has opted out of SMS messages."))
        # The Settings radio may not have been saved yet. Choose Telnyx
        # explicitly rather than dispatching through the current provider.
        sms_api = SmsApiTelnyx(self.env)
        sms_api._set_company(self.company_id)
        result = sms_api._send_sms_batch(
            [
                {
                    "content": self.env._("This is a test SMS from Odoo (Telnyx)."),
                    "numbers": [{"number": number, "uuid": uuid4().hex}],
                }
            ]
        )[0]
        accepted = result.get("state") == "sent"
        message = (
            self.env._(
                "Telnyx accepted the test SMS from %s.",
                get_from_number(self.company_id, number).number,
            )
            if accepted
            else result.get("failure_reason")
            or self.env._(
                "Telnyx could not accept the test SMS. "
                "Check your account configuration."
            )
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("Telnyx SMS"),
                "message": message,
                "type": "success" if accepted else "danger",
                "sticky": not accepted,
            },
        }

    def action_save(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window_close"}
