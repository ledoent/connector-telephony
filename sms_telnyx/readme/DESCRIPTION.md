Send and receive SMS through [Telnyx](https://telnyx.com).

Odoo 19 and 20 ship `sms_twilio`, which makes the SMS provider a per-company
choice but offers only Odoo IAP and Twilio. This module adds Telnyx as a third
option and, unlike either of the built-ins, also handles **inbound** messages:

* **Outbound** — `sms.sms` for a company set to Telnyx is sent through
  `POST /v2/messages`, with delivery receipts reconciled back onto the
  `sms.tracker`.
* **Inbound** — one webhook endpoint receives `message.received` events,
  verifies Telnyx's Ed25519 signature, matches the sender to a partner and posts
  the text on that record's chatter, so a reply reaches the system of record
  instead of someone's handset.
* **Consent** — carrier-mandated `STOP` / `START` keywords add to and remove
  from `phone.blacklist`, which core SMS sending already honours. Telnyx answers
  the sender on our behalf; suppressing our own sending is the part that is
  legally ours, and this is it.

Inbound routing is designed to be extended: `sms.telnyx.inbound._route_target()`
returns the record to post on, defaulting to the matched partner. A deployment
with a helpdesk, a lease or a reservation model should override it.
