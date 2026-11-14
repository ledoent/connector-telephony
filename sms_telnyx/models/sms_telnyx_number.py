# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class SmsTelnyxNumber(models.Model):
    """A Telnyx DID this database may send from, and receive on.

    Deliberately mirrors core's `sms.twilio.number` so the two providers are
    configured the same way. The `company_id` on the matched number is also how
    an inbound webhook decides which company a message belongs to -- see
    `sms.telnyx.inbound._company_from_number`.
    """

    _name = "sms.telnyx.number"
    _description = "Telnyx Number"
    _order = "sequence, id"

    company_id = fields.Many2one(
        "res.company",
        required=True,
        ondelete="cascade",
        index="btree",
        default=lambda self: self.env.company,
    )
    sequence = fields.Integer(default=1)
    number = fields.Char(string="Telnyx Number", required=True)
    country_id = fields.Many2one("res.country", required=True)
    country_code = fields.Char(related="country_id.code", string="Country Code")

    _number_unique = models.Constraint(
        "unique(number)", "A Telnyx number can belong to only one company."
    )

    def _compute_display_name(self):
        for record in self:
            record.display_name = f"{record.number} ({record.country_id.name})"
