"""
Emergency SMS escalation.

Sends an SOS text to a user's emergency contacts through Twilio when the
following environment variables are configured:

    TWILIO_ACCOUNT_SID
    TWILIO_AUTH_TOKEN
    TWILIO_FROM_NUMBER   (E.164, e.g. +12025550123)

If Twilio is not configured, the escalation is skipped and logged; in-app
notifications to circle members still work.
"""

import base64
import logging
import os
import urllib.parse
import urllib.request
from typing import Iterable

logger = logging.getLogger("rtf.sos")


def sms_configured() -> bool:
    return all(
        os.getenv(name, "").strip()
        for name in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER")
    )


def _maps_link(latitude: float, longitude: float) -> str:
    return f"https://www.openstreetmap.org/?mlat={latitude}&mlon={longitude}#map=17/{latitude}/{longitude}"


def build_sos_message(user_name: str, latitude: float, longitude: float) -> str:
    return (
        f"EMERGENCY SOS from {user_name}. "
        f"Live location: {_maps_link(latitude, longitude)} "
        f"Please contact them or emergency services immediately."
    )


def send_sms(to_number: str, body: str) -> bool:
    if not sms_configured():
        return False

    sid = os.environ["TWILIO_ACCOUNT_SID"].strip()
    token = os.environ["TWILIO_AUTH_TOKEN"].strip()
    sender = os.environ["TWILIO_FROM_NUMBER"].strip()

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    payload = urllib.parse.urlencode({"From": sender, "To": to_number, "Body": body}).encode()
    credentials = base64.b64encode(f"{sid}:{token}".encode()).decode()
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read(64)
        return True
    except Exception as exc:  # network, auth, invalid number, quota...
        logger.warning("SOS SMS to %s failed: %s", to_number, exc)
        return False


def escalate_sos_to_phones(
    phones: Iterable[str],
    user_name: str,
    latitude: float,
    longitude: float,
) -> int:
    """Send the SOS text to every phone number. Returns the number sent."""
    if not sms_configured():
        logger.info("SOS SMS skipped: Twilio is not configured (set TWILIO_* env vars).")
        return 0

    body = build_sos_message(user_name, latitude, longitude)
    sent = 0
    for phone in phones:
        phone = (phone or "").strip()
        if not phone:
            continue
        if send_sms(phone, body):
            sent += 1
    return sent
