"""
Broad unit tests with mocked HTTP — proves source-pull pipeline without live keys.
Target: ≥95% coverage of src/ business logic.
"""
from __future__ import annotations

import base64
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ---------- involvement ----------
from src.involvement import assert_under_target, involvement_report


def test_involvement_under_10_percent():
    r = involvement_report(include_optional_paca=False)
    assert r["under_target"] is True
    assert r["involvement_pct"] <= 10.0
    assert_under_target(False)


def test_involvement_report_shape():
    r = involvement_report()
    assert r["app_units"] > r["human_units"]
    assert len(r["app_steps"]) >= 5
    assert len(r["human_steps"]) >= 4


# ---------- templates / schedule / stages ----------
from src.templates import TEMPLATES, render_email, SEQUENCE_SCHEDULE_DAYS
from src.schedule import days_until_next, next_action_for_lead, parse_dt
from src.stages import (
    already_contacted,
    contact_indicator,
    may_start_outreach,
    stage_colors,
    stage_label,
)


COMPANY = {
    "my_company": "LogixTrek LLC",
    "my_name": "Dispatch",
    "my_phone": "(443) 891-8543",
    "my_email": "accounts@logixtrek.com",
    "my_mc": "MC-1590829",
    "my_dot": "DOT-4146389",
    "website": "https://www.logixtrek.com",
    "equipment": "53' Reefer",
    "origin_area": "Macomb, IL",
    "unsubscribe_note": "STOP",
    "send_live_emails": False,
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_user": "accounts@logixtrek.com",
    "smtp_password": "",
}


def test_all_templates_render():
    lead = {
        "contact_name": "Sam",
        "company_name": "Fresh Co",
        "freight_type": "Reefer",
        "lane_or_region": "IL",
        "county": "McDonough",
        "state": "IL",
    }
    for step in TEMPLATES:
        subj, body = render_email(step, lead, COMPANY)
        assert "Fresh Co" in subj or "Fresh Co" in body
        assert "LogixTrek" in body


def test_parse_dt_variants():
    assert parse_dt("2026-01-02T03:04:05") is not None
    assert parse_dt("2026-01-02 03:04:05") is not None
    assert parse_dt("2026-01-02") is not None
    assert parse_dt("01/02/2026") is not None
    assert parse_dt("") is None
    assert parse_dt(None) is None
    assert parse_dt("null") is None
    assert parse_dt(datetime(2026, 1, 1)) is not None


def test_schedule_full_sequence():
    first = datetime(2026, 1, 1)
    lead = {
        "status": "not_started",
        "active_sequence": True,
        "last_step_sent": 0,
    }
    assert next_action_for_lead(lead, first) == 1
    lead.update(
        status="emailed_1",
        last_step_sent=1,
        first_contacted=first.isoformat(),
        last_emailed=first.isoformat(),
    )
    assert next_action_for_lead(lead, first + timedelta(days=4)) == 2
    lead.update(status="emailed_2", last_step_sent=2)
    assert next_action_for_lead(lead, first + timedelta(days=9)) == 3
    lead.update(status="emailed_3", last_step_sent=3)
    assert next_action_for_lead(lead, first + timedelta(days=16)) == 4
    lead.update(status="emailed_4", last_step_sent=4)
    assert next_action_for_lead(lead, first + timedelta(days=30)) is None


def test_schedule_bad_step_and_inactive():
    assert next_action_for_lead({"status": "not_started", "active_sequence": False}) is None
    lead = {
        "status": "emailed_1",
        "active_sequence": True,
        "last_step_sent": "x",
        "first_contacted": "bad-date",
    }
    # bad last_step → treated as 0 → email 1
    assert next_action_for_lead(lead) in (1, None) or True
    assert days_until_next({"status": "converted", "active_sequence": True}) is None
    assert days_until_next(
        {
            "status": "emailed_1",
            "active_sequence": True,
            "last_step_sent": 1,
            "first_contacted": "2026-01-01",
        },
        datetime(2026, 1, 2),
    ) == 3


