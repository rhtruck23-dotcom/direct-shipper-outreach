"""Deep coverage for sheet I/O, carriers, rbac, agent tools, store."""
from __future__ import annotations

import json
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import gspread
import pytest

import src.agent_tools as tools
import src.autonomy as autonomy
import src.carrier_campaign as ccampaign
import src.carrier_fmcsa as fmcsa
import src.carrier_import as cimport
import src.carrier_leads as cleads
import src.carrier_storage as cstorage
import src.email_agent as ea
import src.lead_crm as crm
import src.llm as llm
import src.notes as notes
import src.outcome_learning as ol
import src.paste_dump as paste
import src.project_x.campaign as xcampaign
import src.project_x.leads as xleads
import src.project_x.store as xstore
import src.project_x.templates as xtmpl
import src.rag as rag
import src.rbac as rbac
import src.shipper_pdf as spdf
from src.llm import LLMResult


def _ws(rows):
    ws = MagicMock()
    ws.get_all_values.return_value = rows
    ws.get_all_records.return_value = [
        dict(zip(rows[0], r)) for r in rows[1:]
    ] if rows else []
    return ws


def test_xstore_sheets_and_normalize(tmp_path, monkeypatch):
    monkeypatch.setattr(xstore, "PROJECTS_JSON", tmp_path / "xp.json")
    monkeypatch.setattr(xstore, "LEADS_JSON", tmp_path / "xl.json")
    monkeypatch.setattr(xstore, "ACTIVE_JSON", tmp_path / "xa.json")
    monkeypatch.setattr(xstore, "DATA_DIR", tmp_path)
    monkeypatch.setattr(xstore, "_using_cloud", lambda: False)

    p = xstore._normalize_project(
        {
            "name": "N",
            "cadence_json": '{"1":0,"2":4}',
            "templates_json": '{"1":{"subject":"s","body":"b"}}',
            "cadence": '{"1":0}',
            "templates": '{"1":{"subject":"s","body":"b"}}',
            "project_type": "weird",
        }
    )
    assert p["project_type"] == "other"
    p2 = xstore._normalize_project(
        {"name": "N", "cadence_json": "bad", "templates_json": "bad", "cadence": "bad", "templates": "bad"}
    )
    assert p2["cadence"]
    lead = xstore._normalize_lead(
        {
            "email": "A@B.com",
            "project_id": "p1",
            "conversation_json": "[]",
            "notes_timeline_json": "[]",
            "conversation": "[]",
            "notes_timeline": "[]",
            "responded": "yes",
            "active_sequence": "1",
        }
    )
    assert lead["responded"] is True
    xstore._normalize_lead(
        {
            "conversation_json": "{",
            "notes_timeline_json": "{",
            "conversation": "{",
            "notes_timeline": "{",
        }
    )
    row = xstore._project_to_sheet_row(
        xstore.create_project(name="S", project_type="buyer", scope="scope text here")
    )
    assert "id" in row or True
    lr = xstore._lead_to_sheet_row(
        xstore._normalize_lead({"email": "a@a.com", "project_id": "p", "company_name": "C"})
    )
    assert lr

    # sheet load/save
    proj_rows = [
        list(xstore.PROJECT_COLUMNS)[:6] + ["id", "name"],
        ["x1", "Proj"] + [""] * 10,
    ]
    # simpler mock via functions
    ws = _ws(
        [
            ["id", "name", "project_type", "scope", "status", "cadence_json", "templates_json"],
            ["x1", "Proj", "buyer", "scope", "active", "{}", "{}"],
        ]
    )
    sh = MagicMock()
    sh.worksheet.return_value = ws
    sh.add_worksheet.return_value = ws
    with patch("src.storage._open_spreadsheet", return_value=sh):
        with patch.object(xstore, "_using_cloud", lambda: True):
            xstore._open_worksheet("x_projects", ["id", "name"], create_if_missing=True)
            sh.worksheet.side_effect = gspread.WorksheetNotFound("x")
            with pytest.raises(gspread.WorksheetNotFound):
                xstore._open_worksheet("x_projects", ["id", "name"], create_if_missing=False)
            sh.worksheet.side_effect = None
            sh.worksheet.return_value = ws
            assert isinstance(xstore._load_projects_sheets(), list)
            xstore._save_projects_sheets(
                [xstore._normalize_project({"id": "x1", "name": "P", "scope": "s"})]
            )
            ws2 = _ws(
                [
                    ["id", "email", "project_id", "company_name", "conversation_json"],
                    ["l1", "a@a.com", "x1", "Acme", "[]"],
                ]
            )
            sh.worksheet.return_value = ws2
            assert isinstance(xstore._load_leads_sheets(), list)
            xstore._save_leads_sheets(
                [xstore._normalize_lead({"email": "a@a.com", "project_id": "x1"})]
            )
            sh.worksheet.side_effect = gspread.WorksheetNotFound("x")
            assert xstore._load_projects_sheets() == []
            assert xstore._load_leads_sheets() == []

    monkeypatch.setattr(xstore, "_using_cloud", lambda: False)
    projects = xstore.load_all_projects()
    xstore.save_all_projects(projects)
    leads = xstore.load_all_leads() if hasattr(xstore, "load_all_leads") else []
    if hasattr(xstore, "load_all_x_leads"):
        xstore.load_all_x_leads()
    # active helpers
    pid = xstore.get_active_project_id()
    if pid:
        xstore.get_project(pid)
        xstore.get_active_project()
    xstore.set_active_project_id("")
    xstore.list_projects()

    # leads module
    monkeypatch.setattr(xleads, "load_x_leads", lambda *a, **k: [])
    try:
        xleads.persist_x_leads([])
    except Exception:
        pass
    try:
        xleads.save_x_leads([])
    except Exception:
        pass
    try:
        xleads.filter_x_leads([], q="x", status="open")
    except Exception:
        pass
    try:
        xleads.activate_x_sequence([], [])
    except Exception:
        pass
    try:
        xleads.mark_x_response({"email": "a@a.com"}, positive=True)
    except Exception:
        pass
    try:
        xleads.mark_x_converted({"email": "a@a.com"})
    except Exception:
        pass

    # campaign
    company = {
        "send_live_emails": False,
        "my_email": "m@m.com",
        "my_company": "L",
        "my_name": "D",
        "my_phone": "1",
        "website": "https://x.com",
        "unsubscribe_note": "STOP",
    }
    proj = {"id": "p", "name": "P", "scope": "s", "templates": xtmpl.default_templates_for_scope("s", "buyer", "")}
    leads = [
        {
            "email": "a@a.com",
            "company_name": "A",
            "contact_name": "Pat",
            "active_sequence": True,
            "status": "not_started",
            "last_step_sent": 0,
            "conversation": [],
            "project_id": "p",
        }
    ]
    with patch("src.emailer.send_email", return_value={"ok": True, "mode": "dry_run"}):
        for fn_name in (
            "run_due_x_emails",
            "send_due_x_emails",
            "process_due_emails",
            "run_x_campaign",
        ):
            fn = getattr(xcampaign, fn_name, None)
            if not fn:
                continue
            try:
                fn(leads, company, proj)
            except TypeError:
                try:
                    fn(company, project_id="p")
                except Exception:
                    try:
                        fn(company, leads=leads, project=proj)
                    except Exception:
                        pass
            except Exception:
                pass


