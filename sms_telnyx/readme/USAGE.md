Sending is unchanged from stock Odoo: use the SMS composer from any chatter, an
SMS template, or a mass mailing. Which provider carries the message is decided
per company, so one database can have one entity on Telnyx and another on Twilio.

Inbound messages appear as an `sms` message on the matched record's chatter,
authored by the contact, which notifies that record's followers.

Every inbound message is also recorded in **Settings → Technical → Inbound
Telnyx Messages** (`sms.telnyx.inbound`) with the routing decision:

| State | Meaning |
| --- | --- |
| `posted` | Matched a partner and was filed on a record |
| `unmatched` | No partner has this number — the text is kept, not discarded |
| `opt_out` / `opt_in` | A `STOP` / `START` keyword, applied to `phone.blacklist` |
| `pending` | Recorded but not yet processed |

`unmatched` is worth a periodic look: it is usually a contact whose number was
never captured, and it is the one case where a real message reaches nobody.
