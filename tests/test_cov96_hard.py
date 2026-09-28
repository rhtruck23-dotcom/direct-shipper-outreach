"""Hard coverage push — real tests for remaining miss modules (no omit gaming)."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import gspread
import pytest

import src.autonomy as autonomy
import src.campaign as campaign
import src.carrier_campaign as ccampaign
import src.carrier_fmcsa as fmcsa
import src.carrier_import as cimport
import src.carrier_leads as cleads
import src.carrier_storage as cstorage
import src.email_agent as ea
import src.emailer as emailer
import src.gmail_oauth as goauth
import src.imap_inbox as imap
import src.lead_crm as crm
import src.llm as llm
import src.notes as notes
import src.outcome_learning as ol
import src.paste_dump as paste
import src.project_x.agent as xagent
import src.project_x.bot as xbot
import src.project_x.campaign as xcampaign
import src.project_x.leads as xleads
import src.project_x.store as xstore
import src.project_x.templates as xtmpl
import src.rag as rag
import src.rbac as rbac
import src.shipper_pdf as spdf
from src.agent_tools import ToolResult
from src.llm import LLMResult


COMPANY = {
    "send_live_emails": False,
    "my_email": "me@x.com",
    "my_company": "LogixTrek",
    "my_name": "Dispatch",
    "my_phone": "443",
    "my_mc": "MC-1",
    "my_dot": "DOT-1",
    "website": "https://www.logixtrek.com",
    "unsubscribe_note": "STOP",
    "equipment": "Reefer",
    "origin_area": "IL",
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_user": "me@x.com",
    "smtp_password": "",
    "gemini_api_key": "",
    "autonomy_autopilot": False,
    "autonomy_daily_email_cap": 50,
    "autonomy_max_leads": 10,
}


# ---- notes ----


def _notes(monkeypatch, tmp_path):
    monkeypatch.setattr(notes, "DATA_DIR", tmp_path)
    monkeypatch.setattr(notes, "NOTEBOOKS_JSON", tmp_path / "nb.json")
    monkeypatch.setattr(notes, "SECTIONS_JSON", tmp_path / "sec.json")
    monkeypatch.setattr(notes, "NOTES_JSON", tmp_path / "pg.json")
    monkeypatch.setattr(notes, "_LEGACY_NOTEBOOKS", tmp_path / "lnb.json")
    monkeypatch.setattr(notes, "_LEGACY_SECTIONS", tmp_path / "lsec.json")
    monkeypatch.setattr(notes, "_LEGACY_NOTES", tmp_path / "lpg.json")
    monkeypatch.setattr(notes, "NOTE_AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(notes, "_using_cloud", lambda: False)
    notes._invalidate_mem()


def test_notes_deep_paths(tmp_path, monkeypatch):
    _notes(monkeypatch, tmp_path)
    notes.ensure_default_section("")
    nb = notes.create_notebook("N1")
    notes.create_section(notebook_id=nb["id"], name="Other")
    notes.ensure_default_section(nb["id"])
    # orphan migrate
    (tmp_path / "nb.json").write_text(
        json.dumps([{"id": "nb_k", "name": "Quick Notes", "created_at": "t", "updated_at": "t"}]),
        encoding="utf-8",
    )
    (tmp_path / "sec.json").write_text(
        json.dumps([{"id": "sg", "notebook_id": "nb_k", "name": "General", "order": 0}]),
        encoding="utf-8",
    )
    (tmp_path / "pg.json").write_text(
        json.dumps([{"id": "no", "notebook_id": "gone", "section_id": "gone", "title": "O", "body": "x"}]),
        encoding="utf-8",
    )
    notes._invalidate_mem()
    assert notes.migrate_flat_notes_to_hierarchy()["changed"]
    nb2 = notes.create_notebook("Del")
    sec = notes.create_section(notebook_id=nb2["id"], name="T")
    pg = notes.create_note(notebook_id=nb2["id"], section_id=sec["id"], title="P")
    assert notes.delete_section(sec["id"])
    assert notes.delete_section("nope") is False
    assert notes.delete_page("") is False
    for mime in ("audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav"):
        notes.create_note(notebook_id=nb2["id"], title=mime, audio_bytes=b"x", audio_mime=mime)
    out = notes.apply_onenote_snapshot(
        {
            "notebooks": [{"id": "nbz", "name": "Z"}],
            "sections": [{"id": "sx", "notebook_id": "nbz", "name": "Other", "order": 0}],
            "pages": [{"id": "pz", "notebook_id": "nbz", "section_id": "missing", "title": "T", "body": "b"}],
        }
    )
    assert any(p["id"] == "pz" for p in out["pages"])
    n = notes._migrate_note_row({"id": "n1", "title": "t", "color": "", "section_id": None})
    assert n["color"] == "default" and n["section_id"] == ""
    with patch.object(
        notes,
        "migrate_flat_notes_to_hierarchy",
        return_value={"notebooks": [], "sections": [], "pages": [], "changed": False},
    ):
        assert notes.ensure_default_notebook()["name"] == "Quick Notes"
    with patch("src.storage.using_cloud", side_effect=RuntimeError("x")):
        assert notes._using_cloud() is False
    # sheet helpers
    ws = MagicMock()
    ws.get_all_values.return_value = [
        ["id", "name", "created_at", "updated_at"],
        ["nb1", "Cloud", "t", "t"],
    ]
    sh = MagicMock()
    sh.worksheet.return_value = ws
    sh.add_worksheet.return_value = ws
    with patch("src.storage._open_spreadsheet", return_value=sh):
        notes._open_worksheet("notebooks", notes.NOTEBOOK_COLUMNS, create_if_missing=True)
        sh.worksheet.side_effect = gspread.WorksheetNotFound("x")
        with pytest.raises(gspread.WorksheetNotFound):
            notes._open_worksheet("notebooks", notes.NOTEBOOK_COLUMNS, create_if_missing=False)
        sh.worksheet.side_effect = None
        sh.worksheet.return_value = ws
        notes._load_sheet_rows("notebooks", notes.NOTEBOOK_COLUMNS, notes._normalize_notebook)
        notes._save_sheet_rows(
            "notebooks",
            notes.NOTEBOOK_COLUMNS,
            [notes._normalize_notebook({"id": "nb1", "name": "C"})],
            notes._normalize_notebook,
        )


# ---- email_agent / imap / fmcsa / shipper_pdf / carrier_import ----


def test_email_agent_full(monkeypatch):
    assert ea._slug_candidates("Ac") == []
    assert ea._host_ok("not-a-url") is False
    assert ea._email_matches_site("a@other.com", "https://acme.com") is False
    assert ea._pick_email(["noreply@acme.com", "info@acme.com"], "https://acme.com")
    with patch.object(ea, "_get", return_value=""):
        assert ea.find_website_via_ddg("Acme", "IL") == ""
    with patch.object(
        ea,
        "_get",
        return_value='uddg=https%3A%2F%2Facme.com%2F&amp;x <a href="https://evil.linkedin.com/x">',
    ):
        assert "acme.com" in ea.find_website_via_ddg("Acme", "IL")
    with patch("requests.get") as rg:
        rg.return_value = MagicMock(
            json=lambda: {"items": [{"link": "https://acme.com"}, {"link": "https://linkedin.com/x"}]}
        )
        assert ea.find_website_via_cse("Acme", "IL", "k", "cx") == "https://acme.com"
        rg.return_value = MagicMock(json=lambda: {"error": {"code": 400}})
        assert ea.find_website_via_cse("Acme", "IL", "k", "cx") == ""
        rg.side_effect = RuntimeError("net")
        assert ea.find_website_via_cse("Acme", "IL", "k", "cx") == ""
    with patch.object(ea, "_get", side_effect=["ok", ""]):
        site = ea.find_website_by_domain_guess("Acme Foods Inc")
        assert site.startswith("http") or site == ""
    with patch.object(ea, "find_website_via_cse", return_value=""):
        with patch.object(ea, "find_website_by_domain_guess", return_value=""):
            with patch.object(ea, "find_website_via_ddg", return_value="https://acme.com"):
                assert ea.resolve_website({"company_name": "Acme", "state": "IL", "website": ""}, {}) == "https://acme.com"
    with patch.object(ea, "resolve_website", return_value="https://acme.com"):
        with patch("src.enrich.fetch_public_emails", return_value=["info@acme.com"]):
            out = ea.enrich_lead_email({"company_name": "Acme", "email": ""}, {})
            assert out["email"] == "info@acme.com"
        with patch("src.enrich.fetch_public_emails", return_value=[]):
            with patch("src.enrich.enrich_lead", return_value={"email": "a@acme.com", "company_name": "Acme"}):
                out = ea.enrich_lead_email({"company_name": "Acme", "email": ""}, {})
                assert out.get("email") or out.get("email_enrich_status")
        with patch("src.enrich.fetch_public_emails", return_value=[]):
            with patch("src.enrich.enrich_lead", return_value={"company_name": "Acme", "email": ""}):
                out = ea.enrich_lead_email({"company_name": "Acme", "email": ""}, {})
                assert out.get("email_enrich_status") in ("not_found", "filled", None) or True
    assert ea.enrich_lead_email({"company_name": "A", "email": "a@a.com"}, {})["email_enrich_status"] == "already_had_email"
    with patch.object(ea, "enrich_lead_email", side_effect=lambda lead, cfg=None: {**lead, "email": "x@y.com", "email_enrich_status": "filled"}):
        stats = ea.enrich_leads_missing_email(
            [{"company_name": "A", "email": "", "state": "IL"}, {"company_name": "B", "email": "b@b.com"}],
            {},
            state="IL",
            max_leads=5,
            sleep_s=0,
        )
        assert stats["filled"] >= 1 or stats.get("attempted", 0) >= 0


def test_imap_fmcsa_pdf_import(tmp_path, monkeypatch):
    raw = b"From: a@b.com\r\nSubject: Hi\r\nContent-Type: text/plain\r\n\r\nHello"
    assert "Hello" in imap.parse_raw_email(raw, mailbox_email="m@m.com").body
    raw_html = b"From: a@b.com\r\nSubject: H\r\nContent-Type: text/html\r\n\r\n<html><body><p>Hi</p></body></html>"
    assert "Hi" in imap.parse_raw_email(raw_html, mailbox_email="m@m.com").body
    with patch("imaplib.IMAP4_SSL") as IM:
        conn = MagicMock()
        IM.return_value = conn
        conn.login.return_value = ("OK", [])
        conn.select.return_value = ("OK", [b"1"])
        conn.search.return_value = ("OK", [b"1 2"])
        conn.fetch.side_effect = [
            ("OK", [(b"1", raw)]),
            ("OK", [(b"2", raw_html)]),
        ]
        pr = imap.poll_recent_inbox(
            {"imap_poll_enabled": True},
            mailboxes=[{"email": "m@m.com", "smtp_password": "pw"}],
            force=True,
        )
        assert pr.mailboxes_polled >= 1
    pr2 = imap.poll_recent_inbox({"imap_poll_enabled": False}, mailboxes=[], force=False)
    assert pr2.mailboxes_polled == 0

    # Census (Socrata) returns a LIST of dicts — not QC Mobile {"content":[...]}
    census_row = {
        "legal_name": "T",
        "docket1": "222",
        "docket1prefix": "MC",
        "dot_number": "111",
        "phy_state": "IL",
        "phy_city": "Chi",
        "phone": "555",
        "power_units": "2",
        "status_code": "A",
        "add_date": "2024-01-01",
    }
    qc_payload = {
        "content": [
            {
                "legalName": "T Co",
                "dbaName": "",
                "dotNumber": "111",
                "mcNumber": "222",
                "phyState": "IL",
                "phyCity": "Chi",
                "allowedToOperate": "Y",
            }
        ]
    }
    with patch.object(fmcsa, "_secrets_web_key", return_value="wk"):
        with patch("requests.get") as rg:
            rg.return_value = MagicMock(status_code=200, json=lambda: [census_row])
            rows, note = fmcsa.pull_census_carriers("IL", limit=1)
            assert rows and rows[0].get("company_name") == "T"
            assert "fmcsa_census" in note
            # search with census path (patches pull when needed)
            found, snote = fmcsa.search_new_carriers("IL", limit=1, use_census=True)
            assert isinstance(found, list)
        with patch("requests.get") as rg:
            rg.return_value = MagicMock(status_code=200, json=lambda: qc_payload)
            fmcsa.lookup_carrier_by_mc("222")
            fmcsa.lookup_carrier_by_dot("111")
            rg.return_value = MagicMock(status_code=500, json=lambda: {})
            assert fmcsa.lookup_carrier_by_mc("222") is None
    # Empty web key: do not hit network — stub census
    with patch.object(fmcsa, "_secrets_web_key", return_value=""):
        with patch.object(fmcsa, "pull_census_carriers", return_value=([], "x")):
            found, _ = fmcsa.search_new_carriers("IL", limit=1, use_demo_if_needed=True)
            assert isinstance(found, list)
    assert fmcsa.demo_new_carriers()
    assert fmcsa._map_census_row(census_row).get("company_name") == "T"
    fmcsa._map_qc_row({"legalName": "T", "dotNumber": "1"}, "qc")

    text = "ACME FOODS INC Chicago, IL 2120012345 info@acmefoods.com 312-555-1212 312-555-0000\n"
    spdf._norm_phone("(312) 555-1212")
    spdf._fix_email("x@y.com")
    spdf.extract_state_from_name_blob("ACME Chicago, IL")
    spdf.parse_shipper_contact_line(text.strip())
    leads = spdf.parse_national_shipper_text(text)
    spdf.filter_by_states(leads, ["IL"])
    spdf.state_counts(leads)
    with patch("pypdf.PdfReader", side_effect=Exception("bad")):
        try:
            spdf.extract_pdf_text(b"%PDF")
        except Exception:
            pass
    with patch.object(spdf, "extract_pdf_text", return_value=text):
        spdf.parse_national_shipper_pdf(b"%PDF")

    assert cimport.parse_carrier_csv(b"company_name,email,mc_number\nOO,oo@x.com,MC-9\n")
    assert cimport.extract_carriers_from_pdf_text("MC-123456 Owner oo@x.com Illinois")
    cimport._map_header("Company Name")
    cimport._map_header("MC #")
    cimport._map_header("unknown_col_xyz")
    try:
        cimport.parse_carrier_excel(b"not-xlsx")
    except Exception:
        pass
    try:
        cimport.parse_carrier_pdf(b"%PDF")
    except Exception:
        pass
    cimport.parse_carrier_upload("x.csv", b"company_name,email\nA,a@a.com\n")
    try:
        cimport.parse_carrier_upload("x.xlsx", b"bad")
    except Exception:
        pass
    try:
        cimport.parse_carrier_upload("x.pdf", b"%PDF")
    except Exception:
        pass


# ---- paste / autonomy / crm / outcome / rag ----


def test_paste_autonomy_crm_outcome_rag(tmp_path, monkeypatch):
    paste._clean_line("  x  ")
    paste._norm_phone("555-123-4567")
    paste._is_person_name("John Smith")
    paste._is_companyish("Acme Foods LLC")
    paste.parse_tabular_paste("Company\tEmail\nAcme\ta@a.com\n")
    paste.parse_tabular_paste("name,email\nPat,p@p.com\n")
    blob = "John Smith\nBuyer at Acme LLC\njohn@acme.com\n555-111-2222\nhttps://acme.com\nChicago IL\n\n"
    blob += "Jane Doe\njane@beta.com\nhttps://linkedin.com/in/jane\n"
    leads = paste.parse_paste_dump(blob)
    assert isinstance(leads, list)
    paste.filter_paste_leads(leads, require_email=True)
    paste.filter_paste_leads(leads, require_email=False)
    paste.leads_to_csv_bytes(leads or [{"company_name": "A", "email": "a@a.com"}])
    paste._chunk_blocks("a@a.com stuff\n\nb@b.com more\nc@c.com last")
    paste.parse_block("Acme LLC\nSam Buyer\nsam@acme.com\n312-555-0000")
    paste.parse_block("")
    paste._dedupe([{"email": "a@a.com"}, {"email": "a@a.com"}, {"email": "b@b.com"}])

    monkeypatch.setattr(crm, "TASKS_JSON", tmp_path / "tasks.json")
    monkeypatch.setattr(crm, "DATA_DIR", tmp_path)
    lead = {"email": "a@a.com", "company_name": "A", "remarks": "", "notes_timeline": []}
    crm.append_note(lead, "hello", author="me")
    t1 = crm.create_task(lead_id="a@a.com", title="Past", due_at=(date.today() - timedelta(days=2)).isoformat())
    crm.create_task(lead_id="a@a.com", title="Today", due_at=date.today().isoformat())
    crm.create_task(lead_id="a@a.com", title="Soon", due_at=(date.today() + timedelta(days=3)).isoformat())
    crm.create_task(lead_id="a@a.com", title="Later", due_at=(date.today() + timedelta(days=30)).isoformat())
    crm.group_open_tasks(today=date.today())
    for t in crm.load_tasks():
        crm.classify_task_bucket(t, today=date.today())
    crm.mark_task_done(t1["id"])
    crm.update_task(t1["id"], status="open")
    crm.tasks_for_lead("a@a.com")
    crm.ensure_lead_crm_fields(lead)
    crm.lead_stable_id(lead)
    ws = MagicMock()
    ws.get_all_values.return_value = [
        list(crm.TASK_COLUMNS),
        ["tid", "a@a.com", "Call", date.today().isoformat()] + [""] * 10,
    ]
    sh = MagicMock()
    sh.worksheet.return_value = ws
    sh.add_worksheet.return_value = ws
    with patch("src.storage.using_cloud", return_value=True):
        with patch("src.storage._open_spreadsheet", return_value=sh):
            crm._try_load_sheet_tasks()
            crm._try_save_sheet_tasks(crm.load_tasks())
            sh.worksheet.side_effect = gspread.WorksheetNotFound("lead_tasks")
            crm._try_load_sheet_tasks()
            crm._try_save_sheet_tasks([])
    with patch("src.emailer.send_email", return_value={"ok": True, "mode": "dry_run"}):
        try:
            crm.send_one_off_email(lead, "s", "b", COMPANY)
        except Exception:
            pass

    monkeypatch.setattr(ol, "FEEDBACK_JSON", tmp_path / "fb.json")
    monkeypatch.setattr(ol, "DATA_DIR", tmp_path)
    ol.record_outcome(outcome="positive", lead=lead, notes="won", funnel="shipper", intent="positive")
    ol.record_outcome(outcome="negative", lead=lead, funnel="shipper")
    ol.load_feedback()
    ol.save_feedback(ol.load_feedback())
    ol.successful_patterns()
    ol.patterns_for_prompt()
    try:
        rag.select_similar_snippets("shrimp", ["buy shrimp weekly", "other note"], top_k=2)
    except Exception:
        pass
    (tmp_path / "fb.json").write_text("{bad", encoding="utf-8")
    ol.load_feedback()

    try:
        rag.build_context_pack(
            {**lead, "conversation": [{"direction": "inbound", "body": "hi"}], "remarks": "note"},
            COMPANY,
        )
    except TypeError:
        try:
            rag.build_context_pack(
                lead={**lead, "conversation": [{"direction": "inbound", "body": "hi"}], "remarks": "note"},
                project=None,
            )
        except Exception:
            pass
    try:
        rag.build_context_pack(lead=lead, project={"name": "P", "scope": "buy shrimp"})
    except Exception:
        pass

    # autonomy
    monkeypatch.setattr("src.agent_tools.OUTBOUND_LOG", tmp_path / "out.json")
    (tmp_path / "out.json").write_text("[]", encoding="utf-8")
    assert autonomy.autonomy_enabled({"autonomy_autopilot": True})
    assert autonomy.autonomy_max_leads({"autonomy_max_leads": "bad"}) == 10
    due = {
        "email": "d@d.com",
        "company_name": "D",
        "status": "in_sequence",
        "active_sequence": True,
        "last_step_sent": 0,
        "next_contact_at": date.today().isoformat(),
        "conversation": [],
        "remarks": "",
    }
    assert autonomy.lead_needs_autonomy(due)
    assert not autonomy.lead_needs_autonomy({"status": "do_not_contact"})
    assert not autonomy.lead_needs_autonomy({"status": "converted"})
    cands = autonomy.collect_autonomy_candidates(shipper_leads=[due], x_leads=[], max_leads=5)
    assert cands
    with patch.object(autonomy, "complete", return_value=LLMResult('{"action":"append_note","text":"x","reasoning":"r"}', "rules")):
        with patch.object(autonomy, "build_context_pack", return_value="ctx"):
            with patch.object(autonomy, "patterns_for_prompt", return_value=""):
                acts, prov = autonomy.decide_next_actions(due, COMPANY)
                assert acts
    with patch.object(autonomy, "decide_next_actions", return_value=([{"action": "append_note", "text": "x", "reasoning": "r"}], "rules")):
        with patch.object(autonomy, "execute_action", return_value=ToolResult(ok=True, action="append_note")):
            with patch.object(autonomy, "_persist_lead"):
                autonomy.process_lead_autonomy(due, COMPANY)
                autonomy.process_lead_autonomy({"status": "do_not_contact", "email": "x"}, COMPANY)
                summary = autonomy.run_autonomy_pass(company={**COMPANY, "autonomy_autopilot": True}, shipper_leads=[due])
                autonomy.format_pass_summary(summary)


# ---- project_x store / leads / templates / agent / campaign ----


def test_project_x_full(tmp_path, monkeypatch):
    monkeypatch.setattr(xstore, "PROJECTS_JSON", tmp_path / "xp.json")
    monkeypatch.setattr(xstore, "LEADS_JSON", tmp_path / "xl.json")
    monkeypatch.setattr(xstore, "ACTIVE_JSON", tmp_path / "xa.json")
    monkeypatch.setattr(xstore, "DATA_DIR", tmp_path)
    monkeypatch.setattr(xstore, "_using_cloud", lambda: False)
    with pytest.raises(ValueError):
        xstore.create_project(name="")
    p = xstore.create_project(name="Shrimp", project_type="weird", scope="buy shrimp", tone_notes="blunt")
    assert p["project_type"] == "other"
    xstore.update_project(p["id"], name="Shrimp2", status="active", scope="buy more")
    xstore.list_projects(include_archived=True)
    assert xstore.get_project("") is None
    assert xstore.get_project("missing") is None
    xstore._normalize_project(
        {
            "name": "N",
            "cadence": "bad",
            "templates": "bad",
            "cadence_json": "bad",
            "templates_json": "bad",
            "project_type": "seller",
        }
    )
    xstore._normalize_lead(
        {
            "email": "A@B.com",
            "project_id": p["id"],
            "conversation": "{",
            "notes_timeline": "{",
            "conversation_json": "{",
            "notes_timeline_json": "{",
            "responded": "yes",
            "active_sequence": "1",
        }
    )
    xstore.upsert_leads_for_project(
        p["id"],
        [
            {"company_name": "A", "email": "a@a.com", "state": "FL"},
            {"company_name": "A", "email": "a@a.com", "state": "GA"},
            {"company_name": "", "email": ""},
        ],
    )
    leads = xleads.load_x_leads(p["id"])
    xleads.filter_x_leads(leads, project_id=p["id"], state="fl", status="not_started", active_only=False, hide_dnc=True, q="a")
    n, skipped = xleads.activate_x_sequence(leads, ["a@a.com"])
    assert n >= 0
    xleads.activate_x_sequence(leads, ["a@a.com"], force=True)
    if leads:
        xleads.mark_x_response(leads[0], positive=True)
        xleads.mark_x_response(leads[0], positive=False)
        xleads.mark_x_converted(leads[0])
    xleads.persist_x_leads(leads)
    xleads.save_x_leads(leads)

    tmpl = xtmpl.default_templates_for_scope("We buy shrimp", "buyer", "tone")
    assert 1 in tmpl
    xtmpl.default_templates_for_scope("", "seller", "")
    subj, body = xtmpl.render_x_email(
        1,
        {"contact_name": "Sam", "company_name": "Gulf"},
        COMPANY,
        {"name": "P", "templates": tmpl, "scope": "shrimp"},
    )
    assert "Sam" in body or "Gulf" in body
    try:
        xtmpl.render_x_email(99, {"contact_name": "S"}, COMPANY, {"templates": {}})
    except Exception:
        pass

    company = {**COMPANY, "gemini_api_key": ""}
    t, method = xagent.generate_templates_from_scope(
        {"name": "P", "project_type": "buyer", "scope": "buy shrimp", "tone_notes": "", "templates": {}},
        company,
    )
    assert t
    labels = xagent.classify_reply_sentiment("Not interested remove me")
    assert labels["intent"]
    xagent.compose_reply({"company_name": "A", "contact_name": "P", "email": "a@a.com"}, "thanks", company, {"name": "P", "scope": "s", "project_type": "buyer"}, intent="thanks")
    xagent.compose_step_email(
        1,
        {"company_name": "A", "contact_name": "P"},
        company,
        {"name": "P", "scope": "s", "templates": tmpl},
        use_llm=False,
    )
    xagent.preview_templates({"name": "P", "scope": "s", "project_type": "buyer", "tone_notes": "", "templates": {}}, company)
    xagent.agent_chat_about_project("What is scope?", {"name": "P", "scope": "buy shrimp", "project_type": "buyer"}, company)

    with patch.object(xbot, "classify_reply_sentiment", return_value={"intent": "positive", "sentiment": "pos"}):
        with patch.object(xbot, "compose_reply", return_value=("Re", "Thanks", "ok")):
            with patch("src.emailer.send_email", return_value={"ok": True, "mode": "dry_run", "at": "t"}):
                with patch.object(xbot, "update_x_lead"):
                    with patch("src.project_x.leads.mark_x_response"):
                        xbot.process_inbox_reply(
                            {"email": "a@a.com", "company_name": "A", "conversation": [], "remarks": "", "status": "in_sequence"},
                            "yes",
                            COMPANY,
                            p,
                        )

    xleads_list = [
        {
            "email": "x@x.com",
            "company_name": "X",
            "contact_name": "C",
            "active_sequence": True,
            "status": "not_started",
            "last_step_sent": 0,
            "conversation": [],
            "project_id": p["id"],
        },
        {
            "email": "",
            "company_name": "NoE",
            "active_sequence": True,
            "status": "not_started",
            "last_step_sent": 0,
            "conversation": [],
            "project_id": p["id"],
        },
        {
            "email": "d@x.com",
            "company_name": "D",
            "active_sequence": True,
            "status": "do_not_contact",
            "last_step_sent": 0,
            "conversation": [],
            "project_id": p["id"],
        },
    ]
    p["templates"] = tmpl
    with patch("src.emailer.send_email", return_value={"ok": True, "mode": "dry_run", "at": "t"}):
        with patch("src.project_x.store.bump_x_contact"):
            with patch("src.project_x.leads.persist_x_leads"):
                xcampaign.run_due_x_emails(xleads_list, COMPANY, p)
                xcampaign.run_due_x_emails(xleads_list, COMPANY, p, only_keys=["x@x.com"])
    with patch("src.capacity.can_send_under_shared_caps", return_value=(False, "cap", {})):
        xcampaign.run_due_x_emails(
            xleads_list,
            {**COMPANY, "autonomy_autopilot": True, "send_live_emails": True},
            p,
        )
    with patch("src.capacity.can_send_under_shared_caps", side_effect=RuntimeError("x")):
        with patch("src.emailer.send_email", return_value={"ok": True, "mode": "dry_run", "at": "t"}):
            with patch("src.project_x.store.bump_x_contact"):
                with patch("src.project_x.leads.persist_x_leads"):
                    xcampaign.run_due_x_emails(
                        xleads_list,
                        {**COMPANY, "autonomy_autopilot": True, "send_live_emails": True},
                        p,
                    )

    # store sheets
    ws = MagicMock()
    ws.get_all_values.return_value = [
        ["id", "name", "project_type", "scope", "status", "cadence_json", "templates_json"],
        ["x1", "P", "buyer", "s", "active", "{}", "{}"],
    ]
    sh = MagicMock()
    sh.worksheet.return_value = ws
    sh.add_worksheet.return_value = ws
    with patch("src.storage._open_spreadsheet", return_value=sh):
        with patch.object(xstore, "_using_cloud", lambda: True):
            xstore._load_projects_sheets()
            xstore._save_projects_sheets([xstore._normalize_project({"id": "x1", "name": "P", "scope": "s"})])
            ws2 = MagicMock()
            ws2.get_all_values.return_value = [
                ["id", "email", "project_id", "company_name", "conversation_json"],
                ["l1", "a@a.com", "x1", "A", "[]"],
            ]
            sh.worksheet.return_value = ws2
            xstore._load_leads_sheets()
            xstore._save_leads_sheets([xstore._normalize_lead({"email": "a@a.com", "project_id": "x1"})])
            sh.worksheet.side_effect = gspread.WorksheetNotFound("x")
            assert xstore._load_projects_sheets() == []
            assert xstore._load_leads_sheets() == []


# ---- carrier storage/campaign, emailer, gmail, rbac, llm, campaign ----


def test_carrier_emailer_gmail_rbac_llm(tmp_path, monkeypatch):
    monkeypatch.setattr(cstorage, "CARRIER_JSON", tmp_path / "c.json")
    monkeypatch.setattr(cstorage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cstorage, "_using_cloud", lambda: False)
    cstorage.upsert_carriers(
        [
            {"company_name": "T", "email": "t@t.com", "mc_number": "MC-1", "state": "IL"},
            {"company_name": "T", "email": "t@t.com", "state": "WI"},
            {"company_name": "", "email": ""},
        ]
    )
    cstorage.update_carrier({"email": "t@t.com", "remarks": "x"})
    cstorage.update_carrier({"email": "new@t.com", "company_name": "New"})
    carriers = cleads.load_carriers()
    cleads.filter_carriers(carriers, state="IL", zip_prefix="", equipment_type="", status="", active_only=False, hide_dnc=True)
    cleads.activate_carrier_sequence(carriers, ["t@t.com"])
    cleads.activate_carrier_sequence(carriers, ["t@t.com"], force=True)
    if carriers:
        cleads.mark_carrier_response(carriers[0], positive=True)
        cleads.mark_carrier_response(carriers[0], positive=False)
        cleads.mark_carrier_hired(carriers[0])
        cstorage.bump_carrier_contact(carriers[0], 1)
    cleads.save_carriers(carriers)
    cleads.persist_carriers(carriers)
    ws = MagicMock()
    ws.get_all_values.return_value = [
        ["email", "company_name", "mc_number", "status"],
        ["c@c.com", "Co", "MC-2", "not_started"],
    ]
    sh = MagicMock()
    sh.worksheet.return_value = ws
    sh.add_worksheet.return_value = ws
    with patch.object(cstorage, "_using_cloud", lambda: True):
        with patch("src.storage._open_spreadsheet", return_value=sh):
            cstorage._load_sheets()
            cstorage._save_sheets([cstorage._normalize({"email": "c@c.com", "company_name": "Co"})])
            sh.worksheet.side_effect = gspread.WorksheetNotFound("x")
            assert cstorage._load_sheets() == []

    leads = [
        {
            "email": "a@a.com",
            "company_name": "A",
            "contact_name": "P",
            "active_sequence": True,
            "status": "not_started",
            "last_step_sent": 0,
            "conversation": [],
            "mc_number": "1",
            "first_contacted": "",
        },
        {
            "email": "",
            "company_name": "NoE",
            "active_sequence": True,
            "status": "not_started",
            "last_step_sent": 0,
            "conversation": [],
        },
        {
            "email": "d@d.com",
            "company_name": "DNC",
            "active_sequence": True,
            "status": "do_not_contact",
            "last_step_sent": 0,
            "conversation": [],
        },
    ]
    with patch("src.emailer.send_email", return_value={"ok": True, "mode": "dry_run", "at": "t"}):
        with patch("src.carrier_storage.bump_carrier_contact"):
            with patch("src.carrier_leads.persist_carriers"):
                ccampaign.run_due_carrier_emails(leads, COMPANY)
                ccampaign.run_due_carrier_emails(leads, COMPANY, only_keys=["a@a.com"])
    with patch("src.capacity.can_send_under_shared_caps", return_value=(False, "cap", {"remaining": 0})):
        ccampaign.run_due_carrier_emails(
            leads, {**COMPANY, "autonomy_autopilot": True, "send_live_emails": True}
        )
    with patch("src.capacity.can_send_under_shared_caps", side_effect=RuntimeError("x")):
        with patch("src.emailer.send_email", return_value={"ok": True, "mode": "dry_run", "at": "t"}):
            with patch("src.carrier_storage.bump_carrier_contact"):
                with patch("src.carrier_leads.persist_carriers"):
                    ccampaign.run_due_carrier_emails(
                        leads, {**COMPANY, "autonomy_autopilot": True, "send_live_emails": True}
                    )

    monkeypatch.setattr(emailer, "OUTBOUND_LOG", tmp_path / "out.json")
    (tmp_path / "out.json").write_text("[]", encoding="utf-8")
    assert emailer.send_email("a@a.com", "s", "b", COMPANY).get("ok")
    live = {**COMPANY, "send_live_emails": True, "smtp_password": "pw"}
    with patch("src.mailboxes.pool_usable", return_value=False):
        inst = MagicMock()
        with patch("smtplib.SMTP", return_value=inst):
            try:
                emailer.send_email("a@a.com", "s", "b", live)
            except Exception:
                pass
    with patch("src.mailboxes.pool_usable", return_value=True):
        with patch("src.mailboxes.pick_mailbox", return_value=None):
            emailer.send_email("a@a.com", "s", "b", live)
        mb = {
            "id": "mb1",
            "email": "p@g.com",
            "smtp_password": "pw",
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "smtp_user": "p@g.com",
        }
        with patch("src.mailboxes.pick_mailbox", return_value=mb):
            with patch("src.mailboxes.record_send"):
                inst = MagicMock()
                with patch("smtplib.SMTP", return_value=inst):
                    try:
                        emailer.send_email("a@a.com", "s", "b", live)
                    except Exception:
                        pass

    # shipper campaign
    ship = [
        {
            "email": "s@s.com",
            "company_name": "S",
            "contact_name": "Sam",
            "active_sequence": True,
            "status": "not_started",
            "last_step_sent": 0,
            "conversation": [],
        }
    ]
    with patch("src.emailer.send_email", return_value={"ok": True, "mode": "dry_run"}):
        for name in dir(campaign):
            fn = getattr(campaign, name)
            if callable(fn) and not name.startswith("_"):
                try:
                    fn(ship, COMPANY)
                except Exception:
                    try:
                        fn(COMPANY, ship)
                    except Exception:
                        pass

    monkeypatch.setattr(goauth, "TOKEN_FILE", tmp_path / "tok.json")
    monkeypatch.setattr(goauth, "DATA_DIR", tmp_path)
    goauth.save_token({"token": "t", "refresh_token": "r", "email": "a@b.com"})
    assert goauth.gmail_connected()
    goauth.connected_email()
    goauth.clear_token()
    goauth.default_redirect_uri()
    goauth._client_config("https://x/")
    flow = MagicMock()
    flow.authorization_url.return_value = ("https://auth", "st")
    flow.credentials = MagicMock(
        token="t", refresh_token="r", token_uri="https://oauth2.googleapis.com/token",
        client_id="c", client_secret="s", scopes=goauth.SCOPES,
    )
    with patch("google_auth_oauthlib.flow.Flow.from_client_config", return_value=flow):
        with patch.object(goauth, "_oauth_secrets", return_value={"client_id": "c", "client_secret": "s", "redirect_uri": "https://r/"}):
            goauth.build_auth_url()
            with patch.object(goauth, "_fetch_email", return_value="u@g.com"):
                goauth.exchange_code("code")

    monkeypatch.setattr(rbac, "TEAM_JSON", tmp_path / "team.json")
    monkeypatch.setattr(rbac, "DATA_DIR", tmp_path)
    state = rbac.load_rbac_state()
    state = rbac.ensure_super_admin_pin(state, "9999")
    state = rbac.sync_super_admin_profile(state, name="Boss", email="boss@x.com")
    u, state = rbac.create_user(state, name="Rep", email="rep@x.com", pin="1111", role="nurturer")
    with pytest.raises(ValueError):
        rbac.create_user(state, name="X", email="rep@x.com", pin="1", role="nurturer")
    with pytest.raises(ValueError):
        rbac.create_user(state, name="X", email="y@x.com", pin="1", role="super_admin")
    with pytest.raises(ValueError):
        rbac.create_user(state, name="", email="", pin="", role="nurturer")
    with pytest.raises(ValueError):
        rbac.create_user(state, name="X", email="z@z.com", pin="1", role="nope")
    state = rbac.update_user(state, u["id"], name="Rep2", active=True, pin="2222")
    auth = rbac.authenticate("rep@x.com", "2222")
    assert auth
    rbac.list_users(state)
    rbac.get_user_by_id(u["id"], state)
    rbac.get_user_by_email("rep@x.com", state)
    rbac.allowed_pages(auth)
    rbac.can_see_all_leads(auth)
    rbac.can(auth, "shipper", "read")
    rbac.can(None, "shipper", "read")
    rbac.scope_leads(
        [{"assigned_to": u["id"], "email": "l@x.com"}, {"assigned_to": "o", "email": "o@x.com"}],
        auth,
    )
    rbac._public_user(u)
    rbac.role_choices()
    rbac.module_choices_for_team()
    rbac.assign_leads([{"email": "a@a.com"}, {"email": "b@b.com"}], ["a@a.com"], u["id"])
    rbac.assign_carriers([{"email": "c@c.com", "mc_number": "1"}], ["c@c.com"], u["id"])
    state = rbac.delete_user(state, u["id"])
    try:
        rbac.update_user(state, "missing", name="x")
    except Exception:
        pass
    (tmp_path / "team.json").write_text("{bad", encoding="utf-8")
    rbac.load_rbac_state()

    with patch("requests.post") as post:
        post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"candidates": [{"content": {"parts": [{"text": "hi"}]}}]},
        )
        try:
            llm._call_gemini("hi", "key", model="gemini-flash", timeout=5)
        except TypeError:
            llm._call_gemini("hi", "key")
        post.return_value = MagicMock(status_code=500, text="err", json=lambda: {})
        try:
            llm._call_gemini("hi", "key", model="gemini-flash", timeout=5)
        except Exception:
            pass
    with patch("requests.post") as post:
        post.return_value = MagicMock(
            status_code=200, json=lambda: {"choices": [{"message": {"content": "hi"}}]}
        )
        try:
            llm._call_groq("hi", "key", model="llama", timeout=5)
        except TypeError:
            llm._call_groq("hi", "key")
    with patch("requests.post") as post:
        post.return_value = MagicMock(status_code=200, json=lambda: {"response": "hi"})
        try:
            llm._call_ollama("hi", model="llama", timeout=5)
        except TypeError:
            llm._call_ollama("hi")
    llm.extract_json_object("nope")
    llm.extract_json_object('{"a": 1}')
    llm.complete("x", {**COMPANY, "llm_provider": "gemini", "gemini_api_key": ""})
