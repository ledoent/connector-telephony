This module adds Twilio as an SMS gateway provider for the
``sms_alternative_provider`` framework.

It uses the Twilio REST API directly via Python's standard library
(no external ``twilio`` pip package required).

**Features:**

- A2P 10DLC compliant — sends via Messaging Service SID so messages
  are routed through your registered campaign (required for US delivery
  since December 2024).
- Falls back to a direct ``From`` number when no Messaging Service is
  configured (useful for non-US destinations or testing).
- Supports both Account Auth Token and API Key (SK…) authentication.
  API Keys are recommended for production because they can be revoked
  individually without rotating the master Auth Token.
- Optional delivery status callback URL for tracking delivery
  confirmations and failures via Twilio webhooks.
- Comprehensive Twilio error-code mapping (21211, 21610, 30003–30034,
  etc.) to Odoo SMS states so that invalid numbers, opt-outs, and
  carrier blocks are reported correctly.