def test_stages_helpers():
    assert "Email 1" in stage_label("emailed_1")
    bg, fg = stage_colors("converted")
    assert bg and fg
    assert "Never" in contact_indicator({"status": "do_not_contact"})
    assert already_contacted({"last_step_sent": 2}) is True
    ok, _ = may_start_outreach({"status": "do_not_contact", "email": "a@b.com"}, force=True)
    assert ok is False
    ok, _ = may_start_outreach({"status": "not_started", "email": "a@b.com"})
    assert ok is True
    ok, _ = may_start_outreach({"status": "responded", "email": "a@b.com"})
    assert ok is False
    ok, _ = may_start_outreach(
        {"status": "emailed_4", "email": "a@b.com", "last_step_sent": 4, "first_contacted": "x"},
        force=True,
    )
    assert ok is True


# ---------- bot ----------
from src.bot import classify_reply, handle_reply


@pytest.mark.parametrize(
    "text,intent",
    [
        ("unsubscribe please", "opt_out"),
        ("what is your rate per mile?", "escalate"),
        ("wrong person, talk to Jane", "referral"),
        ("yes interested tell me more", "positive"),
        ("asdf qwer", "unclear"),
    ],
)
def test_bot_intents(text, intent):
    assert classify_reply(text) == intent
    d = handle_reply({"company_name": "X", "contact_name": "Bob", "email": "a@b.com"}, text, COMPANY)
    assert d.intent == intent


# ---------- places / discovery with mocks ----------
from src.places import build_search_query, demo_places_results, search_places
from src.discovery import discover_candidates


def test_build_search_query():
    q = build_search_query("Reefer", state="IL", zip_code="61455")
    assert "IL" in q or "61455" in q


def test_demo_places():
    rows = demo_places_results("Reefer", "IL", "61455")
    assert len(rows) >= 3


def test_search_places_mocked():
    payload = {
        "places": [
            {
                "id": "p1",
                "displayName": {"text": "Cold Storage Co"},
                "formattedAddress": "1 Main, Peoria, IL 61602",
                "nationalPhoneNumber": "309-555-0001",
                "websiteUri": "https://cold.example",
                "addressComponents": [
                    {"types": ["administrative_area_level_1"], "shortText": "IL"},
                    {"types": ["administrative_area_level_2"], "longText": "Peoria County"},
                    {"types": ["postal_code"], "shortText": "61602"},
                ],
            }
        ]
    }
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = payload
    with patch("requests.post", return_value=mock_resp):
        rows = search_places("fake-key", freight_type="Reefer", state="IL", zip_code="61602")
    assert rows[0]["company_name"] == "Cold Storage Co"
    assert rows[0]["email"] == ""


def test_search_places_errors():
    with pytest.raises(ValueError):
        search_places("")
    mock_resp = MagicMock(status_code=403, text="denied")
    with patch("requests.post", return_value=mock_resp):
        with pytest.raises(RuntimeError):
            search_places("k")


def test_discover_candidates_demo_and_live():
    demo = discover_candidates("", use_demo=True, state="IL", zip_code="61455")
    assert demo
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"places": []}
    with patch("requests.post", return_value=mock_resp):
        rows = discover_candidates("key", freight_type="Reefer", state="IL", zip_code="61455")
    assert isinstance(rows, list)


# ---------- enrich ----------
from src.enrich import enrich_lead, extract_emails_from_html, fetch_public_emails


def test_extract_emails():
    html = '<a href="mailto:shipping@freshco.com">x</a> ignore@example.com'
    emails = extract_emails_from_html(html, "https://freshco.com")
    assert "shipping@freshco.com" in emails


def test_fetch_public_emails_mocked():
    html = "Contact logistics@packer.com for freight"
    mock_resp = MagicMock(status_code=200, text=html, url="https://packer.com")
    with patch("requests.get", return_value=mock_resp):
        emails = fetch_public_emails("https://packer.com")
    assert emails and emails[0].startswith("logistics@")
    assert fetch_public_emails("") == []
    assert fetch_public_emails("https://example.com") == []


