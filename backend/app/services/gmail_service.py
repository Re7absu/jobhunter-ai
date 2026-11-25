"""Gmail API integration (official OAuth 2.0 flow). Tokens are stored encrypted."""

import base64
import json
import logging
import secrets
from email.message import EmailMessage
from email.utils import parseaddr

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import decrypt_str, encrypt_str
from app.models import User

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",  # reply detection on application threads
]


class GmailError(RuntimeError):
    pass


def _flow(state: str | None = None) -> Flow:
    if not settings.gmail_configured:
        raise GmailError("Gmail is not configured: set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET")
    cfg = {"web": {
        "client_id": settings.GOOGLE_CLIENT_ID, "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
    }}
    return Flow.from_client_config(cfg, scopes=SCOPES, state=state, redirect_uri=settings.GOOGLE_REDIRECT_URI)


def authorization_url(db: Session, user: User) -> str:
    flow = _flow()
    state = secrets.token_urlsafe(24)
    url, _ = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true", state=state)
    user.gmail_oauth_state = state
    user.gmail_code_verifier = getattr(flow, "code_verifier", None)
    db.commit()
    return url


def complete_authorization(db: Session, state: str, code: str) -> User:
    user = db.query(User).filter(User.gmail_oauth_state == state).first() if state else None
    if not user:
        raise GmailError("Invalid or expired OAuth state")
    flow = _flow(state=state)
    if user.gmail_code_verifier:
        flow.code_verifier = user.gmail_code_verifier
    flow.fetch_token(code=code)
    creds = flow.credentials
    user.gmail_token_encrypted = encrypt_str(creds.to_json())
    user.gmail_oauth_state = None
    user.gmail_code_verifier = None
    try:
        profile = build("gmail", "v1", credentials=creds, cache_discovery=False).users().getProfile(userId="me").execute()
        user.gmail_email = profile.get("emailAddress")
    except HttpError as e:
        log.warning("could not read Gmail profile: %s", e)
    db.commit()
    return user


def disconnect(db: Session, user: User) -> None:
    user.gmail_token_encrypted = None
    user.gmail_email = None
    db.commit()


def _credentials(db: Session, user: User) -> Credentials:
    if not user.gmail_token_encrypted:
        raise GmailError("Gmail account is not connected")
    creds = Credentials.from_authorized_user_info(json.loads(decrypt_str(user.gmail_token_encrypted)), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            user.gmail_token_encrypted = encrypt_str(creds.to_json())
            db.commit()
        else:
            raise GmailError("Gmail authorization expired — reconnect Gmail in Settings")
    return creds


def _service(db: Session, user: User):
    return build("gmail", "v1", credentials=_credentials(db, user), cache_discovery=False)


def build_message(sender: str | None, to: str, subject: str, body: str, attachment: tuple[bytes, str, str] | None = None,
                  in_reply_to: str | None = None) -> EmailMessage:
    msg = EmailMessage()
    msg["To"] = to
    if sender:
        msg["From"] = sender
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(body)
    if attachment:
        data, filename, mime = attachment
        maintype, subtype = mime.split("/", 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    return msg


def send_email(db: Session, user: User, to: str, subject: str, body: str,
               attachment: tuple[bytes, str, str] | None = None, thread_id: str | None = None,
               in_reply_to: str | None = None) -> dict:
    msg = build_message(user.gmail_email, to, subject, body, attachment, in_reply_to)
    payload: dict = {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}
    if thread_id:
        payload["threadId"] = thread_id
    try:
        sent = _service(db, user).users().messages().send(userId="me", body=payload).execute()
    except HttpError as e:
        raise GmailError(f"Gmail send failed: {e}") from e
    return {"id": sent.get("id"), "threadId": sent.get("threadId")}


def thread_replies(db: Session, user: User, thread_id: str) -> list[dict]:
    """Messages in the thread that were not sent by the user."""
    try:
        thread = _service(db, user).users().threads().get(
            userId="me", id=thread_id, format="metadata", metadataHeaders=["From", "Subject", "Date"]).execute()
    except HttpError as e:
        raise GmailError(f"Gmail read failed: {e}") from e
    me = (user.gmail_email or "").lower()
    replies = []
    for m in thread.get("messages", []):
        headers = {h["name"].lower(): h["value"] for h in m.get("payload", {}).get("headers", [])}
        sender = parseaddr(headers.get("from", ""))[1].lower()
        if sender and sender != me:
            replies.append({"id": m["id"], "from": sender, "subject": headers.get("subject"),
                            "snippet": m.get("snippet"), "internalDate": m.get("internalDate")})
    return replies