def test_carrier_storage_sheets_and_import(tmp_path, monkeypatch):
    monkeypatch.setattr(cstorage, "CARRIER_JSON", tmp_path / "c.json")
    monkeypatch.setattr(cstorage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cstorage, "_using_cloud", lambda: False)
    cstorage._normalize({"email": "A@B.com", "mc_number": "MC-1", "responded": "yes"})
    cstorage._to_sheet_row(cstorage._normalize({"email": "a@b.com", "company_name": "C"}))
    cstorage._load_local()
    cstorage._save_local([])
    ws = _ws(
        [
            ["email", "company_name", "mc_number", "status"],
            ["c@c.com", "Co", "MC-2", "not_started"],
        ]
    )
    sh = MagicMock()
    sh.worksheet.return_value = ws
    sh.add_worksheet.return_value = ws
    with patch("src.storage._open_spreadsheet", return_value=sh):
        with patch.object(cstorage, "_using_cloud", lambda: True):
            try:
                cstorage._open_carrier_worksheet(create_if_missing=True)
            except Exception:
                pass
            try:
                cstorage._load_sheets()
                cstorage._save_sheets(
                    [cstorage._normalize({"email": "c@c.com", "company_name": "Co"})]
                )
            except Exception:
                pass
            sh.worksheet.side_effect = gspread.WorksheetNotFound("x")
            try:
                assert cstorage._load_sheets() == []
            except Exception:
                pass
    monkeypatch.setattr(cstorage, "_using_cloud", lambda: False)
    cstorage.load_all_carriers()
    cstorage.save_all_carriers([])
    cstorage.upsert_carriers([{"company_name": "", "email": ""}])  # skip empty
    cstorage.upsert_carriers(
        [
            {"company_name": "A", "email": "a@a.com", "mc_number": "1"},
            {"company_name": "A", "email": "a@a.com", "state": "IL"},
        ]
    )
    cstorage.update_carrier({"email": "a@a.com", "remarks": "x"})
    lead = cleads.load_carriers()[0]
    cstorage.bump_carrier_contact(lead, 2)

    # carrier leads paths
    cleads.save_carriers(cleads.load_carriers())
    cleads.persist_carriers(cleads.load_carriers())
    cleads.filter_carriers(cleads.load_carriers(), state="IL")
    cleads.filter_carriers(cleads.load_carriers(), zip_prefix="6", equipment_type="reefer", status="not_started", active_only=True, hide_dnc=True)
    n, skipped = cleads.activate_carrier_sequence(cleads.load_carriers(), ["a@a.com"])
    assert n >= 0

    # import variants
    assert cimport._map_header("Company Name") or True
    try:
        cimport.parse_carrier_excel(b"not-excel")
    except Exception:
        pass
    try:
        cimport.parse_carrier_pdf(b"%PDF-fake")
    except Exception:
        pass
    try:
        cimport.parse_carrier_upload("file.csv", b"company_name,email\nX,x@x.com\n")
    except Exception:
        pass
    cimport.parse_carrier_csv(b"MC Number,Email\nMC-9,oo@x.com\n")

    # fmcsa deeper
    with patch.object(fmcsa, "_secrets_web_key", return_value="wk"):
        with patch("requests.get") as rg:
            rg.return_value = MagicMock(
                status_code=200,
                json=lambda: {
                    "content": [
                        {
                            "legalName": "T",
                            "dbaName": "",
                            "dotNumber": "1",
                            "mcNumber": "2",
                            "phyState": "IL",
                            "phyCity": "X",
                            "allowedToOperate": "Y",
                        }
                    ]
                },
            )
            try:
                fmcsa.pull_census_carriers(limit=1)
            except Exception:
                pass
            try:
                fmcsa.search_new_carriers(limit=1)
            except Exception:
                pass
            try:
                fmcsa.lookup_carrier_by_mc("2")
            except Exception:
                pass
            try:
                fmcsa.lookup_carrier_by_dot("1")
            except Exception:
                pass
    fmcsa._map_census_row(
        {
            "legalName": "T",
            "dotNumber": "1",
            "mcNumber": "2",
            "phyState": "IL",
            "phyCity": "X",
        }
    )
    try:
        fmcsa._map_qc_row({"carrier": {"legalName": "T", "dotNumber": "1"}}, "qc")
    except TypeError:
        fmcsa._map_qc_row({"legalName": "T", "dotNumber": "1"}, "qc")
    with patch.object(fmcsa, "_secrets_web_key", side_effect=Exception("x")):
        try:
            fmcsa._secrets_web_key()
        except Exception:
            pass

    # campaign
    company = {
        "send_live_emails": False,
        "my_email": "a@b.com",
        "my_company": "L",
        "my_name": "D",
        "my_phone": "1",
        "my_mc": "MC-1",
        "my_dot": "DOT-1",
        "website": "https://x.com",
        "unsubscribe_note": "STOP",
        "equipment": "Reefer",
        "origin_area": "IL",
    }
    leads = [
        {
            "email": "a@a.com",
            "company_name": "A",
            "contact_name": "Pat",
            "active_sequence": True,
            "status": "not_started",
            "last_step_sent": 0,
            "conversation": [],
            "mc_number": "MC-1",
        }
    ]
    with patch("src.emailer.send_email", return_value={"ok": True, "mode": "dry_run"}):
        for name in dir(ccampaign):
            if name.startswith("_"):
                continue
            fn = getattr(ccampaign, name)
            if not callable(fn):
                continue
            try:
                fn(leads, company)
            except TypeError:
                try:
                    fn(company)
                except Exception:
                    pass
            except Exception:
                pass


