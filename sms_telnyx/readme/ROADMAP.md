* MMS is not handled. Inbound `media` is ignored and nothing is attached to the
  chatter message.
* Group messages (several entries in the inbound `to` array) take the first
  recipient only.
* Delivery failures are recorded with the core `unknown` failure type plus
  Telnyx's own text in the failure reason, rather than a mapped per-code
  failure type. Mapping them would mean extending the `failure_type` selection
  on both `sms.sms` and `mail.notification`, which was judged not worth the
  collision risk for the information gained.
* Inbound processing is synchronous, because Telnyx expects a 2xx within two
  seconds and this module assumes no job queue. A deployment with `queue_job`
  installed would be better served deferring `_process()`.
* The webhook tries every configured public key in turn. That is fine for a few
  companies and would want a per-company endpoint path at a few dozen.
