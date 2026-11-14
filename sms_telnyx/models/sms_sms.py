# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from collections import defaultdict

from odoo import fields, models


class SmsSms(models.Model):
    _inherit = "sms.sms"

    sms_telnyx_id = fields.Char(
        related="sms_tracker_id.sms_telnyx_id", depends=["sms_tracker_id"]
    )

    def _split_by_api(self):
        """Route this company's SMS to Telnyx, and leave every other company alone.

        Same shape as `sms_twilio`'s override: claim only what belongs to this
        provider and hand the rest to `super()`, which lets twilio, IAP and
        telnyx coexist on one database with different companies on different
        providers.
        """
        sms_by_company = defaultdict(lambda: self.env["sms.sms"])
        todo_via_super = self.browse()
        for sms in self:
            sms_by_company[sms._get_sms_company()] += sms
        for company, company_sms in sms_by_company.items():
            if company.sms_provider == "telnyx":
                sms_api = company._get_sms_api_class()(self.env)
                sms_api._set_company(company)
                yield sms_api, company_sms
            else:
                todo_via_super += company_sms
        if todo_via_super:
            yield from super(SmsSms, todo_via_super)._split_by_api()

    def _handle_call_result_hook(self, results):
        """Persist the Telnyx message id on the tracker before sms.sms is deleted.

        This is the only link between an outbound message and the delivery
        receipt Telnyx posts later: unlike Twilio there is no per-message
        callback URL to carry our own uuid, because Telnyx webhooks are
        configured on the messaging profile.
        """
        telnyx_sms = self.filtered(
            lambda s: s._get_sms_company().sms_provider == "telnyx"
        )
        grouped = telnyx_sms.grouped("uuid")
        for result in results:
            sms = grouped.get(result.get("uuid"))
            if sms and sms.sms_tracker_id and result.get("sms_telnyx_id"):
                sms.sms_tracker_id.write(
                    {
                        "sms_telnyx_id": result["sms_telnyx_id"],
                        "sms_telnyx_company_id": sms._get_sms_company().id,
                    }
                )
        return super(SmsSms, self - telnyx_sms)._handle_call_result_hook(results)
