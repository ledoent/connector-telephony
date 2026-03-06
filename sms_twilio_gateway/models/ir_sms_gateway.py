# Copyright 2025 Ledo Enterprises LLC - Don Kendall
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class IrSmsGateway(models.Model):
    _inherit = "ir.sms.gateway"

    twilio_account_sid = fields.Char("Account SID")
    twilio_auth_token = fields.Char(
        "Auth Token",
        help="Account Auth Token, or leave blank to use API Key authentication.",
    )
    twilio_api_key_sid = fields.Char(
        "API Key SID",
        help="Optional. If set, authentication uses API Key (SK...) "
        "instead of Account Auth Token.",
    )
    twilio_api_key_secret = fields.Char(
        "API Key Secret",
        help="Required when API Key SID is set.",
    )
    twilio_messaging_service_sid = fields.Char(
        "Messaging Service SID",
        help="Optional. If set, messages are sent via this Messaging Service "
        "(MG...) instead of a direct From number. Required for US A2P "
        "10DLC compliance when sending to US numbers.",
    )
    twilio_from_number = fields.Char(
        "From Number",
        help="Twilio phone number in E.164 format, e.g. +14122846600. "
        "Used as fallback when no Messaging Service SID is configured.",
    )
    twilio_status_callback_url = fields.Char(
        "Status Callback URL",
        help="Optional. Twilio will POST delivery status updates to this URL. "
        "Useful for tracking delivery confirmations and failures.",
    )
