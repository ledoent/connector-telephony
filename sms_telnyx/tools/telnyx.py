# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import logging
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from odoo.addons.phone_validation.tools import phone_validation

_logger = logging.getLogger(__name__)

TELNYX_MESSAGES_URL = "https://api.telnyx.com/v2/messages"

# Telnyx rejects a webhook that does not answer 2xx within 2 seconds (API v2)
# and then retries it, so a wide timestamp tolerance buys no liveness at all --
# it only widens the replay window. Five minutes is the usual compromise and
# survives modest clock skew between Telnyx and this host.
SIGNATURE_TOLERANCE_SECONDS = 300

# Carrier-mandated keywords. Telnyx, like every US aggregator, answers STOP on
# our behalf, but it does not stop *us* sending: suppression is the sender's
# obligation, which is why these land on phone.blacklist.
OPT_OUT_KEYWORDS = frozenset(
    {"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"}
)
# Deliberately NOT including "YES": it is not a carrier-mandated opt-in keyword,
# and treating it as one would swallow a tenant answering an actual question
# instead of filing the reply on their record.
OPT_IN_KEYWORDS = frozenset({"START", "UNSTOP"})


def verify_webhook_signature(
    public_key,
    signature,
    timestamp,
    raw_body,
    tolerance=SIGNATURE_TOLERANCE_SECONDS,
):
    """Verify a Telnyx webhook's Ed25519 signature.

    Telnyx signs ``{telnyx-timestamp}|{raw body}`` with an account key pair and
    sends the detached signature base64-encoded in the
    ``telnyx-signature-ed25519`` header, with the timestamp in
    ``telnyx-timestamp``.

    ``raw_body`` must be the bytes as received. Re-serialising parsed JSON does
    not round-trip byte-for-byte, so a signature checked against
    ``json.dumps(parsed)`` fails for payloads that are in fact authentic -- a
    failure that looks exactly like an attack and is not one. This is the single
    most common way this check is got wrong.

    Returns True only on a verified signature; every failure path returns False
    rather than raising, so the caller can answer with one uniform rejection and
    reveal nothing about which check failed.
    """
    if not (public_key and signature and timestamp):
        return False
    try:
        skew = abs(time.time() - int(timestamp))
    except (TypeError, ValueError):
        return False
    if tolerance and skew > tolerance:
        _logger.warning(
            "Telnyx webhook: timestamp outside tolerance (skew %ss)", int(skew)
        )
        return False
    if isinstance(raw_body, str):
        raw_body = raw_body.encode()
    signed_payload = str(timestamp).encode() + b"|" + raw_body
    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key))
        key.verify(base64.b64decode(signature), signed_payload)
    except (InvalidSignature, ValueError, TypeError):
        return False
    return True


def get_from_number(company, to_number):
    """Pick the Telnyx number to send from, preferring the destination's country.

    Mirrors ``sms_twilio.tools.sms_twilio.get_twilio_from_number`` so that a
    company switching providers keeps the same selection behaviour.
    """
    country_code = phone_validation.phone_get_country_code_for_number(to_number)
    numbers = company.sms_telnyx_number_ids
    if not numbers or not country_code:
        return numbers[:1]
    return numbers.sorted(lambda rec: rec.country_code == country_code, reverse=True)[0]
