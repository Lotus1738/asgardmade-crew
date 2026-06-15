"""
Twilio SMS integration for AsgardMade Pantheon.

Sends the ODIN morning briefing as a condensed SMS via Twilio's
Programmable Messaging API.

Required environment variables:
  TWILIO_ACCOUNT_SID   — Twilio Account SID (starts with "AC")
  TWILIO_AUTH_TOKEN    — Twilio Auth Token
  TWILIO_FROM_NUMBER   — Your Twilio phone number (E.164 format, e.g. +15551234567)
  TWILIO_TO_NUMBER     — Destination phone number (E.164 format, e.g. +15559876543)

If any of these are missing, send_sms() returns silently without error.

API reference: https://www.twilio.com/docs/messaging/api/message-resource
Endpoint: POST https://api.twilio.com/2010-04-01/Accounts/{SID}/Messages.json
Auth: HTTP Basic — username=ACCOUNT_SID, password=AUTH_TOKEN
"""
from __future__ import annotations


import os
import httpx

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"
SMS_MAX_CHARS = 160


def _has_credentials() -> bool:
    return all([
        os.getenv("TWILIO_ACCOUNT_SID"),
        os.getenv("TWILIO_AUTH_TOKEN"),
        os.getenv("TWILIO_FROM_NUMBER"),
        os.getenv("TWILIO_TO_NUMBER"),
    ])


def build_briefing_sms(
    sales_yesterday: int = 0,
    revenue: float = 0.0,
    pending_approvals: int = 0,
    top_niche: str = "—",
) -> str:
    """
    Build a condensed SMS briefing under 160 characters.
    Format: "AsgardMade Daily: {N} sales, ${R} revenue. {P} pending approvals. Top niche: {T}"
    """
    msg = (
        f"AsgardMade Daily: {sales_yesterday} sales, "
        f"${revenue:.0f} revenue. "
        f"{pending_approvals} pending approvals. "
        f"Top niche: {top_niche}"
    )
    return msg[:SMS_MAX_CHARS]


async def send_sms(message: str) -> dict | None:
    """
    Send an SMS via Twilio. Returns the API response dict on success.
    Returns None silently if credentials are missing or on any error.

    Args:
        message: The SMS body text (will be truncated to 160 chars)
    """
    if not _has_credentials():
        return None

    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_FROM_NUMBER")
    to_number = os.getenv("TWILIO_TO_NUMBER")

    url = f"{TWILIO_API_BASE}/Accounts/{account_sid}/Messages.json"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                auth=(account_sid, auth_token),
                data={
                    "From": from_number,
                    "To": to_number,
                    "Body": message[:SMS_MAX_CHARS],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "sid": data.get("sid"),
                "status": data.get("status"),
                "to": to_number,
                "body": message[:SMS_MAX_CHARS],
            }
    except Exception as e:
        # Silently fail — SMS is non-critical
        print(f"[TWILIO SMS] Failed to send: {type(e).__name__}: {e}")
        return None