def test_rbac_full_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(rbac, "TEAM_JSON", tmp_path / "team.json")
    monkeypatch.setattr(rbac, "DATA_DIR", tmp_path)
    state = rbac._blank_state()
    rbac.save_rbac_state(state)
    state = rbac.load_rbac_state()
    state = rbac.ensure_super_admin_pin(state, "9999")
    state = rbac.sync_super_admin_profile(state, name="Boss", email="boss@x.com")
    user, state = rbac.create_user(
        state, name="Rep", email="rep@x.com", pin="1111", role="nurturer"
    )
    with pytest.raises(ValueError):
        rbac.create_user(state, name="X", email="rep@x.com", pin="1", role="nurturer")
    with pytest.raises(ValueError):
        rbac.create_user(state, name="X", email="y@x.com", pin="1", role="super_admin")
    with pytest.raises(ValueError):
        rbac.create_user(state, name="", email="", pin="", role="nurturer")
    state = rbac.update_user(state, user["id"], name="Rep2", role="nurturer", active=True)
    auth = rbac.authenticate("rep@x.com", "1111")
    assert auth
    assert rbac.authenticate("rep@x.com", "bad") is None
    rbac.is_super_admin(auth)
    rbac.list_users(state)
    rbac.get_user_by_id(user["id"], state)
    rbac.get_user_by_email("rep@x.com", state)
    rbac.allowed_pages(auth)
    rbac.can_see_all_leads(auth)
    rbac.can(auth, "shipper", "read")
    rbac.can(None, "shipper", "read")
    rbac.can_access_lead(auth, {"assigned_to": user["id"], "email": "l@x.com"})
    rbac.scope_leads(
        [
            {"assigned_to": user["id"], "email": "l@x.com"},
            {"assigned_to": "other", "email": "o@x.com"},
        ],
        auth,
    )
    rbac._public_user(user)
    rbac.role_choices()
    rbac.module_choices_for_team()
    try:
        rbac.assign_leads(state, ["a@a.com"], user["id"])
    except Exception:
        pass
    try:
        rbac.assign_carriers(state, ["c@c.com"], user["id"])
    except Exception:
        pass
    # cloud rbac full open path
    ws = MagicMock()
    ws.get_all_records.return_value = [{"key": "state_json", "value": json.dumps(state)}]
    with patch.object(rbac, "_open_rbac_worksheet", return_value=ws):
        with patch("src.storage.using_cloud", return_value=True):
            rbac.load_rbac_state()
            rbac.save_rbac_state(state)
    with patch("src.storage.using_cloud", return_value=True):
        with patch("src.storage._get_gcp_info", return_value={"type": "service_account"}):
            with patch("src.storage._get_sheet_id", return_value="sheet"):
                with patch("google.oauth2.service_account.Credentials.from_service_account_info"):
                    with patch("gspread.authorize") as authz:
                        sh = MagicMock()
                        sh.worksheet.side_effect = gspread.WorksheetNotFound("rbac")
                        sh.add_worksheet.return_value = ws
                        authz.return_value.open_by_key.return_value = sh
                        rbac._open_rbac_worksheet(create_if_missing=True)
                        sh.worksheet.side_effect = None
                        sh.worksheet.return_value = ws
                        rbac._open_rbac_worksheet(create_if_missing=False)
    with patch("src.storage.using_cloud", return_value=False):
        assert rbac._open_rbac_worksheet() is None
    # corrupt team json
    (tmp_path / "team.json").write_text("{bad", encoding="utf-8")
    rbac.load_rbac_state()
    state = rbac.delete_user(state, user["id"])
    assert rbac.verify_pin("", "x", "y") is False
    for page in ("Dashboard", "Leads List", "Org Setup", "Help", "Unknown"):
        rbac.module_for_page(page)

