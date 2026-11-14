-- Sanitised copies must never be able to talk to the real Telnyx account, nor
-- accept a webhook signed by it. Mirrors sms_twilio/data/neutralize.sql.
UPDATE res_company
   SET sms_telnyx_api_key = 'dummykey',
       sms_telnyx_public_key = NULL;
