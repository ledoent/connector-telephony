## In Telnyx

1. Create a **Messaging Profile** and buy at least one phone number, then assign
   the number to that profile. Sending from a number that is not on a profile
   fails with Telnyx error `40300`.
2. For US traffic, complete **A2P 10DLC** brand and campaign registration.
   Unregistered messages to US numbers are blocked by the carriers, not by
   Telnyx, so this cannot be worked around and takes weeks — start it first.
3. Set the profile's **webhook URL** to `https://<your-odoo>/sms_telnyx/webhook`
   and the **webhook API version to v2**. v1 does not send an Ed25519 signature,
   so every delivery would be rejected.
4. Copy the **API key** (Account → Keys & Credentials) and the account's
   **public key** from the same page.

## In Odoo

Settings → General Settings → SMS:

1. Set **SMS Provider** to *Send via Telnyx*.
2. Click **Configure Telnyx Account** to open the account modal. Enter the API
   key, public key and messaging profile id, then add each DID with its country. The
   country matters twice: it selects the sending number for a given destination,
   and the number is how an inbound message is attributed to a company.

The public key is what makes the webhook trustworthy, so the endpoint rejects
everything while it is unset — including genuine Telnyx deliveries. That is
deliberate: an unauthenticated public route that accepted anything would let a
stranger file messages against your customers.

Use **Send test SMS** with a test recipient to check the selected Telnyx account.
The test uses Telnyx even before the provider choice in Settings is saved.
**Update Account** closes the modal; save Settings to apply the provider choice.
The modal also shows the webhook URL to copy into the Telnyx messaging profile.