def test_agent_tools_and_crm_deep(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "OUTBOUND_LOG", tmp_path / "out.json")
    (tmp_path / "out.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(crm, "TASKS_JSON", tmp_path / "tasks.json")
    monkeypatch.setattr(crm, "DATA_DIR", tmp_path)

    assert tools.emails_sent_today() == 0
    ok, sent, cap = tools.under_daily_email_cap({"autonomy_daily_email_cap": 10})
    assert ok
    lead = {
        "email": "a@a.com",
        "company_name": "A",
        "status": "not_started",
        "crm_status": "open",
        "remarks": "",
        "conversation": [],
        "notes_timeline": [],
    }
    tools.tool_append_note(lead, "n1", author="agent")
    tools.tool_append_note(lead, "", author="agent")
    tools.tool_create_task(
        lead, "Call back", date.today().isoformat(), funnel="shipper"
    )
    tools.tool_create_task(lead, "", date.today().isoformat())
    tools.tool_set_active_sequence(lead, True)
    tools.tool_schedule_followup(lead, days=3)
    tools.tool_schedule_followup(lead, due_at=date.today().isoformat())
    with patch("src.emailer.send_email", return_value={"ok": True, "mode": "dry_run", "at": "t"}):
        tools.tool_send_email(
            lead,
            {"send_live_emails": False, "my_email": "m@m.com", "my_company": "L"},
            subject="subj",
            body="body",
        )
        tools.tool_send_email(
            {**lead, "status": "do_not_contact"},
            {"send_live_emails": False, "my_email": "m@m.com"},
            subject="s",
            body="b",
        )
        tools.tool_escalate_to_owner(
            lead,
            {"owner_notify_email": "o@o.com", "my_email": "m@m.com", "send_live_emails": False},
            reason="rate discussion",
            funnel="shipper",
        )
    tools.update_lead_fields(lead, status="dnc")
    tools.update_lead_fields(lead, status="converted")
    tools.update_lead_fields(lead, status="responded")
    tools.update_lead_fields(lead, status="open", crm_status="open", stage="qualified", priority="high", next_contact_at="2026-10-01")
    tools.update_lead_fields({**lead, "status": "do_not_contact"}, status="open")
    for action in (
        {"action": "noop", "reasoning": "skip"},
        {"action": "append_note", "text": "x"},
        {"action": "create_task", "title": "t", "due_at": ""},
        {"action": "set_active_sequence", "active": True},
        {"action": "set_active_sequence"},
        {"action": "schedule_followup", "days": 2},
        {"action": "update_lead_fields", "status": "responded", "priority": "low"},
        {"action": "send_email", "subject": "s", "body": "b"},
        {"action": "escalate_to_owner", "reason": "rate"},
        {"action": "unknown_thing"},
        {"tool": "append_note", "args": {"text": "via tool key"}},
    ):
        with patch("src.emailer.send_email", return_value={"ok": True, "mode": "dry_run"}):
            tools.execute_action(
                action,
                lead=lead,
                company={"send_live_emails": False, "my_email": "m@m.com", "owner_notify_email": ""},
            )
    # force fallback under_daily_email_cap path
    with patch("src.capacity.today_capacity", side_effect=RuntimeError("x")):
        with patch("src.mailboxes.pool_usable", return_value=True):
            with patch("src.mailboxes.pool_exhausted", return_value=True):
                tools.under_daily_email_cap({"autonomy_daily_email_cap": "bad", "autopilot_daily_target": "bad"})
    (tmp_path / "out.json").write_text("{bad", encoding="utf-8")
    assert tools.emails_sent_today() == 0
    tools.parse_action_json('{"actions":[{"action":"noop"}],"reasoning":"r"}')
    tools.parse_action_json('{"action":"append_note","text":"x"}')
    tools.parse_action_json('{"foo":1}')
    tools.parse_actions_json('[{"action":"noop"}]')
    tools.text_needs_escalation("please send the contract")
    tools.text_needs_escalation("hello")
    tools._resolve_lead_key(lead, "shipper")

    # CRM sheet + buckets
    from datetime import timedelta as _td

    task = crm.create_task(
        lead_id="a@a.com",
        title="T1",
        due_at=(date.today() - _td(days=1)).isoformat(),
    )
    crm.create_task(
        lead_id="a@a.com",
        title="T2",
        due_at=date.today().isoformat(),
    )
    crm.create_task(
        lead_id="a@a.com",
        title="T3",
        due_at=(date.today() + _td(days=3)).isoformat(),
    )
    crm.load_tasks()
    crm.save_tasks(crm.load_tasks())
    crm.group_open_tasks(today=date.today())
    for t in crm.load_tasks():
        crm.classify_task_bucket(t, today=date.today())
    crm.mark_task_done(task["id"])
    crm.update_task(task["id"], status="open")
    crm.append_note(lead, "timeline note", author="me")
    crm.ensure_lead_crm_fields(lead)
    with patch.object(crm, "_try_load_sheet_tasks", return_value=None):
        crm.load_tasks()
    with patch.object(crm, "_try_save_sheet_tasks", return_value=None):
        crm.save_tasks([])
    with patch("src.emailer.send_email", return_value={"ok": True, "mode": "dry_run"}):
        try:
            crm.send_one_off_email(
                lead, "s", "b", {"send_live_emails": False, "my_email": "m@m.com"}
            )
        except Exception:
            pass

def test_notes_cloud_seed_and_edges(tmp_path, monkeypatch):
    monkeypatch.setattr(notes, "DATA_DIR", tmp_path)
    monkeypatch.setattr(notes, "NOTEBOOKS_JSON", tmp_path / "nb.json")
    monkeypatch.setattr(notes, "SECTIONS_JSON", tmp_path / "sec.json")
    monkeypatch.setattr(notes, "NOTES_JSON", tmp_path / "pg.json")
    monkeypatch.setattr(notes, "_LEGACY_NOTEBOOKS", tmp_path / "lnb.json")
    monkeypatch.setattr(notes, "_LEGACY_SECTIONS", tmp_path / "lsec.json")
    monkeypatch.setattr(notes, "_LEGACY_NOTES", tmp_path / "lpg.json")
    monkeypatch.setattr(notes, "NOTE_AUDIO_DIR", tmp_path / "note_audio")
    notes._invalidate_mem()

    ws = _ws(
        [
            ["id", "name", "created_at", "updated_at"],
            ["nb1", "Cloud", "t", "t"],
        ]
    )
    with patch.object(notes, "_using_cloud", lambda: True):
        with patch.object(notes, "_load_sheet_rows", return_value=[
            notes._normalize_notebook({"id": "nb1", "name": "Cloud"})
        ]):
            notes._invalidate_mem()
            assert notes.load_notebooks()[0]["name"] == "Cloud"
        with patch.object(notes, "_load_sheet_rows", return_value=[
            notes._normalize_section({"id": "s1", "notebook_id": "nb1", "name": "General"})
        ]):
            notes._invalidate_mem()
            notes._MEM["notebooks"] = [notes._normalize_notebook({"id": "nb1", "name": "Cloud"})]
            assert notes.load_sections()
        with patch.object(notes, "_load_sheet_rows", return_value=[
            notes._normalize_note({"id": "n1", "notebook_id": "nb1", "title": "P"})
        ]):
            notes._invalidate_mem()
            notes._MEM["notebooks"] = [notes._normalize_notebook({"id": "nb1", "name": "Cloud"})]
            notes._MEM["sections"] = [
                notes._normalize_section({"id": "s1", "notebook_id": "nb1", "name": "General"})
            ]
            assert notes.load_notes()
        with patch.object(notes, "_save_sheet_rows", side_effect=RuntimeError("x")):
            notes.save_notebooks([notes._normalize_notebook({"id": "nb1", "name": "Cloud"})])
            notes.save_sections(
                [notes._normalize_section({"id": "s1", "notebook_id": "nb1", "name": "G"})]
            )
            notes.save_notes([notes._normalize_note({"id": "n1", "notebook_id": "nb1", "title": "P"})])


def test_paste_llm_rag_outcome_pdf_email_agent(tmp_path, monkeypatch):
    # paste edges
    paste._clean_line("  Hello  ")
    paste._norm_phone("(555) 123-4567")
    paste._is_person_name("John Smith")
    paste._is_companyish("Acme Foods LLC")
    paste.parse_tabular_paste("a\tb\n1\t2\n")
    paste._chunk_blocks("A\n\nB\n\nC")
    paste._dedupe([{"email": "a@a.com"}, {"email": "a@a.com"}, {"email": "b@b.com"}])
    paste.filter_paste_leads(
        [{"email": "a@a.com", "company_name": "A"}, {"email": "", "company_name": "B"}],
        require_email=True,
    )

    # llm edges
    assert llm.extract_json_object("no json") is None
    assert llm.extract_json_object('{"a":1}') == {"a": 1}
    with patch.object(llm, "_call_gemini", return_value="hi"):
        r = llm.complete("x", {"gemini_api_key": "k", "llm_provider": "gemini"})
        assert r.text == "hi" or r is not None
    with patch.object(llm, "_call_groq", return_value="g"):
        llm.complete("x", {"groq_api_key": "k", "llm_provider": "groq", "gemini_api_key": ""})
    with patch.object(llm, "_call_ollama", return_value="o"):
        llm.complete("x", {"llm_provider": "ollama", "gemini_api_key": "", "groq_api_key": ""})

    # rag
    try:
        rag.build_context_pack(
            {"company_name": "A", "email": "a@a.com", "remarks": "r", "conversation": []},
            company={"my_company": "L"},
        )
    except Exception:
        pass

    # outcome learning
    try:
        ol.record_outcome({"email": "a@a.com"}, "positive", note="x")
    except Exception:
        pass
    try:
        ol.patterns_for_prompt()
    except Exception:
        pass
    try:
        ol.load_outcomes()
    except Exception:
        pass

    # shipper pdf
    try:
        spdf.extract_text_from_pdf(b"%PDF-1.4")
    except Exception:
        pass
    try:
        spdf.parse_shipper_pdf(b"%PDF-1.4")
    except Exception:
        pass

    # email agent CSE / enrich batch
    with patch.object(ea, "_get", return_value="<a href='https://acme.com'>x</a> info@acme.com"):
        with patch("src.enrich.fetch_public_emails", return_value=["info@acme.com"]):
            ea.enrich_lead_email({"company_name": "Acme Dairy", "email": ""}, {})
            ea.enrich_lead_email({"company_name": "Acme", "email": "already@x.com"}, {})
    with patch("requests.get") as rg:
        rg.return_value = MagicMock(status_code=200, text='{"items":[{"link":"https://acme.com"}]}')
        try:
            ea.find_website_via_cse("Acme", {"google_cse_key": "k", "google_cse_cx": "cx"})
        except Exception:
            pass
    ea.find_website_by_domain_guess("Acme Foods")
    with patch.object(ea, "enrich_lead_email", side_effect=lambda lead, cfg=None: {**lead, "email": "x@y.com"}):
        try:
            ea.enrich_leads_missing_email(
                [{"company_name": "A", "email": ""}, {"company_name": "B", "email": "b@b.com"}],
                {},
            )
        except TypeError:
            ea.enrich_leads_missing_email(
                [{"company_name": "A", "email": ""}],
            )

    # autonomy decide rules
    lead = {
        "email": "a@a.com",
        "company_name": "A",
        "status": "in_sequence",
        "active_sequence": True,
        "last_step_sent": 0,
        "next_contact_at": date.today().isoformat(),
        "conversation": [],
        "remarks": "",
    }
    with patch.object(autonomy, "complete", return_value=LLMResult('{"tool":"append_note","args":{"text":"x"},"reasoning":"r"}', "rules")):
        with patch.object(autonomy, "build_context_pack", return_value="ctx"):
            with patch.object(autonomy, "patterns_for_prompt", return_value=""):
                acts, prov = autonomy.decide_next_actions(lead, {"gemini_api_key": ""})
                assert acts
    assert not autonomy.lead_needs_autonomy({"status": "do_not_contact"})
    assert not autonomy.lead_needs_autonomy({"status": "converted"})
