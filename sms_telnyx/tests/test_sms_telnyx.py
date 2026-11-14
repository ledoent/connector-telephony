# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import time

from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from ..tools.sms_api import SmsApiTelnyx
from ..tools.telnyx import (
    get_from_number,
    verify_webhook_signature,
)
from .common import TENANT_NUMBER, TEST_DID, UK_NUMBER, TelnyxCommon


@tagged("post_install", "-at_install", "telnyx")
class TestSmsTelnyx(TelnyxCommon, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_telnyx(cls.env.company)
        cls.partner = cls.env["res.partner"].create(
            {"name": "Tenant", "phone": TENANT_NUMBER}
        )

    # ------------------------------------------------------------------
    # Provider wiring
    # ------------------------------------------------------------------

    def test_provider_class_selected(self):
        self.assertEqual(self.env.company.sms_provider, "telnyx")
        self.assertIs(self.env.company._get_sms_api_class(), SmsApiTelnyx)

    def test_from_number_follows_destination_country(self):
        company = self.env.company.sudo()
        self.env["sms.telnyx.number"].create(
            {
                "number": UK_NUMBER,
                "country_id": self.env.ref("base.uk").id,
                "company_id": company.id,
                "sequence": 5,
            }
        )
        company.invalidate_recordset(["sms_telnyx_number_ids"])
        # A GB destination must pick the GB sender over the US one...
        self.assertEqual(get_from_number(company, UK_NUMBER).number, UK_NUMBER)
        # ...and a US destination must still pick the US one, even though the
        # GB number sorts later by sequence.
        self.assertEqual(get_from_number(company, TENANT_NUMBER).number, TEST_DID)

    # ------------------------------------------------------------------
    # Outbound
    # ------------------------------------------------------------------

    def test_outbound_stores_telnyx_message_id(self):
        self.partner._message_sms(body="Arrival window 2-4pm")
        sms = self.env["sms.sms"].sudo().search([("partner_id", "=", self.partner.id)])
        self.assertTrue(sms, "an sms.sms should be queued for the partner")
        sms.send(unlink_sent=False)
        self.assertFalse(sms.failure_type)
        self.assertEqual(
            sms.sms_telnyx_id,
            self.telnyx_message_id,
            "the Telnyx id must live on the tracker: sms.sms is deleted once sent",
        )

    def test_outbound_error_maps_to_core_failure_type(self):
        # Set on the CLASS, not the instance: _request_handler is a classmethod
        # and would never see an instance attribute.
        type(self).telnyx_api_status = 403
        type(self).telnyx_api_body = {
            "errors": [
                {
                    "code": "40300",
                    "title": "Forbidden",
                    "detail": "The from number is not assigned to a messaging profile.",
                }
            ]
        }
        self.addCleanup(self._reset_api_mock)
        self.partner._message_sms(body="This will fail")
        sms = self.env["sms.sms"].sudo().search([("partner_id", "=", self.partner.id)])
        sms.send(unlink_sent=False)
        self.assertEqual(sms.state, "error")
        self.assertEqual(
            sms.failure_type,
            "sms_acc",
            "Telnyx 40300 must map onto a core failure_type, not a new value",
        )

    def _reset_api_mock(self):
        type(self).telnyx_api_status = 200
        type(self).telnyx_api_body = {
            "data": {"id": self.telnyx_message_id, "status": "queued"}
        }

    # ------------------------------------------------------------------
    # Signature primitive
    # ------------------------------------------------------------------

    def test_signature_roundtrip(self):
        body = b'{"data":{"event_type":"message.received"}}'
        headers = self._telnyx_sign(body)
        self.assertTrue(
            verify_webhook_signature(
                self.telnyx_public_key,
                headers["telnyx-signature-ed25519"],
                headers["telnyx-timestamp"],
                body,
            )
        )

    def test_signature_rejects_tampered_body(self):
        body = b'{"data":{"event_type":"message.received"}}'
        headers = self._telnyx_sign(body)
        self.assertFalse(
            verify_webhook_signature(
                self.telnyx_public_key,
                headers["telnyx-signature-ed25519"],
                headers["telnyx-timestamp"],
                body + b" ",
            )
        )

    @mute_logger("odoo.addons.sms_telnyx.tools.telnyx")
    def test_signature_rejects_stale_timestamp(self):
        body = b'{"data":{}}'
        stale = int(time.time()) - 4000
        headers = self._telnyx_sign(body, timestamp=stale)
        self.assertFalse(
            verify_webhook_signature(
                self.telnyx_public_key,
                headers["telnyx-signature-ed25519"],
                headers["telnyx-timestamp"],
                body,
            ),
            "a replayed webhook outside the tolerance window must be rejected",
        )

    def test_signature_rejects_missing_key(self):
        body = b'{"data":{}}'
        headers = self._telnyx_sign(body)
        self.assertFalse(
            verify_webhook_signature(
                False,
                headers["telnyx-signature-ed25519"],
                headers["telnyx-timestamp"],
                body,
            ),
            "no configured public key means no verification is possible: fail closed",
        )
