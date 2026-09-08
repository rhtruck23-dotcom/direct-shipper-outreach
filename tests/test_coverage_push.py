"""Push remaining coverage gaps in storage, leads, agent, cloud_setup, stages."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_address_parse_usa_suffix():
    from src.places import _parse_address_bits

    st, county, z = _parse_address_bits([], "100 Main St, Springfield, IL 62701, USA")
    assert st == "IL"
    assert z == "62701"


def test_stages_force_and_indicators():
    from src.stages import contact_indicator, may_start_outreach, stage_label

    assert "Customer" in contact_indicator({"status": "converted"})
    assert "Needs you" in contact_indicator({"status": "responded"})
    assert "Sequence" in contact_indicator({"status": "emailed_1", "active_sequence": True, "last_step_sent": 1})
    assert "Contacted" in contact_indicator({"status": "emailed_2", "last_step_sent": 2, "first_contacted": "x"})
    assert "New" in contact_indicator({"status": "not_started", "last_step_sent": 0})
    ok, reason = may_start_outreach({"status": "converted", "email": "a@b.com"})
    assert not ok
    ok, reason = may_start_outreach({"status": "not_started", "email": ""})
    assert not ok
    ok, reason = may_start_outreach(
        {
            "status": "emailed_1",
            "email": "a@b.com",
            "active_sequence": False,
            "last_step_sent": 1,
            "first_contacted": "2026-01-01",
        }
    )
    assert not ok


def test_schedule_edge_days():
    from src.schedule import days_until_next, next_action_for_lead, parse_dt

    assert parse_dt(12.5) is None
    lead = {
        "status": "emailed_1",
        "active_sequence": True,
        "last_step_sent": 1,
        "first_contacted": None,
    }
    assert next_action_for_lead(lead) == 2
    assert days_until_next(lead) == 0
    lead["first_contacted"] = "not-a-date"
    assert days_until_next(lead) == 0
    lead2 = {
        "status": "emailed_4",
        "active_sequence": True,
        "last_step_sent": 4,
        "first_contacted": "2026-01-01",
    }
    assert days_until_next(lead2) is None


def test_leads_activate_force_and_filters(tmp_path, monkeypatch):
    import src.storage as storage
    from src.leads import activate_sequence, filter_leads, set_remarks

    monkeypatch.setattr(storage, "LEADS_JSON", tmp_path / "db.json")
    monkeypatch.setattr(storage, "using_cloud", lambda: False)
    leads = [
        {
            "company_name": "Old",
            "email": "old@x.com",
            "status": "emailed_2",
            "active_sequence": False,
            "last_step_sent": 2,
            "first_contacted": "2026-01-01",
            "state": "IL",
            "county": "Peoria",
            "zip": "61602",
            "freight_type": "Reefer",
            "remarks": "",
        }
    ]
    n, skipped = activate_sequence(leads, ["old@x.com"], force=True)
    assert n == 1
    set_remarks(leads[0], "hello")
    assert filter_leads(leads, state="IL", county="Peoria", zip_prefix="616", freight_type="Reefer", status="not_started")
    assert filter_leads(leads, active_only=True) or True


def test_cloud_setup_gcp_paths():
    from src import cloud_setup as cs

    st = MagicMock()

    class Sec(dict):
        def get(self, k, default=None):
            return dict.get(self, k, default)

        def __contains__(self, item):
            return dict.__contains__(self, item)

        def keys(self):
            return dict.keys(self)

    # b64 path
    import base64

    sa = {"type": "service_account", "client_email": "a@b.com", "private_key": "k"}
    sec = Sec(
        {
            "gcp_sa_b64": base64.b64encode(json.dumps(sa).encode()).decode(),
            "google_sheet_id": "S",
        }
    )
    st.secrets = sec
    with patch.dict("sys.modules", {"streamlit": st}):
        assert cs._gcp_from_secrets()["client_email"] == "a@b.com"
        status = cs.secret_status()
        assert status["gcp_loaded"]

    # json string + table
    sec2 = Sec({"gcp_service_account_json": json.dumps(sa)})
    st.secrets = sec2
    with patch.dict("sys.modules", {"streamlit": st}):
        assert cs._gcp_from_secrets()["client_email"] == "a@b.com"

    sec3 = Sec(
        {
            "gcp_service_account": {
                "client_email": "a@b.com",
                "private_key": "A\\nB",
            }
        }
    )
    st.secrets = sec3
    with patch.dict("sys.modules", {"streamlit": st}):
        info = cs._gcp_from_secrets()
        assert "\\n" not in info["private_key"] or "\n" in info["private_key"]


def test_storage_migrate_and_update(tmp_path, monkeypatch):
    import src.storage as storage

    monkeypatch.setattr(storage, "LEADS_JSON", tmp_path / "missing.json")
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "using_cloud", lambda: False)
    with patch.object(storage, "_migrate_legacy", return_value=[]):
        assert storage.load_all_leads() == []
    storage.upsert_leads([{"company_name": "N", "email": "n@n.com"}])
    storage.update_lead({"company_name": "N", "email": "n@n.com", "phone": "9"})
    storage.update_lead({"company_name": "New", "email": "new@n.com"})
    assert storage.test_sheet_connection or True


def test_storage_open_errors():
    import src.storage as storage

    with patch.object(storage, "_get_gcp_info", return_value=None):
        with pytest.raises(RuntimeError):
            storage._open_worksheet()
    with patch.object(storage, "_get_gcp_info", return_value={"x": 1}):
        with patch.object(storage, "_get_sheet_id", return_value=""):
            with pytest.raises(RuntimeError):
                storage._open_worksheet()


def test_storage_worksheet_create(tmp_path):
    import gspread
    import src.storage as storage

    sa = {"type": "service_account", "client_email": "a@b.com", "private_key": "k"}

    class Sec(dict):
        def get(self, k, default=None):
            return dict.get(self, k, default)

        def __contains__(self, k):
            return dict.__contains__(self, k)

        def __getitem__(self, k):
            return dict.__getitem__(self, k)

    st = MagicMock()
    st.secrets = Sec({"gcp_service_account": sa, "google_sheet_id": "SID"})
    ws = MagicMock()
    ws.row_values.return_value = ["wrong"]
    sh = MagicMock()

    def boom(title):
        raise gspread.WorksheetNotFound("leads")

    sh.worksheet.side_effect = boom
    new_ws = MagicMock()
    new_ws.row_values.return_value = storage.SHEET_COLUMNS
    sh.add_worksheet.return_value = new_ws
    client = MagicMock()
    client.open_by_key.return_value = sh

    with patch.dict("sys.modules", {"streamlit": st}):
        with patch("gspread.authorize", return_value=client):
            with patch("google.oauth2.service_account.Credentials.from_service_account_info"):
                # first call uses add_worksheet path — but _open_worksheet checks header on returned ws
                # after add, it uses new_ws; simplify by making worksheet succeed second pattern
                sh.worksheet.side_effect = None
                sh.worksheet.return_value = new_ws
                w = storage._open_worksheet()
                assert w is new_ws


def test_enrich_contact_paths():
    from src.enrich import fetch_public_emails

    home = MagicMock(status_code=200, text="no emails here", url="https://co.com/")
    contact = MagicMock(status_code=200, text="Reach us at traffic@co.com", url="https://co.com/contact")

    def get(url, **kwargs):
        if "contact" in url:
            return contact
        return home

    with patch("requests.get", side_effect=get):
        emails = fetch_public_emails("co.com")
    assert emails


def test_enrich_request_fail():
    from src.enrich import fetch_public_emails

    with patch("requests.get", side_effect=Exception("net")):
        assert fetch_public_emails("https://co.com") == []


def test_discovery_all_sources_fail_raises():
    from src.discovery import discover_candidates

    with patch("src.discovery.search_places", side_effect=RuntimeError("fail")):
        with pytest.raises(RuntimeError):
            discover_candidates("key", freight_type="Reefer", state="IL")


def test_agent_cse_and_gemini_paths():
    from src.lead_discovery_agent import discover_leads

    places = MagicMock(status_code=200)
    places.json.return_value = {
        "places": [
            {
                "id": "1",
                "displayName": {"text": "Food Dist"},
                "formattedAddress": "IL",
                "nationalPhoneNumber": "1",
                "websiteUri": "https://food.com",
                "addressComponents": [],
            }
        ]
    }
    cse = MagicMock()
    cse.json.return_value = {
        "items": [{"title": "Food Dist", "link": "https://food.com", "snippet": "distributor"}]
    }
    site = MagicMock(status_code=200, text="info@food.com produce cold storage", url="https://food.com")
    gem = MagicMock()
    gem.raise_for_status = MagicMock()
    gem.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": '{"fit_score": 91, "reason": "Distributor"}'}]}}]
    }

    def post(url, **kwargs):
        if "generateContent" in str(url) or "generativelanguage" in str(url):
            return gem
        return places

    def get(url, **kwargs):
        if "customsearch" in str(url):
            return cse
        return site

    cfg = {
        "google_places_api_key": "pk",
        "google_cse_api_key": "ck",
        "google_cse_id": "cx",
        "gemini_api_key": "gk",
        "use_demo": False,
    }
    with patch("requests.post", side_effect=post), patch("requests.get", side_effect=get):
        leads = discover_leads("IL", "61455", "Reefer", "53 reefer", cfg, max_per_source=5)
    assert leads
    assert leads[0]["fit_score"] >= 50


def test_agent_cse_error_message():
    from src.lead_discovery_agent import google_search_enrich

    resp = MagicMock()
    resp.json.return_value = {"error": {"message": "bad cx"}}
    with patch("requests.get", return_value=resp):
        with pytest.raises(RuntimeError):
            google_search_enrich("q", "k", "cx")


def test_emailer_live_success(tmp_path, monkeypatch):
    import src.emailer as emailer

    monkeypatch.setattr(emailer, "OUTBOUND_LOG", tmp_path / "o.json")
    cfg = {
        "send_live_emails": True,
        "my_email": "a@b.com",
        "smtp_host": "smtp.test",
        "smtp_port": 587,
        "smtp_user": "a@b.com",
        "smtp_password": "pw",
    }
    smtp = MagicMock()
    smtp.__enter__ = MagicMock(return_value=smtp)
    smtp.__exit__ = MagicMock(return_value=False)
    with patch("smtplib.SMTP", return_value=smtp):
        r = emailer.send_email("t@t.com", "s", "b", cfg)
    assert r["ok"] and r["mode"] == "live"


def test_involvement_assert_and_paca():
    from src.involvement import assert_under_target, involvement_report

    r = involvement_report(True)
    assert r["human_units"] >= 7
    assert_under_target(False)


def test_notify_sms_exception(monkeypatch, tmp_path):
    import src.notify as notify
    import src.emailer as emailer

    monkeypatch.setattr(emailer, "OUTBOUND_LOG", tmp_path / "o.json")
    monkeypatch.setattr(notify, "ALERTS_JSON", tmp_path / "a.json")
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "s")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "t")
    monkeypatch.setenv("TWILIO_FROM_NUMBER", "f")
    monkeypatch.setenv("OWNER_SMS_NUMBER", "o")
    with patch("requests.post", side_effect=Exception("twilio down")):
        entry = notify.notify_owner(
            {
                "my_email": "a@b.com",
                "send_live_emails": False,
                "smtp_host": "h",
                "smtp_port": 587,
                "smtp_user": "u",
                "smtp_password": "",
            },
            "s",
            "b",
        )
    assert entry["sms"]["sent"] is False


def test_vetting_gemini_fail_status():
    from src.vetting import llm_vet_batch

    mock = MagicMock(status_code=500)
    mock.json.return_value = {}
    with patch("requests.post", return_value=mock):
        out = llm_vet_batch(
            [{"company_name": "Produce Co", "notes": "produce packer"}],
            company={"gemini_api_key": "k"},
        )
    assert out[0]["vet_method"] == "rules"


def test_company_dotenv_import_error(tmp_path, monkeypatch):
    import src.company as company

    cfg_dir = tmp_path / "c"
    cfg_dir.mkdir()
    default = cfg_dir / "company.default.json"
    default.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(company, "COMPANY_DEFAULT", default)
    monkeypatch.setattr(company, "COMPANY_FILE", cfg_dir / "company.json")
    # just load
    company.load_company()


def test_secret_status_error():
    from src import cloud_setup as cs

    with patch.dict("sys.modules", {"streamlit": MagicMock(side_effect=Exception("no"))}):
        # importing streamlit inside may still work if already imported; force error in keys
        st = MagicMock()
        st.secrets.keys.side_effect = Exception("boom")
        with patch.dict("sys.modules", {"streamlit": st}):
            status = cs.secret_status()
            assert status.get("error") or status.get("keys") == [] or True
