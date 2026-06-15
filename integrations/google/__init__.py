"""
Google Suite integration layer for AsgardMade Pantheon.

Authentication modes (priority order):
  1. GOOGLE_SERVICE_ACCOUNT_JSON env var (base64-encoded JSON) — Drive, Sheets, Calendar
  2. GOOGLE_OAUTH_JSON env var (base64-encoded OAuth credentials) — all services
  3. Graceful no-op if neither is set (all functions return empty results)

Setup:
  1. Go to console.cloud.google.com
  2. Create a project, enable: Gmail API, Drive API, Calendar API, Sheets API
  3. Create a Service Account → download JSON → base64 encode it
  4. Set GOOGLE_SERVICE_ACCOUNT_JSON in Railway env vars
  5. For Gmail read access: also create OAuth credentials and set GOOGLE_OAUTH_JSON
"""

import os
import json
import base64
from typing import Optional

_service_account_info: Optional[dict] = None
_oauth_info: Optional[dict] = None


def _load_service_account() -> Optional[dict]:
    global _service_account_info
    if _service_account_info is not None:
        return _service_account_info
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        return None
    try:
        decoded = base64.b64decode(raw).decode("utf-8")
        _service_account_info = json.loads(decoded)
        return _service_account_info
    except Exception as e:
        print(f"[GOOGLE] Service account load error: {e}")
        return None


def _load_oauth() -> Optional[dict]:
    global _oauth_info
    if _oauth_info is not None:
        return _oauth_info
    raw = os.getenv("GOOGLE_OAUTH_JSON", "")
    if not raw:
        return None
    try:
        decoded = base64.b64decode(raw).decode("utf-8")
        _oauth_info = json.loads(decoded)
        return _oauth_info
    except Exception as e:
        print(f"[GOOGLE] OAuth load error: {e}")
        return None


def has_service_account() -> bool:
    return _load_service_account() is not None


def has_oauth() -> bool:
    return _load_oauth() is not None


def has_any_credentials() -> bool:
    return has_service_account() or has_oauth()


def get_service_account_credentials(scopes: list[str]):
    """Return google.oauth2.service_account.Credentials or None."""
    info = _load_service_account()
    if not info:
        return None
    try:
        from google.oauth2 import service_account
        return service_account.Credentials.from_service_account_info(info, scopes=scopes)
    except Exception as e:
        print(f"[GOOGLE] Credentials error: {e}")
        return None


def get_oauth_credentials(scopes: list[str]):
    """Return google.oauth2.credentials.Credentials from stored token."""
    info = _load_oauth()
    if not info:
        return None
    try:
        from google.oauth2.credentials import Credentials
        return Credentials(
            token=info.get("access_token"),
            refresh_token=info.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=info.get("client_id"),
            client_secret=info.get("client_secret"),
            scopes=scopes,
        )
    except Exception as e:
        print(f"[GOOGLE] OAuth credentials error: {e}")
        return None


def get_credentials(scopes: list[str]):
    """Try service account first, then OAuth."""
    creds = get_service_account_credentials(scopes)
    if creds:
        return creds
    return get_oauth_credentials(scopes)


def google_status() -> dict:
    """Return current credential status for the dashboard."""
    sa = _load_service_account()
    oauth = _load_oauth()
    return {
        "service_account": bool(sa),
        "oauth": bool(oauth),
        "any_credentials": bool(sa or oauth),
        "service_account_email": sa.get("client_email", "") if sa else "",
        "gmail_smtp": bool(os.getenv("GMAIL_USER") and os.getenv("GMAIL_APP_PASSWORD")),
    }
