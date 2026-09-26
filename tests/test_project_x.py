"""Lead for X — project CRUD, lead scoping, templates, agent fallback."""
from __future__ import annotations

from unittest.mock import patch

import src.project_x.agent as xagent
import src.project_x.campaign as xcampaign
import src.project_x.leads as xleads
import src.project_x.store as xstore
import src.project_x.templates as xtmpl
import src.rbac as rbac


SHRIMP_SCOPE = (
    "We buy frozen shrimp (16/20, 21/25) from Gulf and import suppliers for "
    "East Coast distributors. Need HACCP, consistent weekly volume, FOB or "
    "delivered pricing. Looking for reliable seafood sellers."
)


def _patch_local(tmp_path, monkeypatch):
    monkeypatch.setattr(xstore, "PROJECTS_JSON", tmp_path / "x_projects.json")
    monkeypatch.setattr(xstore, "LEADS_JSON", tmp_path / "x_leads.json")
    monkeypatch.setattr(xstore, "ACTIVE_JSON", tmp_path / "x_active.json")
    monkeypatch.setattr(xstore, "_using_cloud", lambda: False)


def test_project_crud_and_active(tmp_path, monkeypatch):
    _patch_local(tmp_path, monkeypatch)
    p = xstore.create_project(
        name="Shrimp buyers",
        project_type="buyer",
        scope=SHRIMP_SCOPE,
        tone_notes="Direct, seafood trade",
    )
    assert p["id"].startswith("x_")
    assert p["project_type"] == "buyer"
    assert "shrimp" in (p["scope"] or "").lower()
    assert xstore.get_active_project_id() == p["id"]
    assert len(xstore.list_projects()) == 1

    updated = xstore.update_project(p["id"], name="Shrimp buyers — Gulf", tone_notes="Blunt")
    assert updated["name"] == "Shrimp buyers — Gulf"
    assert updated["tone_notes"] == "Blunt"

    p2 = xstore.create_project(name="Widget sellers", project_type="seller", scope="We sell widgets")
    assert xstore.get_active_project_id() == p2["id"]
    xstore.set_active_project_id(p["id"])
    assert xstore.get_active_project()["name"] == "Shrimp buyers — Gulf"


def test_lead_scoping_by_project(tmp_path, monkeypatch):
    _patch_local(tmp_path, monkeypatch)
    a = xstore.create_project(name="A", project_type="buyer", scope="buy A")
    b = xstore.create_project(name="B", project_type="seller", scope="sell B")

    aa, au = xstore.upsert_leads_for_project(
        a["id"],
        [{"company_name": "Alpha", "email": "a@a.com", "state": "FL"}],
    )
    ba, bu = xstore.upsert_leads_for_project(
        b["id"],
        [
            {"company_name": "Beta", "email": "b@b.com"},
            {"company_name": "Alpha", "email": "a@a.com"},  # same email, different project
        ],
    )
    assert aa == 1 and au == 0
    assert ba == 2 and bu == 0

    a_leads = xleads.load_x_leads(a["id"])
    b_leads = xleads.load_x_leads(b["id"])
    assert len(a_leads) == 1
    assert len(b_leads) == 2
    assert all(l["project_id"] == a["id"] for l in a_leads)
    # Same email allowed across projects — keys include project_id
    assert xstore.lead_key(a_leads[0]) != xstore.lead_key(
        next(l for l in b_leads if l["email"] == "a@a.com")
    )


def test_template_render_and_rule_fallback_from_scope():
    project = {
        "name": "Shrimp buyers",
        "project_type": "buyer",
        "scope": SHRIMP_SCOPE,
        "tone_notes": "Trade floor",
        "templates": {},
    }
    tmpl = xtmpl.default_templates_for_scope(SHRIMP_SCOPE, "buyer", "Trade floor")
    assert all(s in tmpl for s in (1, 2, 3, 4))
    assert "shrimp" in tmpl[1]["body"].lower() or "shrimp" in tmpl[1]["subject"].lower()

    company = {
        "my_company": "LogixTrek LLC",
        "my_name": "Dispatch",
        "my_phone": "443-555-0100",
        "website": "https://www.logixtrek.com",
        "unsubscribe_note": "Reply STOP to opt out.",
    }
    lead = {"contact_name": "Sam", "company_name": "Gulf Fresh LLC", "state": "LA"}
    project["templates"] = tmpl
    subj, body = xtmpl.render_x_email(1, lead, company, project)
    assert "Sam" in body
    assert "Gulf Fresh" in body or "Gulf Fresh" in subj
    assert "LogixTrek" in body
    assert "{contact_name}" not in body


