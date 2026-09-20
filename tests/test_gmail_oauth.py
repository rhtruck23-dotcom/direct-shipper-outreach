"""Gmail OAuth helpers — unit tests (no network)."""
from __future__ import annotations

from src.gmail_oauth import _oauth_secrets, oauth_configured, SCOPES


def test_scopes_include_gmail_send():
    assert any("gmail.send" in s for s in SCOPES)


def test_oauth_configured_false_without_secrets(monkeypatch):
    monkeypatch.setattr(
        "src.gmail_oauth._oauth_secrets",
        lambda: {"client_id": "", "client_secret": "", "redirect_uri": ""},
    )
    assert oauth_configured() is False


def test_oauth_configured_true_when_id_and_secret(monkeypatch):
    monkeypatch.setattr(
        "src.gmail_oauth._oauth_secrets",
        lambda: {
            "client_id": "cid.apps.googleusercontent.com",
            "client_secret": "secret",
            "redirect_uri": "https://example.com/",
        },
    )
    assert oauth_configured() is True


def test_oauth_secrets_reads_company_file(monkeypatch, tmp_path):
    """Company file fields alone are enough (no Streamlit Secrets)."""
    company = {
        "google_oauth_client_id": "file-client-id",
        "google_oauth_client_secret": "file-secret",
        "google_oauth_redirect_uri": "https://app.example/",
    }
    monkeypatch.setattr("src.company.load_company", lambda: company)

    # Pretend streamlit secrets/session are unavailable
    class _NoSecrets:
        def get(self, *a, **k):
            raise KeyError("no secrets")

        def __contains__(self, key):
            return False

    class _FakeSt:
        secrets = _NoSecrets()
        session_state = {}

    monkeypatch.setitem(__import__("sys").modules, "streamlit", _FakeSt())
    # Re-import path: _oauth_secrets imports streamlit inside try
    out = _oauth_secrets()
    assert out["client_id"] == "file-client-id"
    assert out["client_secret"] == "file-secret"
    assert out["redirect_uri"] == "https://app.example/"


def test_oauth_secrets_prefers_session_company(monkeypatch):
    class _EmptySecrets:
        def get(self, *a, **k):
            return ""

        def __contains__(self, key):
            return False

    class _FakeSt:
        secrets = _EmptySecrets()
        session_state = {
            "company": {
                "google_oauth_client_id": "session-id",
                "google_oauth_client_secret": "session-secret",
                "google_oauth_redirect_uri": "https://session.example/",
            }
        }

    monkeypatch.setitem(__import__("sys").modules, "streamlit", _FakeSt())
    monkeypatch.setattr(
        "src.company.load_company",
        lambda: {
            "google_oauth_client_id": "file-id",
            "google_oauth_client_secret": "file-secret",
        },
    )
    out = _oauth_secrets()
    assert out["client_id"] == "session-id"
    assert out["client_secret"] == "session-secret"
    assert out["redirect_uri"] == "https://session.example/"
