"""
Gmail integration — read inbox, search threads, send email.

Reading: uses Gmail API (requires OAuth) or IMAP fallback (GMAIL_APP_PASSWORD).
Sending: uses existing SMTP from gmail_report.py (GMAIL_USER + GMAIL_APP_PASSWORD).
"""

import os
import imaplib
import email
from email.header import decode_header
from datetime import datetime
from typing import Optional

GMAIL_USER = lambda: os.getenv("GMAIL_USER", "")
GMAIL_PASS = lambda: os.getenv("GMAIL_APP_PASSWORD", "")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


# ─── IMAP helpers (no OAuth needed) ─────────────────────────────────────────

def _imap_connect() -> Optional[imaplib.IMAP4_SSL]:
    user = GMAIL_USER()
    pwd = GMAIL_PASS()
    if not user or not pwd:
        return None
    try:
        conn = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        conn.login(user, pwd)
        return conn
    except Exception as e:
        print(f"[GMAIL] IMAP connect error: {e}")
        return None


def _decode_header_str(value: str) -> str:
    parts = decode_header(value or "")
    out = []
    for part, enc in parts:
        if isinstance(part, bytes):
            try:
                out.append(part.decode(enc or "utf-8", errors="replace"))
            except Exception:
                out.append(part.decode("utf-8", errors="replace"))
        else:
            out.append(str(part))
    return "".join(out)


def _parse_email(raw: bytes) -> dict:
    msg = email.message_from_bytes(raw)
    subject = _decode_header_str(msg.get("Subject", ""))
    sender = _decode_header_str(msg.get("From", ""))
    date_str = msg.get("Date", "")
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain" and not part.get("Content-Disposition"):
                try:
                    body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                    break
                except Exception:
                    pass
    else:
        try:
            body = msg.get_payload(decode=True).decode("utf-8", errors="replace")
        except Exception:
            pass
    return {
        "subject": subject,
        "from": sender,
        "date": date_str,
        "body": body[:500],
        "body_preview": body[:200].strip(),
    }


def get_inbox(limit: int = 10, folder: str = "INBOX") -> list[dict]:
    """
    Fetch recent emails via IMAP. Returns list of dicts with subject, from, date, body_preview.
    Falls back to [] if no credentials.
    """
    conn = _imap_connect()
    if not conn:
        return []
    try:
        conn.select(folder)
        _, data = conn.search(None, "ALL")
        ids = data[0].split()
        ids = ids[-limit:][::-1]
        emails = []
        for uid in ids:
            try:
                _, raw = conn.fetch(uid, "(RFC822)")
                if raw and raw[0] and isinstance(raw[0], tuple):
                    parsed = _parse_email(raw[0][1])
                    parsed["uid"] = uid.decode()
                    emails.append(parsed)
            except Exception:
                pass
        return emails
    except Exception as e:
        print(f"[GMAIL] inbox error: {e}")
        return []
    finally:
        try:
            conn.close()
            conn.logout()
        except Exception:
            pass


def search_emails(query: str, limit: int = 5) -> list[dict]:
    """Search emails by keyword using IMAP SEARCH."""
    conn = _imap_connect()
    if not conn:
        return []
    try:
        conn.select("INBOX")
        _, data = conn.search(None, f'TEXT "{query}"')
        ids = data[0].split()[-limit:][::-1]
        emails = []
        for uid in ids:
            try:
                _, raw = conn.fetch(uid, "(RFC822)")
                if raw and raw[0] and isinstance(raw[0], tuple):
                    parsed = _parse_email(raw[0][1])
                    parsed["uid"] = uid.decode()
                    emails.append(parsed)
            except Exception:
                pass
        return emails
    except Exception as e:
        print(f"[GMAIL] search error: {e}")
        return []
    finally:
        try:
            conn.close()
            conn.logout()
        except Exception:
            pass


async def send_email(to: str, subject: str, body: str, html: bool = False) -> bool:
    """Send email via Gmail SMTP. Returns True on success."""
    user = GMAIL_USER()
    pwd = GMAIL_PASS()
    if not user or not pwd:
        return False
    try:
        import aiosmtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = user
        msg["To"] = to
        content_type = "html" if html else "plain"
        msg.attach(MIMEText(body, content_type))
        await aiosmtplib.send(
            msg,
            hostname="smtp.gmail.com",
            port=465,
            use_tls=True,
            username=user,
            password=pwd,
        )
        return True
    except Exception as e:
        print(f"[GMAIL] send error: {e}")
        return False


def get_unread_count() -> int:
    """Quick unread count via IMAP."""
    conn = _imap_connect()
    if not conn:
        return -1
    try:
        conn.select("INBOX")
        _, data = conn.search(None, "UNSEEN")
        return len(data[0].split()) if data[0] else 0
    except Exception:
        return -1
    finally:
        try:
            conn.close()
            conn.logout()
        except Exception:
            pass


def gmail_available() -> bool:
    return bool(GMAIL_USER() and GMAIL_PASS())