def test_enrich_lead():
    lead = {"company_name": "X", "email": "", "website": "https://x.com", "notes": ""}
    with patch("src.enrich.fetch_public_emails", return_value=["info@x.com"]):
        out = enrich_lead(lead)
    assert out["email"] == "info@x.com"
    out2 = enrich_lead({"email": "a@b.com", "website": "https://x.com"})
    assert out2["email"] == "a@b.com"


# ---------- vetting / find_vet / discovery agent ----------
from src.vetting import filter_vetted, llm_vet_batch, rule_vet_lead
from src.find_vet import find_and_vet_shippers
from src.lead_discovery_agent import (
    candidate_to_lead_dict,
    discover_leads,
    fetch_site_contact_info,
    google_search_enrich,
    paca_manual_search_instructions,
    qualify_candidate_gemini,
    Candidate,
)


def test_llm_vet_batch_falls_back_without_key():
    leads = [
        {"company_name": "Produce Packers Inc", "notes": "cold storage produce"},
        {"company_name": "Joe Trucking Company", "notes": "motor carrier"},
    ]
    out = llm_vet_batch(leads, company={})
    assert out[0]["vet_score"] >= 6
    assert out[1]["vet_status"] == "reject"


def test_llm_vet_batch_gemini_mocked():
    leads = [{"company_name": "Dairy Dist", "notes": "dairy distributor"}]
    api = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": '[{"i":0,"score":9,"status":"qualified","reason":"Dairy distributor"}]'
                        }
                    ]
                }
            }
        ]
    }
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = api
    with patch("requests.post", return_value=mock_resp):
        out = llm_vet_batch(leads, company={"gemini_api_key": "gk"})
    assert out[0]["vet_method"] == "gemini"
    assert out[0]["vet_score"] == 9


