# Copyright 2025 Ledo Enterprises LLC - Don Kendall
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class IrSmsGateway(models.Model):
    _inherit = "ir.sms.gateway"

    twilio_account_sid = fields.Char("Account SID")
    twilio_auth_token = fields.Char("Auth Token")
    twilio_from_number = fields.Char(
        "From Number",
        help="Twilio phone number in E.164 format, e.g. +14122846600",
    )
