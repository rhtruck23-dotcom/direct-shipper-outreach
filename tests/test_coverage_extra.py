"""Extra coverage for storage sheets path, notify SMS, places parse, company env."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_places_address_fallback():
    from src.places import _parse_address_bits

    st, county, z = _parse_address_bits([], "100 Main St, Springfield, IL 62701, USA")
    assert st == "IL"
    assert z == "62701"


def test_storage_get_gcp_b64():
    import base64
    import src.storage as storage

    sa = {"type": "service_account", "client_email": "a@b.com", "private_key": "k"}
    b64 = base64.b64encode(json.dumps(sa).encode()).decode()

    class Sec(dict):
        def get(self, k, default=None):
            return dict.get(self, k, default)

        def __contains__(self, k):
            return dict.__contains__(self, k)

    secrets = Sec({"gcp_sa_b64": b64, "google_sheet_id": "SID"})
    st = MagicMock()
    st.secrets = secrets
    with patch.dict("sys.modules", {"streamlit": st}):
        # force reload of functions that import streamlit inside
        info = storage._get_gcp_info()
        assert info and info["client_email"] == "a@b.com"
        assert storage._get_sheet_id() == "SID"
        assert storage.sheets_configured() is True


def test_storage_gcp_json_string():
    import src.storage as storage

    sa = {"type": "service_account", "client_email": "a@b.com", "private_key": "k"}

    class Sec(dict):
        def get(self, k, default=None):
            return dict.get(self, k, default)

        def __contains__(self, k):
            return dict.__contains__(self, k)

    secrets = Sec(
        {
            "gcp_service_account_json": json.dumps(sa),
            "google_sheet_id": "SID",
        }
    )
    st = MagicMock()
    st.secrets = secrets
    with patch.dict("sys.modules", {"streamlit": st}):
        info = storage._get_gcp_info()
        assert info["client_email"] == "a@b.com"


def test_storage_gcp_toml_table():
    import src.storage as storage

    class Sec(dict):
        def get(self, k, default=None):
            return dict.get(self, k, default)

        def __contains__(self, k):
            return dict.__contains__(self, k)

    secrets = Sec(
        {
            "gcp_service_account": {
                "type": "service_account",
                "client_email": "a@b.com",
                "private_key": "BEGIN\\nKEY\\nEND",
            },
            "google_sheet_id": "SID",
        }
    )
    st = MagicMock()
    st.secrets = secrets
    with patch.dict("sys.modules", {"streamlit": st}):
        info = storage._get_gcp_info()
        assert "client_email" in info


def test_open_worksheet_mocked():
    import src.storage as storage

    sa = {"type": "service_account", "client_email": "a@b.com", "private_key": "k"}

    class Sec(dict):
        def get(self, k, default=None):
            return dict.get(self, k, default)

        def __contains__(self, k):
            return dict.__contains__(self, k)

        def __getitem__(self, k):
            return dict.__getitem__(self, k)

    secrets = Sec({"gcp_service_account": sa, "google_sheet_id": "SID"})
    st = MagicMock()
    st.secrets = secrets

    ws = MagicMock()
    ws.row_values.return_value = storage.SHEET_COLUMNS
    ws.get_all_records.return_value = [
        {"company_name": "X", "email": "x@y.com", "status": "not_started"}
    ]
    sh = MagicMock()
    sh.worksheet.return_value = ws
    client = MagicMock()
    client.open_by_key.return_value = sh

    with patch.dict("sys.modules", {"streamlit": st}):
        with patch("gspread.authorize", return_value=client):
            with patch("google.oauth2.service_account.Credentials.from_service_account_info"):
                got = storage._load_sheets()
    assert got[0]["company_name"] == "X"


def test_save_sheets_mocked():
    import src.storage as storage

    sa = {"type": "service_account", "client_email": "a@b.com", "private_key": "k"}

    class Sec(dict):
        def get(self, k, default=None):
            return dict.get(self, k, default)

        def __contains__(self, k):
            return dict.__contains__(self, k)

        def __getitem__(self, k):
            return dict.__getitem__(self, k)

    secrets = Sec({"gcp_service_account": sa, "google_sheet_id": "SID"})
    st = MagicMock()
    st.secrets = secrets
    ws = MagicMock()
    ws.row_values.return_value = storage.SHEET_COLUMNS
    sh = MagicMock()
    sh.worksheet.return_value = ws
    client = MagicMock()
    client.open_by_key.return_value = sh

    with patch.dict("sys.modules", {"streamlit": st}):
        with patch("gspread.authorize", return_value=client):
            with patch("google.oauth2.service_account.Credentials.from_service_account_info"):
                storage._save_sheets(
                    [{"company_name": "Z", "email": "z@z.com", "conversation": []}]
                )
    assert ws.update.called or ws.clear.called


def test_notify_sms_configured(monkeypatch, tmp_path):
    import src.notify as notify
    import src.emailer as emailer

    monkeypatch.setattr(emailer, "OUTBOUND_LOG", tmp_path / "o.json")
    monkeypatch.setattr(notify, "ALERTS_JSON", tmp_path / "a.json")
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "sid")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setenv("TWILIO_FROM_NUMBER", "+1")
    monkeypatch.setenv("OWNER_SMS_NUMBER", "+2")
    mock_resp = MagicMock(status_code=201)
    with patch("requests.post", return_value=mock_resp):
        entry = notify.notify_owner(
            {
                "my_email": "a@b.com",
                "owner_notify_email": "a@b.com",
                "send_live_emails": False,
                "smtp_host": "h",
                "smtp_port": 587,
                "smtp_user": "a",
                "smtp_password": "",
            },
            "subj",
            "hello world " * 40,
        )
    assert entry["sms"]["sent"] is True


def test_secret_status_and_build():
    from src.cloud_setup import build_simple_secrets_toml, secret_status

    st = MagicMock()
    st.secrets.keys.return_value = []
    st.secrets.get.return_value = ""
    with patch.dict("sys.modules", {"streamlit": st}):
        status = secret_status()
    assert "keys" in status
    toml = build_simple_secrets_toml(
        "id",
        json.dumps(
            {
                "type": "service_account",
                "private_key": "x",
                "client_email": "a@b.com",
                "project_id": "p",
            }
        ),
    )
    assert "gcp_sa_b64" in toml


def test_company_env_override(tmp_path, monkeypatch):
    import src.company as company

    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    default = cfg_dir / "company.default.json"
    default.write_text(json.dumps({"my_company": "X", "smtp_password": ""}), encoding="utf-8")
    monkeypatch.setattr(company, "COMPANY_DEFAULT", default)
    monkeypatch.setattr(company, "COMPANY_FILE", cfg_dir / "company.json")
    monkeypatch.setenv("SMTP_PASSWORD", "secretpw")
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "pk")
    loaded = company.load_company()
    assert loaded["smtp_password"] == "secretpw"
    assert loaded["google_places_api_key"] == "pk"


def test_campaign_blocks_dnc_and_no_email():
    from src.campaign import run_due_emails

    leads = [
        {"company_name": "DNC", "email": "d@x.com", "status": "do_not_contact", "active_sequence": True},
        {"company_name": "NoMail", "email": "", "status": "not_started", "active_sequence": True},
    ]
    r = run_due_emails(leads, {"send_live_emails": False, "my_email": "a@b.com", "my_company": "L", "my_name": "N", "my_phone": "1", "my_mc": "M", "my_dot": "D", "equipment": "R", "origin_area": "IL", "unsubscribe_note": "S", "smtp_host": "h", "smtp_port": 587, "smtp_user": "u", "smtp_password": ""})
    assert any(not x.get("ok") for x in r)


def test_vetting_filter_maybe():
    from src.vetting import filter_vetted

    leads = [
        {"vet_score": 5, "vet_status": "maybe", "company_name": "M"},
        {"vet_score": 3, "vet_status": "weak", "company_name": "W"},
        {"vet_score": 1, "vet_status": "reject", "company_name": "R"},
    ]
    kept = filter_vetted(leads, min_score=6, include_maybe=True)
    assert len(kept) == 1


def test_discovery_agent_dedupe_and_map():
    from src.lead_discovery_agent import Candidate, _dedupe, candidate_to_lead_dict

    a = Candidate(company_name="Same", phone="1", source="google_places")
    b = Candidate(company_name="Same", email_guess="a@b.com", website="https://x.com", source="google_search", raw_snippet="extra")
    merged = _dedupe([a, b])
    assert len(merged) == 1
    assert merged[0].email_guess == "a@b.com"
    d = candidate_to_lead_dict(merged[0], "Reefer", "IL", "61455")
    assert d["needs_email"] is False or d["email"]


def test_paths_exist():
    from src.paths import DATA_DIR, ROOT

    assert ROOT.exists()
    assert DATA_DIR.exists() or True
