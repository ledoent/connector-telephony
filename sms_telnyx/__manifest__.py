# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Telnyx SMS",
    "summary": "Send and receive SMS messages through Telnyx",
    "version": "20.0.1.0.0",
    "category": "Hidden/Tools",
    "author": "Ledo Enterprises, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/connector-telephony",
    "license": "AGPL-3",
    "development_status": "Beta",
    "maintainers": ["dnplkndll"],
    "external_dependencies": {"python": ["cryptography", "phonenumbers", "requests"]},
    # sms_twilio owns the `res.company.sms_provider` selection and the
    # `sms.sms.record_company_id` / `_get_sms_company()` plumbing that any
    # per-company provider needs. Depending on it is cheaper and safer than
    # redefining the same field in a second module, which would make whichever
    # module loaded last silently own the selection.
    "depends": [
        "sms_twilio",
        "phone_validation",
    ],
    "data": [
        "security/ir.access.csv",
        "views/sms_telnyx_number_views.xml",
        "wizard/sms_telnyx_account_manage_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
}
