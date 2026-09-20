"""
Gmail send via Sign in with Google (OAuth) — no App Password needed.

One-time: put OAuth Web client id/secret in Streamlit Secrets.
Daily use: click Connect Gmail → pick Google account → Send test.
"""
from __future__ import annotations

import base64
import json
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Optional

from .paths import DATA_DIR

TOKEN_FILE = DATA_DIR / "gmail_oauth_token.json"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]


def _oauth_secrets() -> dict[str, str]:
    out = {"client_id": "", "client_secret": "", "redirect_uri": ""}
    try:
        import streamlit as st

        out["client_id"] = str(st.secrets.get("google_oauth_client_id", "") or "").strip()
        out["client_secret"] = str(
            st.secrets.get("google_oauth_client_secret", "") or ""
        ).strip()
        out["redirect_uri"] = str(
            st.secrets.get("google_oauth_redirect_uri", "") or ""
        ).strip()
        # allow company table overrides
        if "company" in st.secrets:
            c = st.secrets["company"]
            out["client_id"] = out["client_id"] or str(
                c.get("google_oauth_client_id", "") or ""
            ).strip()
            out["client_secret"] = out["client_secret"] or str(
                c.get("google_oauth_client_secret", "") or ""
            ).strip()
    except Exception:
        pass
    return out


def oauth_configured() -> bool:
    s = _oauth_secrets()
    return bool(s["client_id"] and s["client_secret"])


def default_redirect_uri() -> str:
    s = _oauth_secrets()
    if s["redirect_uri"]:
        return s["redirect_uri"]
    try:
        import streamlit as st

        # Streamlit Cloud / browser URL if available
        url = ""
        try:
            url = str(st.get_option("browser.serverAddress") or "")
        except Exception:
            url = ""
        # Prefer explicit secret; fallback common app URL
        return (
            s["redirect_uri"]
            or "https://direct-shipper-outreach-ccrnu6jzt5dwjua7srdhha.streamlit.app/"
        )
    except Exception:
        return "http://localhost:8501/"


def _client_config(redirect_uri: str) -> dict:
    s = _oauth_secrets()
    return {
        "web": {
            "client_id": s["client_id"],
            "client_secret": s["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }


def build_auth_url(redirect_uri: Optional[str] = None) -> tuple[str, str]:
    """Return (auth_url, state)."""
    from google_auth_oauthlib.flow import Flow

    redir = redirect_uri or default_redirect_uri()
    flow = Flow.from_client_config(_client_config(redir), scopes=SCOPES)
    flow.redirect_uri = redir
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return auth_url, state


def exchange_code(code: str, redirect_uri: Optional[str] = None) -> dict:
    from google_auth_oauthlib.flow import Flow
    from google.oauth2.credentials import Credentials

    redir = redirect_uri or default_redirect_uri()
    flow = Flow.from_client_config(_client_config(redir), scopes=SCOPES)
    flow.redirect_uri = redir
    flow.fetch_token(code=code)
    creds: Credentials = flow.credentials
    data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or SCOPES),
        "email": _fetch_email(creds),
    }
    save_token(data)
    return data


def _fetch_email(creds) -> str:
    try:
        from googleapiclient.discovery import build

        svc = build("oauth2", "v2", credentials=creds, cache_discovery=False)
        info = svc.userinfo().get().execute()
        return str(info.get("email") or "")
    except Exception:
        return ""


def save_token(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    # Best-effort cloud persistence
    try:
        _save_token_sheet(data)
    except Exception:
        pass


def load_token() -> Optional[dict]:
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("refresh_token") or data.get("token"):
                return data
        except Exception:
            pass
    try:
        return _load_token_sheet()
    except Exception:
        return None


def clear_token() -> None:
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
    try:
        _save_token_sheet({})
    except Exception:
        pass


def gmail_connected() -> bool:
    tok = load_token()
    return bool(tok and (tok.get("refresh_token") or tok.get("token")))


def connected_email() -> str:
    tok = load_token() or {}
    return str(tok.get("email") or "")


def _creds_from_token(data: dict):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    creds = Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri") or "https://oauth2.googleapis.com/token",
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=data.get("scopes") or SCOPES,
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        data["token"] = creds.token
        save_token(data)
    return creds


def send_via_gmail(to_addr: str, subject: str, body: str, from_email: str = "") -> dict:
    """Send using connected Google account. Raises on hard failure."""
    from googleapiclient.discovery import build

    tok = load_token()
    if not tok:
        raise RuntimeError("Gmail not connected — click Sign in with Google first.")
    creds = _creds_from_token(tok)
    msg = MIMEText(body)
    msg["to"] = to_addr
    msg["subject"] = subject
    sender = from_email or tok.get("email") or "me"
    msg["from"] = sender
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    sent = (
        service.users()
        .messages()
        .send(userId="me", body={"raw": raw})
        .execute()
    )
    return {"id": sent.get("id"), "email": tok.get("email") or sender}


def _open_sheet():
    from .storage import _open_spreadsheet

    return _open_spreadsheet()


def _save_token_sheet(data: dict) -> None:
    import gspread

    sh = _open_sheet()
    try:
        ws = sh.worksheet("gmail_oauth")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="gmail_oauth", rows=10, cols=4)
    ws.clear()
    ws.update(
        "A1",
        [["key", "value"], ["token_json", json.dumps(data)]],
        value_input_option="USER_ENTERED",
    )


def _load_token_sheet() -> Optional[dict]:
    import gspread

    sh = _open_sheet()
    try:
        ws = sh.worksheet("gmail_oauth")
    except gspread.WorksheetNotFound:
        return None
    values = ws.get_all_values()
    for row in values[1:]:
        if row and row[0] == "token_json" and len(row) > 1 and row[1].strip():
            data = json.loads(row[1])
            if data.get("refresh_token") or data.get("token"):
                # mirror locally for speed
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                return data
    return None
