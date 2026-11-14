# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    sms_telnyx_api_key = fields.Char(
        related="company_id.sms_telnyx_api_key",
        readonly=False,
        groups="base.group_system",
    )
    sms_telnyx_public_key = fields.Char(
        related="company_id.sms_telnyx_public_key",
        readonly=False,
        groups="base.group_system",
    )
    sms_telnyx_messaging_profile_id = fields.Char(
        related="company_id.sms_telnyx_messaging_profile_id",
        readonly=False,
        groups="base.group_system",
    )

    def action_open_sms_telnyx_account_manage(self):
        self.ensure_one()
        return self.company_id._action_open_sms_telnyx_account_manage()

    def action_open_sms_telnyx_numbers(self):
        self.ensure_one()
        return {
            "name": self.env._("Telnyx Numbers"),
            "type": "ir.actions.act_window",
            "res_model": "sms.telnyx.number",
            "view_mode": "list,form",
            "domain": [("company_id", "=", self.company_id.id)],
            "context": {"default_company_id": self.company_id.id},
        }
