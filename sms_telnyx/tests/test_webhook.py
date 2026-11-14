# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger

from .common import STRANGER_NUMBER, TENANT_NUMBER, TEST_DID, TelnyxCommon

WEBHOOK_LOGGER = "odoo.addons.sms_telnyx.controllers.main"
INBOUND_LOGGER = "odoo.addons.sms_telnyx.models.sms_telnyx_inbound"


@tagged("post_install", "-at_install", "telnyx", "telnyx_webhook")
class TestTelnyxWebhook(TelnyxCommon, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_telnyx(cls.env.company)
        cls.did = TEST_DID
        cls.tenant = cls.env["res.partner"].create(
            {"name": "Tenant", "phone": TENANT_NUMBER}
        )

    def _inbound(
        self, text="The heat is out in unit 4", event_id="evt-0001", sender=None
    ):
        return self._inbound_event(
            sender or self.tenant.phone, self.did, text, event_id=event_id
        )

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_inbound_posts_on_partner_chatter(self):
        response = self._post_webhook(self._inbound())
        self.assertEqual(response.status_code, 200)

        record = self.env["sms.telnyx.inbound"].search(
            [("telnyx_event_id", "=", "evt-0001")]
        )
        self.assertEqual(len(record), 1)
        self.assertEqual(record.state, "posted")
        self.assertEqual(record.partner_id, self.tenant)
        self.assertEqual(record.company_id, self.env.company)
        self.assertEqual(record.res_model, "res.partner")
        self.assertEqual(record.res_id, self.tenant.id)

        message = record.message_id
        self.assertTrue(message)
        self.assertEqual(message.message_type, "sms")
        self.assertEqual(message.author_id, self.tenant)
        self.assertIn("heat is out", message.body)

    def test_company_resolved_from_the_dialled_number(self):
        """The sender says nothing about which entity was contacted; the DID does."""
        record = self.env["sms.telnyx.inbound"]
        self._post_webhook(self._inbound())
        self.assertEqual(
            record.search([("telnyx_event_id", "=", "evt-0001")]).company_id,
            self.env["sms.telnyx.number"]
            .search([("number", "=", self.did)])
            .company_id,
        )

    @mute_logger(INBOUND_LOGGER)
    def test_unknown_recipient_does_not_fall_back_to_main_company(self):
        event = self._inbound_event(TENANT_NUMBER, STRANGER_NUMBER, "Unknown DID")
        self.assertEqual(self._post_webhook(event).status_code, 200)
        self.assertFalse(self.env["sms.telnyx.inbound"].search([]))

    @mute_logger(INBOUND_LOGGER)
    def test_signature_cannot_authorize_another_company_recipient(self):
        other = self.env["res.company"].create({"name": "Other account"})
        self.env["sms.telnyx.number"].search(
            [("number", "=", self.did)]
        ).company_id = other
        self.assertEqual(self._post_webhook(self._inbound()).status_code, 200)
        self.assertFalse(self.env["sms.telnyx.inbound"].search([]))

    @mute_logger(INBOUND_LOGGER)
    def test_wrong_messaging_profile_is_ignored(self):
        event = self._inbound()
        event["data"]["payload"]["messaging_profile_id"] = "another-profile"
        self.assertEqual(self._post_webhook(event).status_code, 200)
        self.assertFalse(self.env["sms.telnyx.inbound"].search([]))

    def test_partner_in_other_company_is_not_matched(self):
        other = self.env["res.company"].create({"name": "Other company"})
        self.tenant.company_id = other
        self._post_webhook(self._inbound())
        record = self.env["sms.telnyx.inbound"].search([])
        self.assertEqual(record.state, "unmatched")
        self.assertFalse(record.partner_id)

    @mute_logger(INBOUND_LOGGER)
    def test_ambiguous_partner_is_not_selected_arbitrarily(self):
        self.tenant.copy({"name": "Same phone, another contact"})
        self._post_webhook(self._inbound())
        record = self.env["sms.telnyx.inbound"].search([])
        self.assertEqual(record.state, "unmatched")
        self.assertFalse(record.partner_id)

    def test_employee_cannot_read_other_company_inbound(self):
        from odoo.exceptions import AccessError
        from odoo.tests.common import new_test_user

        self._post_webhook(self._inbound())
        record = self.env["sms.telnyx.inbound"].search([])
        other = self.env["res.company"].create({"name": "Other company"})
        employee = new_test_user(
            self.env,
            login="telnyx_other",
            groups="base.group_user",
            company_id=other.id,
            company_ids=[(6, 0, other.ids)],
        )
        with self.assertRaises(AccessError):
            record.with_user(employee).read(["body"])

    # ------------------------------------------------------------------
    # Rejection and idempotency
    # ------------------------------------------------------------------

    @mute_logger(WEBHOOK_LOGGER)
    def test_tampered_body_is_rejected(self):
        response = self._post_webhook(self._inbound(), mangle=True)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.env["sms.telnyx.inbound"].search([]))

    @mute_logger(WEBHOOK_LOGGER)
    def test_unsigned_request_is_rejected(self):
        response = self.url_open(
            "/sms_telnyx/webhook",
            data=json.dumps(self._inbound()).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.env["sms.telnyx.inbound"].search([]))

    @mute_logger(WEBHOOK_LOGGER)
    def test_signature_from_another_key_is_rejected(self):
        self.env.company.sudo().sms_telnyx_public_key = (
            "Zm9vYmFyZm9vYmFyZm9vYmFyZm9vYmFyMTIzNDU2Nzg="
        )
        response = self._post_webhook(self._inbound())
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.env["sms.telnyx.inbound"].search([]))

    def test_replayed_event_is_a_no_op(self):
        """Telnyx retries anything that misses the 2s budget, so replays are normal."""
        self._post_webhook(self._inbound())
        self._post_webhook(self._inbound())
        records = self.env["sms.telnyx.inbound"].search(
            [("telnyx_event_id", "=", "evt-0001")]
        )
        self.assertEqual(
            len(records), 1, "a replayed event must not duplicate the message"
        )
        self.assertEqual(
            self.env["mail.message"].search_count(
                [
                    ("model", "=", "res.partner"),
                    ("res_id", "=", self.tenant.id),
                    ("message_type", "=", "sms"),
                ]
            ),
            1,
        )

    # ------------------------------------------------------------------
    # Unknown sender and consent
    # ------------------------------------------------------------------

    def test_matches_a_partner_whose_number_is_not_stored_in_e164(self):
        """The production condition, which an exact match on phone_sanitized misses.

        `phone_sanitized` is a stored compute, so a row keeps whatever it
        evaluated to when it was last written. Measured on odoo.ledoweb.com,
        most partners hold the raw national string ("208-405-6061") and
        searching that same number in E.164 finds nothing -- on either
        `phone_sanitized` or `phone_mobile_search`. Only the national digits do.

        This test reproduces that shape, so the fallback cannot be refactored
        away without a failure. Without it, every inbound text from such a
        partner is filed `unmatched`, which is silent and is exactly the defect
        this module exists to prevent.
        """
        local = self.env["res.partner"].create(
            {"name": "Stored Nationally", "phone": "208-405-6061"}
        )
        # Simulate a stale stored compute from an imported database.
        self.env.cr.execute(
            "UPDATE res_partner SET phone_sanitized = %s WHERE id = %s",
            ["208-405-6061", local.id],
        )
        local.invalidate_recordset(["phone_sanitized"])
        self._post_webhook(
            self._inbound(sender="+12084056061", event_id="evt-national-1")
        )
        record = self.env["sms.telnyx.inbound"].search(
            [("telnyx_event_id", "=", "evt-national-1")]
        )
        self.assertEqual(record.state, "posted")
        self.assertEqual(record.partner_id, local)

    @mute_logger(INBOUND_LOGGER)
    def test_unknown_sender_is_kept_not_dropped(self):
        self._post_webhook(self._inbound(sender=STRANGER_NUMBER))
        record = self.env["sms.telnyx.inbound"].search(
            [("telnyx_event_id", "=", "evt-0001")]
        )
        self.assertEqual(record.state, "unmatched")
        self.assertFalse(record.partner_id)
        self.assertTrue(record.body, "the message text must survive even with no match")

    def test_stop_blacklists_the_number(self):
        self._post_webhook(self._inbound(text="STOP"))
        record = self.env["sms.telnyx.inbound"].search(
            [("telnyx_event_id", "=", "evt-0001")]
        )
        self.assertEqual(record.state, "opt_out")
        self.tenant.invalidate_recordset(["phone_sanitized_blacklisted"])
        self.assertTrue(
            self.env["phone.blacklist"]
            .sudo()
            .search([("number", "=", self.tenant.phone)]),
            "STOP must suppress our own sending, not just Telnyx's auto-reply",
        )

    def test_start_removes_the_blacklist_entry(self):
        self.env["phone.blacklist"].sudo().add(self.tenant.phone)
        self._post_webhook(self._inbound(text="START", event_id="evt-0002"))
        record = self.env["sms.telnyx.inbound"].search(
            [("telnyx_event_id", "=", "evt-0002")]
        )
        self.assertEqual(record.state, "opt_in")
        entry = (
            self.env["phone.blacklist"]
            .sudo()
            .search([("number", "=", self.tenant.phone)])
        )
        self.assertFalse(entry.active if entry else False)

    # ------------------------------------------------------------------
    # Delivery receipts
    # ------------------------------------------------------------------

    def test_delivery_receipt_updates_the_tracker(self):
        self.tenant._message_sms(body="Arrival window 2-4pm")
        sms = self.env["sms.sms"].sudo().search([("partner_id", "=", self.tenant.id)])
        sms.send(unlink_sent=False)
        tracker = sms.sms_tracker_id
        self.assertEqual(tracker.sms_telnyx_id, self.telnyx_message_id)

        event = {
            "data": {
                "event_type": "message.finalized",
                "id": "evt-dlr-1",
                "payload": {
                    "id": self.telnyx_message_id,
                    "to": [{"phone_number": self.tenant.phone, "status": "delivered"}],
                },
            }
        }
        response = self._post_webhook(event)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(sms.state, "sent")

    @mute_logger(WEBHOOK_LOGGER)
    def test_delivery_receipt_for_unknown_message_is_ignored(self):
        event = {
            "data": {
                "event_type": "message.finalized",
                "id": "evt-dlr-2",
                "payload": {
                    "id": "not-a-message-we-sent",
                    "to": [{"phone_number": STRANGER_NUMBER, "status": "delivered"}],
                },
            }
        }
        self.assertEqual(self._post_webhook(event).status_code, 200)

    def test_delivery_receipt_cannot_update_other_company_tracker(self):
        other = self.env["res.company"].create({"name": "Other company"})
        tracker = self.env["sms.tracker"].create(
            {
                "sms_uuid": "other-company-sms",
                "sms_telnyx_id": self.telnyx_message_id,
                "sms_telnyx_company_id": other.id,
            }
        )
        event = {
            "data": {
                "event_type": "message.finalized",
                "payload": {
                    "id": self.telnyx_message_id,
                    "to": [{"phone_number": STRANGER_NUMBER, "status": "delivered"}],
                },
            }
        }
        from unittest.mock import patch

        with patch.object(type(tracker), "_action_update_from_sms_state") as update:
            self.assertEqual(self._post_webhook(event).status_code, 200)
            update.assert_not_called()

    @mute_logger(WEBHOOK_LOGGER)
    def test_signed_non_object_json_is_rejected(self):
        response = self._post_webhook(["not an event"])
        self.assertEqual(response.status_code, 404)
