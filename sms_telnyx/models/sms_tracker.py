# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class SmsTracker(models.Model):
    _inherit = "sms.tracker"

    sms_telnyx_company_id = fields.Many2one("res.company", readonly=True, index=True)

    # Indexed because the delivery-receipt webhook looks a message up by it.
    # The tracker, not sms.sms, is the durable home for this: core deletes
    # sms.sms once it has been sent.
    sms_telnyx_id = fields.Char(
        string="Telnyx Message ID", readonly=True, index="btree_not_null"
    )
