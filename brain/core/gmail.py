"""
Gmail integration — uses same OAuth token as Google Calendar.
Requires google_gmail_enabled = true in config.
Run `brain setup --google` to enable.
"""
import base64
import email as email_lib
from datetime import datetime, timezone
from brain import config


def is_enabled() -> bool:
    return bool(config.get("google_gmail_enabled", False))


def _get_service():
    """Build Gmail v1 service using the shared Google OAuth token."""
    from brain.core.google_cal import _get_service as _cal_get_creds
    from googleapiclient.discovery import build

    # Reuse the same credential flow from google_cal (same token file)
    from pathlib import Path
    from brain.core.google_cal import SCOPES
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    creds_path = Path(config.get("google_credentials_path", ""))
    token_path = Path(config.get("google_token_path", ""))

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def _parse_headers(headers: list) -> dict:
    return {h["name"].lower(): h["value"] for h in headers}


def _extract_body(payload: dict) -> str:
    """Extract plain text body from a Gmail message payload."""
    body = ""
    mime_type = payload.get("mimeType", "")

    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            body = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    elif mime_type in ("multipart/alternative", "multipart/mixed", "multipart/related"):
        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    body = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
                    break
        if not body:
            for part in payload.get("parts", []):
                body = _extract_body(part)
                if body:
                    break

    return body.strip()


def _format_date(internal_date_ms: str) -> str:
    """Convert Gmail internalDate (ms since epoch) to readable string."""
    try:
        ts = int(internal_date_ms) / 1000
        dt = datetime.fromtimestamp(ts)
        now = datetime.now()
        diff = (now - dt).days
        if diff == 0:
            return dt.strftime("today %H:%M")
        elif diff == 1:
            return "yesterday"
        elif diff < 7:
            return dt.strftime("%A")
        else:
            return dt.strftime("%b %-d")
    except Exception:
        return ""


def get_unread(limit: int = 10) -> list[dict]:
    """Return unread inbox emails, newest first."""
    try:
        service = _get_service()
        result = service.users().messages().list(
            userId="me",
            q="is:unread in:inbox",
            maxResults=limit,
        ).execute()

        messages = []
        for msg in result.get("messages", []):
            try:
                meta = service.users().messages().get(
                    userId="me", id=msg["id"],
                    format="metadata",
                    metadataHeaders=["Subject", "From", "Date"],
                ).execute()
                headers = _parse_headers(meta.get("payload", {}).get("headers", []))
                messages.append({
                    "id": msg["id"],
                    "subject": headers.get("subject", "(no subject)"),
                    "from": headers.get("from", ""),
                    "date": _format_date(meta.get("internalDate", "0")),
                    "snippet": meta.get("snippet", "")[:100],
                })
            except Exception:
                continue
        return messages
    except Exception:
        return []


def search_emails(query: str, limit: int = 10) -> list[dict]:
    """Search emails using Gmail search syntax."""
    try:
        service = _get_service()
        result = service.users().messages().list(
            userId="me", q=query, maxResults=limit,
        ).execute()

        messages = []
        for msg in result.get("messages", []):
            try:
                meta = service.users().messages().get(
                    userId="me", id=msg["id"],
                    format="metadata",
                    metadataHeaders=["Subject", "From", "Date"],
                ).execute()
                headers = _parse_headers(meta.get("payload", {}).get("headers", []))
                messages.append({
                    "id": msg["id"],
                    "subject": headers.get("subject", "(no subject)"),
                    "from": headers.get("from", ""),
                    "date": _format_date(meta.get("internalDate", "0")),
                    "snippet": meta.get("snippet", "")[:100],
                })
            except Exception:
                continue
        return messages
    except Exception:
        return []


def get_email(msg_id: str) -> dict:
    """Get full email content — subject, from, date, plain-text body."""
    try:
        service = _get_service()
        msg = service.users().messages().get(
            userId="me", id=msg_id, format="full",
        ).execute()
        headers = _parse_headers(msg.get("payload", {}).get("headers", []))
        body = _extract_body(msg.get("payload", {}))
        return {
            "id": msg_id,
            "subject": headers.get("subject", "(no subject)"),
            "from": headers.get("from", ""),
            "date": _format_date(msg.get("internalDate", "0")),
            "body": body[:3000],
        }
    except Exception as e:
        return {"error": str(e)}


def mark_read(msg_id: str) -> None:
    """Remove UNREAD label from a message."""
    try:
        service = _get_service()
        service.users().messages().modify(
            userId="me", id=msg_id,
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()
    except Exception:
        pass


def get_unread_count() -> int:
    """Fast unread count for daily brief."""
    try:
        service = _get_service()
        result = service.users().messages().list(
            userId="me", q="is:unread in:inbox", maxResults=1,
        ).execute()
        return result.get("resultSizeEstimate", 0)
    except Exception:
        return 0


def get_my_email() -> str:
    """Return the authenticated user's email address."""
    service = _get_service()
    profile = service.users().getProfile(userId="me").execute()
    return profile.get("emailAddress", "")


def send_email(to: str, subject: str, html: str, text: str = "") -> dict:
    """Send an email via Gmail API. Returns {id, threadId}."""
    import base64
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    service = _get_service()
    msg = MIMEMultipart("alternative")
    msg["to"] = to
    msg["subject"] = subject
    msg.attach(MIMEText(text or "See HTML version.", "plain"))
    msg.attach(MIMEText(html, "html"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    result = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return {"id": result["id"], "threadId": result.get("threadId", "")}
