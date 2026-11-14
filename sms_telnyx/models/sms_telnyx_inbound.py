# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from psycopg2 import IntegrityError, errorcodes

from odoo import api, fields, models

from odoo.addons.phone_validation.tools import phone_validation

from ..tools.telnyx import OPT_IN_KEYWORDS, OPT_OUT_KEYWORDS

_logger = logging.getLogger(__name__)


class SmsTelnyxInbound(models.Model):
    """Durable ledger of every inbound Telnyx message, and the routing decision.

    Why a model rather than posting straight to chatter from the controller:

    * Core deletes `sms.sms` once sent, so there is no existing table that holds
      a message we *received*. Without this, an inbound text that fails to match
      a partner would be lost silently -- the exact defect this feature exists
      to fix.
    * Telnyx retries a webhook that does not answer 2xx within 2 seconds, and
      may deliver the same event more than once regardless. `telnyx_event_id`
      carries a unique constraint so a replay is a no-op instead of a duplicate
      chatter message.
    * `_route_target()` lets downstream modules choose another chatter record.
    """

    _name = "sms.telnyx.inbound"
    _description = "Inbound Telnyx Message"
    _order = "id desc"

    telnyx_event_id = fields.Char(required=True, index="btree", readonly=True)
    telnyx_message_id = fields.Char(index="btree_not_null", readonly=True)
    company_id = fields.Many2one(
        "res.company", required=True, readonly=True, index="btree"
    )
    from_number = fields.Char(required=True, readonly=True)
    to_number = fields.Char(readonly=True)
    body = fields.Text(readonly=True)
    occurred_at = fields.Datetime(readonly=True)
    partner_id = fields.Many2one("res.partner", readonly=True, index="btree_not_null")
    res_model = fields.Char("Routed Model", readonly=True)
    res_id = fields.Integer("Routed Record", readonly=True)
    message_id = fields.Many2one("mail.message", readonly=True, ondelete="set null")
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("posted", "Posted"),
            ("opt_out", "Opt-out"),
            ("opt_in", "Opt-in"),
            ("unmatched", "Unknown sender"),
        ],
        default="pending",
        required=True,
        index="btree",
        readonly=True,
    )

    _telnyx_event_unique = models.Constraint(
        "unique(telnyx_event_id)",
        "This Telnyx event has already been recorded.",
    )

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    @api.model
    def _record_event(self, event, companies):
        """Create the ledger row for one `message.received` event and route it.

        `event` is the already-parsed `data` object of a verified webhook. The
        caller is responsible for signature verification: this method trusts its
        input, which is why it is not exposed to RPC by any access rule.

        Returns the record, or an empty recordset when the event is a duplicate.
        """
        payload = event.get("payload") or {}
        event_id = event.get("id")
        if not event_id:
            _logger.warning("Telnyx inbound: event without an id, ignored")
            return self.browse()
        existing = self.sudo().search([("telnyx_event_id", "=", event_id)], limit=1)
        if existing:
            # A retry, not a new message. Answer 2xx and change nothing.
            return self.browse()

        from_number = (payload.get("from") or {}).get("phone_number")
        # `to` is a LIST of objects on the inbound webhook, even though it is a
        # plain string when sending. Taking [0] is correct for SMS; MMS group
        # messages would need more, and are out of scope.
        to_entries = payload.get("to") or []
        to_number = to_entries[0].get("phone_number") if to_entries else None
        if not from_number:
            _logger.warning("Telnyx inbound: event %s has no sender, ignored", event_id)
            return self.browse()

        company = self._company_from_number(to_number, companies)
        if not company or (
            company.sms_telnyx_messaging_profile_id
            and payload.get("messaging_profile_id")
            != company.sms_telnyx_messaging_profile_id
        ):
            _logger.warning(
                "Telnyx inbound: recipient or messaging profile is not configured"
            )
            return self.browse()
        try:
            with self.env.cr.savepoint():
                record = (
                    self.sudo()
                    .with_company(company)
                    .create(
                        {
                            "telnyx_event_id": event_id,
                            "telnyx_message_id": payload.get("id"),
                            "company_id": company.id,
                            "from_number": from_number,
                            "to_number": to_number,
                            "body": payload.get("text") or "",
                            "occurred_at": fields.Datetime.now(),
                        }
                    )
                )
        except IntegrityError as error:
            if error.pgcode != errorcodes.UNIQUE_VIOLATION:
                raise
            return self.browse()
        record._process()
        return record

    @api.model
    def _company_from_number(self, to_number, companies):
        """Which company owns the DID the message arrived on.

        This is the reliable multi-company key for inbound traffic: the sender
        tells us nothing about which entity they were contacting. Only a company
        whose key verified the request may receive it. Unknown DIDs are ignored.
        """
        if to_number:
            number = (
                self.env["sms.telnyx.number"]
                .sudo()
                .search(
                    [("number", "=", to_number), ("company_id", "in", companies.ids)],
                    limit=1,
                )
            )
            if number:
                return number.company_id
        _logger.warning(
            "Telnyx inbound: no verified company owns %s",
            to_number or "-",
        )
        return self.env["res.company"].browse()

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def _process(self):
        for record in self:
            keyword = (record.body or "").strip().upper()
            if keyword in OPT_OUT_KEYWORDS:
                record._handle_opt_out()
                continue
            if keyword in OPT_IN_KEYWORDS:
                record._handle_opt_in()
                continue
            record.partner_id = record._find_partner()
            if not record.partner_id:
                record.state = "unmatched"
                continue
            target = record._route_target()
            if not target:
                record.state = "unmatched"
                continue
            record.message_id = target.message_post(
                body=record.body or "",
                author_id=record.partner_id.id,
                message_type="sms",
                subtype_xmlid="mail.mt_comment",
            )
            record.write(
                {
                    "res_model": target._name,
                    "res_id": target.id,
                    "state": "posted",
                }
            )

    def _find_partner(self):
        """Match the sender to a partner, tolerantly.

        An exact match on `phone_sanitized` is the obvious implementation and it
        is not sufficient. `phone_sanitized` is a STORED compute, so a row keeps
        whatever it evaluated to when it was last written -- and measured against
        odoo.ledoweb.com, most partners hold the raw string ("208-405-6061")
        rather than E.164, even though both the partner and the company carry a
        US country. For such a row, searching `phone_sanitized = "+12084056061"`
        finds nothing, and so does `phone_mobile_search` with that same E.164
        value; only the national digits ("2084056061") find it.

        So try three representations, most precise first, stopping at the first
        hit. Getting this wrong does not raise -- it silently files every
        inbound message as `unmatched`, which is the failure this module exists
        to prevent.

        Note that in Odoo 20 `res.partner` has no `mobile` field at all, only
        `phone`, so there is one number per partner to match against.
        """
        self.ensure_one()
        partner_model = self.env["res.partner"].sudo()
        company_domain = [("company_id", "in", [False, self.company_id.id])]
        domains = [
            [("phone_sanitized", "=", self.from_number)],
            [("phone_mobile_search", "=", self.from_number)],
        ]
        national = phone_validation.phone_get_region_data_for_number(self.from_number)[
            "national_number"
        ]
        if national:
            domains.append([("phone_mobile_search", "=", national)])

        partners = partner_model.browse()
        for domain in domains:
            partners = partner_model.search(company_domain + domain, order="id")
            if partners:
                break

        if len(partners) > 1:
            _logger.warning(
                "Telnyx inbound: %s matches %s partners; leaving unmatched",
                self.from_number,
                len(partners),
            )
            return partner_model.browse()
        return partners[:1]

    def _route_target(self):
        """Return the mail.thread record this message belongs on.

        Override point. The default is the partner's own chatter, which is
        always available and needs no extra modules. A deployment with a
        helpdesk, a lease or a reservation should prefer that instead.
        """
        self.ensure_one()
        return self.partner_id

    # ------------------------------------------------------------------
    # Consent
    # ------------------------------------------------------------------

    def _sanitized_number(self):
        """E.164 form of the sender, or False if it cannot be formatted.

        Needed because `phone.blacklist.add()` feeds
        `env.user._phone_format(number=...)` straight into
        `create({"number": ...})`. A number it cannot format becomes a NULL
        insert and a not-null violation -- and inside a webhook that is a 500,
        which makes Telnyx retry the same message indefinitely. Sanitize here
        and skip instead of crashing.
        """
        self.ensure_one()
        return self.env.user.with_company(self.company_id)._phone_format(
            number=self.from_number
        )

    def _handle_opt_out(self):
        self.ensure_one()
        sanitized = self._sanitized_number()
        if sanitized:
            self.env["phone.blacklist"].sudo()._add(
                [sanitized], message=self.env._("Opted out by SMS (Telnyx)")
            )
        else:
            # Record the intent even though suppression could not be applied:
            # losing an opt-out silently is a compliance problem, not a bug to
            # swallow.
            _logger.warning(
                "Telnyx inbound: cannot format %s, opt-out NOT blacklisted",
                self.from_number,
            )
        self.partner_id = self._find_partner()
        self.state = "opt_out"

    def _handle_opt_in(self):
        self.ensure_one()
        sanitized = self._sanitized_number()
        if sanitized:
            self.env["phone.blacklist"].sudo()._remove(
                [sanitized], message=self.env._("Opted back in by SMS (Telnyx)")
            )
        else:
            _logger.warning(
                "Telnyx inbound: cannot format %s, opt-in NOT un-blacklisted",
                self.from_number,
            )
        self.partner_id = self._find_partner()
        self.state = "opt_in"
