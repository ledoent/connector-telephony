## Basic setup

1. Go to **Settings → Phone Validation → SMS Providers**.
2. Create a new gateway with type **Twilio**.
3. Fill in your **Account SID** (starts with ``AC``).
4. Choose an authentication method:

   - **Auth Token** — paste the token from the Twilio Console.
   - **API Key** (recommended) — create an API Key in the Twilio Console,
     then fill in the **API Key SID** (``SK…``) and **API Key Secret**.
     Leave *Auth Token* blank.

## A2P 10DLC compliance (US destinations)

Since December 2024 US carriers block all SMS from unregistered 10DLC
numbers.  To send to US numbers you **must**:

1. Register a **Brand** in the Twilio Console (A2P → Brand Registrations).
2. Create a **Campaign** (A2P → Campaign Registrations) linked to a
   **Messaging Service**.
3. Add your Twilio phone number(s) to the Messaging Service's Sender Pool.
4. Wait for the campaign status to become **VERIFIED** (typically 1–15
   business days).
5. In this gateway form, paste the **Messaging Service SID** (``MG…``).

When a Messaging Service SID is configured, messages use
``MessagingServiceSid`` instead of ``From`` so that Twilio routes them
through the registered campaign.

If the Messaging Service SID is left blank, the module falls back to the
**From Number** field — suitable for non-US destinations or testing with
Twilio Magic Numbers.

## Delivery tracking (optional)

Fill in **Status Callback URL** with a publicly reachable endpoint.
Twilio will ``POST`` delivery status updates (``queued``, ``sent``,
``delivered``, ``undelivered``, ``failed``) to this URL.  This is
useful for monitoring delivery rates and diagnosing failures.

## Error code reference

The module maps Twilio error codes to Odoo SMS states:

| Twilio code | Meaning | Odoo state |
|-------------|---------|------------|
| 21211 / 21614 | Invalid number | ``wrong_number_format`` |
| 30003 / 30005 / 30006 | Unreachable / landline | ``wrong_number_format`` |
| 21610 | Recipient opted out (STOP) | ``unregistered`` |
| 30004 / 30007 | Carrier filter / spam block | ``server_error`` |
| 30034 | Unregistered A2P 10DLC number | ``server_error`` |
