1. Go to **Settings → Phone Validation → SMS Providers**.
2. Create a new gateway with type **Twilio**.
3. Fill in your **Account SID**, **Auth Token**, and **From Number**
   (the Twilio phone number in E.164 format, e.g. ``+14122846600``).
4. If you have multiple gateways, use the **sequence** handle to set
   priority — the first matching gateway is used.
