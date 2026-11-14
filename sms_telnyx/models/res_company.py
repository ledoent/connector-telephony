# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models
from odoo.exceptions import UserError

from ..tools.sms_api import SmsApiTelnyx


class ResCompany(models.Model):
    _inherit = "res.company"

    # `sms_provider` is declared by core `sms_twilio`; extend rather than
    # redefine. `ondelete` is required because the field is stored.
    sms_provider = fields.Selection(
        selection_add=[("telnyx", "Send via Telnyx")],
        ondelete={"telnyx": "set default"},
    )
    sms_telnyx_api_key = fields.Char("Telnyx API Key", groups="base.group_system")
    sms_telnyx_public_key = fields.Char(
        "Telnyx Public Key",
        groups="base.group_system",
        help="Account-level Ed25519 public key, used to verify inbound webhooks. "
        "Found under Account > Keys & Credentials in the Telnyx portal.",
    )
    sms_telnyx_messaging_profile_id = fields.Char(
        "Telnyx Messaging Profile", groups="base.group_system"
    )
    sms_telnyx_number_ids = fields.One2many(
        "sms.telnyx.number", "company_id", "Telnyx Numbers"
    )

    def _get_sms_api_class(self):
        self.ensure_one()
        if self.sms_provider == "telnyx":
            return SmsApiTelnyx
        return super()._get_sms_api_class()

    def _action_open_sms_telnyx_account_manage(self):
        self.ensure_one()
        return {
            "name": self.env._("Manage Telnyx SMS"),
            "type": "ir.actions.act_window",
            "res_model": "sms.telnyx.account.manage",
            "views": [(False, "form")],
            "target": "new",
            "context": {**self.env.context, "default_company_id": self.id},
        }

    def _assert_telnyx_configured(self):
        """Fail loudly at configuration time rather than silently at send time."""
        self.ensure_one()
        if not self.sms_telnyx_api_key:
            raise UserError(
                self.env._("A Telnyx API key is required to send SMS through Telnyx.")
            )
        if not self.sms_telnyx_number_ids:
            raise UserError(self.env._("Add at least one Telnyx sending number."))
