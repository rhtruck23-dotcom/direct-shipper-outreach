"""Gmail OAuth helpers — unit tests (no network)."""
from __future__ import annotations

from src.gmail_oauth import oauth_configured, SCOPES


def test_scopes_include_gmail_send():
    assert any("gmail.send" in s for s in SCOPES)


def test_oauth_configured_false_without_secrets(monkeypatch):
    monkeypatch.setattr("src.gmail_oauth._oauth_secrets", lambda: {"client_id": "", "client_secret": "", "redirect_uri": ""})
    assert oauth_configured() is False
