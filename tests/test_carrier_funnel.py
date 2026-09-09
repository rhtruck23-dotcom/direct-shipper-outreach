"""Carrier funnel — unit + regression (shipper path untouched)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import src.carrier_campaign as campaign
import src.carrier_fmcsa as fmcsa
import src.carrier_import as cimport
import src.carrier_leads as cleads
import src.carrier_storage as cstorage
import src.carrier_templates as ctmpl
import src.rbac as rbac


def test_carrier_key_prefers_email_then_mc():
    assert cstorage.carrier_key({"email": "A@B.com", "mc_number": "MC-1"}) == "a@b.com"
    assert cstorage.carrier_key({"mc_number": "MC-123456"}) == "mc:123456"
    assert cstorage.carrier_key({"dot_number": "DOT-99"}) == "dot:99"


def test_carrier_upsert_and_activate(tmp_path, monkeypatch):
    monkeypatch.setattr(cstorage, "CARRIER_JSON", tmp_path / "carriers.json")
    monkeypatch.setattr(cstorage, "_using_cloud", lambda: False)
    a, u = cstorage.upsert_carriers(
        [
            {
                "company_name": "OO One",
                "email": "oo1@test.com",
                "mc_number": "MC-111",
                "state": "IL",
            }
        ]
    )
    assert a == 1 and u == 0
    leads = cleads.load_carriers()
    n, skipped = cleads.activate_carrier_sequence(leads, ["oo1@test.com"])
    assert n == 1
    assert leads[0]["active_sequence"] is True


def test_carrier_templates_mention_mc_not_hard_earnings():
    subj, body = ctmpl.render_carrier_email(
        1,
        {"contact_name": "Sam", "company_name": "Sam Trucking", "mc_number": "MC-9"},
        {
            "my_company": "LogixTrek LLC",
            "my_mc": "MC-1590829",
            "my_dot": "DOT-4146389",
            "my_name": "Dispatch",
            "my_phone": "443",
            "equipment": "Reefer",
            "website": "https://www.logixtrek.com",
            "unsubscribe_note": "STOP",
            "origin_area": "IL",
        },
    )
    assert "40k" not in subj.lower() and "40k" not in body.lower()
    assert "$40" not in body
    assert "MC-1590829" in body
    assert "Sam" in body
    assert "walk through real pay" in body


def test_carrier_campaign_dry_run(tmp_path, monkeypatch):
    monkeypatch.setattr(cstorage, "CARRIER_JSON", tmp_path / "carriers.json")
    monkeypatch.setattr(cstorage, "_using_cloud", lambda: False)
    leads = [
        {
            "company_name": "C",
            "email": "c@c.com",
            "active_sequence": True,
            "status": "not_started",
            "last_step_sent": 0,
            "conversation": [],
        }
    ]
    company = {
        "send_live_emails": False,
        "my_email": "a@b.com",
        "my_company": "L",
        "my_name": "N",
        "my_phone": "1",
        "my_mc": "MC-1",
        "my_dot": "D",
        "equipment": "R",
        "unsubscribe_note": "S",
        "smtp_host": "h",
        "smtp_port": 587,
        "smtp_user": "u",
        "smtp_password": "",
    }
    with patch("src.carrier_campaign.send_email") as send:
        send.return_value = {"ok": True, "mode": "dry_run", "live": False, "at": "t"}
        with patch("src.carrier_campaign.persist_carriers"):
            results = campaign.run_due_carrier_emails(leads, company)
    assert len(results) == 1
    assert results[0]["ok"] is True
    assert leads[0]["last_step_sent"] == 1


def test_csv_and_pdf_import():
    csv_bytes = (
        b"company_name,email,mc_number,state\n"
        b"Alpha Haul,alpha@x.com,MC-55,IL\n"
    )
    rows = cimport.parse_carrier_csv(csv_bytes)
    assert rows[0]["company_name"] == "Alpha Haul"
    assert rows[0]["mc_number"] == "MC-55"

    pdf_text = "Beta Freight LLC\nMC-778899\nDOT-1234567\nops@beta.com\n(309) 555-1212\n"
    scraped = cimport.extract_carriers_from_pdf_text(pdf_text)
    assert any("778899" in (r.get("mc_number") or "") for r in scraped)
    assert any("ops@beta.com" in (r.get("email") or "") for r in scraped)


def test_fmcsa_demo_and_search():
    demo = fmcsa.demo_new_carriers("IL", days=30)
    assert len(demo) >= 3
    assert all(d["source"] == "fmcsa_demo" for d in demo)
    rows, mode = fmcsa.search_new_carriers(
        "IL", days=30, use_demo_if_needed=True, web_key="", use_census=False
    )
    assert "demo" in mode or mode.startswith("fmcsa")
    assert len(rows) >= 1


def test_census_mapper_and_pull_mocked():
    mapped = fmcsa._map_census_row(
        {
            "legal_name": "VA OWNER OP LLC",
            "dot_number": "1234567",
            "docket1": "555555",
            "docket1prefix": "MC",
            "phy_state": "VA",
            "phy_city": "Richmond",
            "phy_zip": "23219",
            "phone": "8045551212",
            "power_units": "2",
            "status_code": "A",
            "add_date": "2024-01-15T00:00:00.000",
        }
    )
    assert mapped["mc_number"] == "MC-555555"
    assert mapped["state"] == "VA"

    fake = [
        {
            "legal_name": f"Carrier {i}",
            "dot_number": str(1000 + i),
            "docket1": str(2000 + i),
            "docket1prefix": "MC",
            "phy_state": "VA",
            "phy_city": "Norfolk",
            "power_units": "3",
            "status_code": "A",
            "phone": "",
            "add_date": "2024-06-01",
        }
        for i in range(5)
    ]
    with patch("src.carrier_fmcsa.requests.get") as get:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = fake
        resp.text = ""
        get.return_value = resp
        rows, note = fmcsa.pull_census_carriers("VA", limit=5, max_power_units=10)
    assert len(rows) == 5
    assert "fmcsa_census" in note


def test_rbac_carrier_modules_and_recruiter(tmp_path, monkeypatch):
    monkeypatch.setattr(rbac, "TEAM_JSON", tmp_path / "team.json")
    assert "Find Carriers" in [m["page"] for m in rbac.MODULES.values() if m.get("page")]
    assert "carrier_recruiter" in rbac.ROLE_PRESETS
    state = rbac._blank_state()
    rbac.save_rbac_state(state)
    user, state = rbac.create_user(
        state,
        name="Recruiter",
        email="recruit@logixtrek.com",
        pin="hire1",
        role="carrier_recruiter",
    )
    pub = rbac.authenticate("recruit@logixtrek.com", "hire1")
    assert pub is not None
    assert "Carrier Pipeline" in rbac.allowed_pages(pub)
    assert "Find Leads" not in rbac.allowed_pages(pub)
    assert "Org Setup" not in rbac.allowed_pages(pub)

    leads = [
        {"email": "a@a.com", "assigned_to": user["id"]},
        {"email": "b@b.com", "assigned_to": ""},
    ]
    assert len(rbac.scope_leads(leads, pub)) == 1


def test_assign_carriers():
    leads = [
        {"email": "a@a.com", "mc_number": "", "assigned_to": ""},
        {"email": "b@b.com", "assigned_to": ""},
    ]
    out, n = rbac.assign_carriers(leads, ["a@a.com"], "u_9")
    assert n == 1
    assert out[0]["assigned_to"] == "u_9"


def test_mark_hired():
    lead = {"status": "responded", "active_sequence": True, "remarks": ""}
    cleads.mark_carrier_hired(lead)
    assert lead["status"] == "converted"
    assert lead["deal_stage"] == "signed_onboarded"
    assert "Hired under" in lead["remarks"]


def test_carrier_deal_stage_progression():
    from src.stages import set_carrier_deal_stage

    lead = {"status": "emailed_1", "active_sequence": True, "responded": False}
    set_carrier_deal_stage(lead, "applied")
    assert lead["status"] == "responded"
    assert lead["active_sequence"] is False
    set_carrier_deal_stage(lead, "packet_sent")
    assert lead["deal_stage"] == "packet_sent"
    set_carrier_deal_stage(lead, "docs_reviewed")
    set_carrier_deal_stage(lead, "signed_onboarded")
    assert lead["status"] == "converted"
    assert lead["deal_stage"] == "signed_onboarded"


def test_shipper_modules_still_present():
    pages = {m["page"] for m in rbac.MODULES.values() if m.get("page")}
    assert "Find Leads" in pages
    assert "Pipeline & Outreach" in pages
    assert "Carrier Leads" in pages