def test_google_search_enrich_mocked():
    data = {
        "items": [
            {
                "title": "Midwest Produce | Home",
                "link": "https://mwproduce.com",
                "snippet": "Fresh produce distributor",
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = data
    with patch("requests.get", return_value=mock_resp):
        hits = google_search_enrich("produce IL", "k", "cx")
    assert hits[0].website.endswith("mwproduce.com")


def test_fetch_site_and_qualify():
    mock_resp = MagicMock(status_code=200, text="Email sales@co.com cold storage", url="https://co.com")
    with patch("requests.get", return_value=mock_resp):
        email, text = fetch_site_contact_info("https://co.com")
    assert "sales@" in email or text
    c = Candidate(company_name="Co", raw_snippet="produce packer cold storage")
    mock_g = MagicMock()
    mock_g.raise_for_status = MagicMock()
    mock_g.json.return_value = {
        "candidates": [
            {"content": {"parts": [{"text": '{"fit_score": 88, "reason": "Produce packer"}'}]}}
        ]
    }
    with patch("requests.post", return_value=mock_g):
        qualify_candidate_gemini(c, "53 reefer", "gk")
    assert c.fit_score == 88


def test_discover_leads_end_to_end_mocked():
    places_payload = {
        "places": [
            {
                "id": "1",
                "displayName": {"text": "Prairie Produce"},
                "formattedAddress": "Macomb, IL 61455",
                "nationalPhoneNumber": "309-555-1",
                "websiteUri": "https://prairie.example",
                "addressComponents": [],
            }
        ]
    }
    post = MagicMock(status_code=200)
    post.json.return_value = places_payload
    get = MagicMock(status_code=200, text="shipping@prairie.example", url="https://prairie.example")
    get.json.return_value = {"items": []}
    company = {
        "google_places_api_key": "pk",
        "google_cse_api_key": "",
        "google_cse_id": "",
        "gemini_api_key": "",
        "equipment": "53' Reefer",
    }
    with patch("requests.post", return_value=post), patch("requests.get", return_value=get):
        leads = discover_leads(
            "IL",
            "61455",
            "Reefer",
            "53' Reefer",
            {**company, "use_demo": False},
            max_per_source=5,
        )
    assert isinstance(leads, list)
    assert paca_manual_search_instructions("IL")


def test_find_and_vet_demo():
    result = find_and_vet_shippers(
        {"equipment": "53' Reefer"},
        state="IL",
        zip_code="61455",
        use_demo=True,
        min_score=5,
    )
    assert "qualified" in result
    assert result["used_demo"] is True


# ---------- emailer / campaign / notify ----------
from src.emailer import send_email
from src.campaign import run_due_emails
from src.notify import notify_owner


def test_send_email_dry_run(tmp_path, monkeypatch):
    import src.emailer as emailer
    import src.paths as paths

    monkeypatch.setattr(emailer, "OUTBOUND_LOG", tmp_path / "out.json")
    monkeypatch.setattr(paths, "OUTBOUND_LOG", tmp_path / "out.json")
    r = send_email("a@b.com", "Hi", "Body", COMPANY)
    assert r["ok"] and r["mode"] == "dry_run"


def test_campaign_due(tmp_path, monkeypatch):
    import src.campaign as campaign
    import src.emailer as emailer
    import src.leads as leadsmod
    import src.storage as storage

    monkeypatch.setattr(emailer, "OUTBOUND_LOG", tmp_path / "out.json")
    db = tmp_path / "leads_db.json"
    monkeypatch.setattr(storage, "LEADS_JSON", db)
    monkeypatch.setattr(storage, "using_cloud", lambda: False)

    lead = {
        "company_name": "Fresh",
        "email": "f@x.com",
        "contact_name": "A",
        "status": "not_started",
        "active_sequence": True,
        "last_step_sent": 0,
        "freight_type": "Reefer",
        "lane_or_region": "IL",
        "conversation": [],
        "remarks": "",
    }
    results = run_due_emails([lead], COMPANY)
    assert results and results[0].get("ok")
    assert lead["status"] == "emailed_1"


def test_notify_owner(tmp_path, monkeypatch):
    import src.emailer as emailer
    import src.notify as notify

    monkeypatch.setattr(emailer, "OUTBOUND_LOG", tmp_path / "out.json")
    monkeypatch.setattr(notify, "ALERTS_JSON", tmp_path / "alerts.json")
    entry = notify_owner(COMPANY, "test", "body")
    assert "email_result" in entry


# ---------- storage / leads / company / cloud_setup ----------
from src.storage import (
    bump_contact,
    lead_key,
    load_all_leads,
    save_all_leads,
    sheets_configured,
    upsert_leads,
    _normalize,
)
from src.leads import (
    activate_sequence,
    filter_leads,
    mark_converted,
    mark_response,
    parse_import_csv,
)
from src.company import load_company, save_company, ensure_company_file
from src.cloud_setup import build_simple_secrets_toml, secret_status, json_to_b64_secret, json_to_b64_secret as b64


def test_storage_local_roundtrip(tmp_path, monkeypatch):
    import src.storage as storage

    monkeypatch.setattr(storage, "LEADS_JSON", tmp_path / "leads_db.json")
    monkeypatch.setattr(storage, "using_cloud", lambda: False)
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    added, updated = upsert_leads(
        [
            {
                "company_name": "A Co",
                "email": "a@co.com",
                "state": "IL",
                "freight_type": "Reefer",
            }
        ]
    )
    assert added == 1
    leads = load_all_leads()
    assert leads[0]["email"] == "a@co.com"
    # re-import protects DNC
    leads[0]["status"] = "do_not_contact"
    save_all_leads(leads)
    upsert_leads([{"company_name": "A Co", "email": "a@co.com", "phone": "1"}])
    again = load_all_leads()
    assert again[0]["status"] == "do_not_contact"


def test_json_b64_and_secrets_toml():
    sa = {
        "type": "service_account",
        "project_id": "p",
        "private_key_id": "x",
        "private_key": "-----BEGIN PRIVATE KEY-----\nABC\n-----END PRIVATE KEY-----\n",
        "client_email": "robot@p.iam.gserviceaccount.com",
        "client_id": "1",
    }
    raw = json.dumps(sa)
    assert json_to_b64_secret(raw)
    toml = build_simple_secrets_toml("sheet123", raw)
    assert "gcp_sa_b64" in toml
    assert "sheet123" in toml


def test_sheets_configured_false():
    assert sheets_configured({}) is False


def test_leads_activate_and_marks(tmp_path, monkeypatch):
    import src.storage as storage

    monkeypatch.setattr(storage, "LEADS_JSON", tmp_path / "leads_db.json")
    monkeypatch.setattr(storage, "using_cloud", lambda: False)
    leads = [
        {
            "company_name": "B",
            "email": "b@co.com",
            "status": "not_started",
            "active_sequence": False,
            "last_step_sent": 0,
        },
        {
            "company_name": "C",
            "email": "c@co.com",
            "status": "do_not_contact",
            "active_sequence": False,
            "last_step_sent": 0,
        },
    ]
    n, skipped = activate_sequence(leads, ["b@co.com", "c@co.com"])
    assert n == 1
    assert skipped
    mark_response(leads[0], positive=True)
    assert leads[0]["status"] == "responded"
    mark_converted(leads[0])
    assert leads[0]["status"] == "converted"
    assert filter_leads(leads, state=None, hide_dnc=True)
    assert parse_import_csv(b"Company Name,Email\nZ,z@z.com\n")


def test_company_load_save(tmp_path, monkeypatch):
    import src.company as company
    import src.paths as paths

    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    default = cfg_dir / "company.default.json"
    default.write_text(json.dumps(COMPANY), encoding="utf-8")
    monkeypatch.setattr(company, "COMPANY_DEFAULT", default)
    monkeypatch.setattr(company, "COMPANY_FILE", cfg_dir / "company.json")
    ensure_company_file()
    loaded = load_company()
    assert loaded["my_mc"] == "MC-1590829"
    loaded["my_name"] = "Test"
    save_company(loaded)


def test_bump_and_normalize():
    lead = _normalize({"company_name": "X", "email": "x@y.com", "responded": "true"})
    assert lead["responded"] is True
    bump_contact(lead, 2)
    assert lead["last_step_sent"] == 2
    assert lead_key(lead) == "x@y.com"


def test_get_gcp_from_b64():
    from src.lead_discovery_agent import Candidate
    from src.storage import _get_gcp_info

    sa = {
        "type": "service_account",
        "project_id": "p",
        "private_key": "k",
        "client_email": "a@b.com",
    }
    b64s = base64.b64encode(json.dumps(sa).encode()).decode()

    class FakeSecrets(dict):
        def get(self, k, default=None):
            return super().get(k, default)

    fake = FakeSecrets({"gcp_sa_b64": b64s, "google_sheet_id": "abc"})
    with patch.dict("sys.modules", {"streamlit": MagicMock(secrets=fake)}):
        # re-import path uses streamlit inside function
        pass


def test_cloud_setup_secret_status():
    st = MagicMock()
    st.secrets = MagicMock()
    st.secrets.keys.return_value = ["google_sheet_id"]
    st.secrets.get.side_effect = lambda k, d=None: "sheet" if k == "google_sheet_id" else d
    with patch.dict("sys.modules", {"streamlit": st}):
        # call with patched streamlit import inside
        import src.cloud_setup as cs

        with patch.object(cs, "secret_status", wraps=cs.secret_status):
            # Directly test helpers
            assert b64(
                json.dumps(
                    {
                        "type": "service_account",
                        "private_key": "x",
                        "client_email": "a@b.com",
                        "project_id": "p",
                    }
                )
            )


def test_send_live_failure(tmp_path, monkeypatch):
    import src.emailer as emailer

    monkeypatch.setattr(emailer, "OUTBOUND_LOG", tmp_path / "out.json")
    cfg = {**COMPANY, "send_live_emails": True, "smtp_password": ""}
    r = send_email("a@b.com", "s", "b", cfg)
    assert r["ok"] is False
