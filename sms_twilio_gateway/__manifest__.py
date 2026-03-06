# Copyright 2025 Ledo Enterprises LLC - Don Kendall
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "SMS Twilio Gateway",
    "version": "18.0.1.0.0",
    "category": "Tools",
    "summary": "Send SMS via Twilio using the alternative provider framework.",
    "author": "Ledo Enterprises LLC, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/connector-telephony",
    "license": "AGPL-3",
    "depends": [
        "sms_alternative_provider",
    ],
    "data": [
        "views/ir_sms_gateway.xml",
    ],
    "installable": True,
}