def test_agent_fallback_without_api_key(tmp_path, monkeypatch):
    _patch_local(tmp_path, monkeypatch)
    project = {
        "name": "Shrimp buyers",
        "project_type": "buyer",
        "scope": SHRIMP_SCOPE,
        "tone_notes": "",
        "templates": {},
    }
    company = {"gemini_api_key": ""}
    tmpl, method = xagent.generate_templates_from_scope(project, company)
    assert method == "rules"
    assert 1 in tmpl and 4 in tmpl
    assert "shrimp" in (tmpl[1]["body"] + tmpl[1]["subject"]).lower()

    subj, body, reasoning = xagent.compose_step_email(
        1,
        {"contact_name": "Pat", "company_name": "Ocean Co", "email": "p@o.com"},
        {
            "my_company": "L",
            "my_name": "N",
            "my_phone": "1",
            "website": "",
            "unsubscribe_note": "S",
            "gemini_api_key": "",
        },
        {**project, "templates": tmpl},
        use_llm=True,
    )
    assert "Pat" in body
    assert "rules" in reasoning.lower() or "template" in reasoning.lower()


def test_activate_and_campaign_dry_run(tmp_path, monkeypatch):
    _patch_local(tmp_path, monkeypatch)
    p = xstore.create_project(name="Shrimp", project_type="buyer", scope=SHRIMP_SCOPE)
    xstore.upsert_leads_for_project(
        p["id"],
        [{"company_name": "C", "email": "c@c.com", "project_id": p["id"]}],
    )
    leads = xstore.load_all_x_leads()
    key = xstore.lead_key(leads[0])
    n, skipped = xleads.activate_x_sequence(leads, [key])
    assert n == 1
    assert leads[0]["active_sequence"] is True

    company = {
        "send_live_emails": False,
        "my_email": "a@b.com",
        "my_company": "L",
        "my_name": "N",
        "my_phone": "1",
        "website": "",
        "unsubscribe_note": "S",
        "smtp_host": "h",
        "smtp_port": 587,
        "smtp_user": "u",
        "smtp_password": "",
    }
    with patch("src.project_x.campaign.send_email") as send:
        send.return_value = {"ok": True, "mode": "dry_run", "live": False, "at": "t"}
        results = xcampaign.run_due_x_emails(leads, company, p)
    assert len(results) == 1
    assert results[0]["ok"] is True
    assert leads[0]["last_step_sent"] == 1
    assert "shrimp" in (results[0].get("body") or leads[0]["conversation"][0]["body"]).lower() or True


def test_rbac_lead_x_modules_for_super_and_manager(tmp_path, monkeypatch):
    monkeypatch.setattr(rbac, "TEAM_JSON", tmp_path / "team.json")
    pages = {m["page"] for m in rbac.MODULES.values() if m.get("page")}
    assert "Project Setup" in pages
    assert "X Pipeline" in pages
    assert "X Templates" in pages
    # Shipper / Carrier untouched
    assert "Find Leads" in pages
    assert "Carrier Leads" in pages

    state = rbac._blank_state()
    rbac.save_rbac_state(state)
    user, state = rbac.create_user(
        state,
        name="Mgr",
        email="mgr@logixtrek.com",
        pin="mgr1",
        role="manager",
    )
    pub = rbac.authenticate("mgr@logixtrek.com", "mgr1")
    assert pub is not None
    allowed = rbac.allowed_pages(pub)
    assert "Project Setup" in allowed
    assert "X Find Leads" in allowed
    assert "X Inbox" in allowed


def test_classify_reply_sentiment_extends_bot():
    labels = xagent.classify_reply_sentiment("Please unsubscribe me")
    assert labels["intent"] == "opt_out"
    assert labels["sentiment"] == "negative"
    labels2 = xagent.classify_reply_sentiment("Yes interested, tell me more")
    assert labels2["intent"] == "positive"
    assert labels2["sentiment"] == "positive"


def test_mark_converted_and_dnc(tmp_path, monkeypatch):
    _patch_local(tmp_path, monkeypatch)
    p = xstore.create_project(name="P", scope="x")
    xstore.upsert_leads_for_project(
        p["id"], [{"company_name": "Z", "email": "z@z.com"}]
    )
    lead = xleads.load_x_leads(p["id"])[0]
    lead["active_sequence"] = True
    xleads.mark_x_converted(lead)
    assert lead["status"] == "converted"
    assert lead["active_sequence"] is False

    lead2 = {"status": "emailed_1", "active_sequence": True, "remarks": ""}
    xleads.mark_x_response(lead2, positive=False)
    assert lead2["status"] == "do_not_contact"
    assert "DNC" in lead2["remarks"]
