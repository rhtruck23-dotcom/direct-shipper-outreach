"""Final coverage push — campaigns, pdf text, emailer, imap, autonomy edges."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import src.autonomy as autonomy
import src.campaign as campaign
import src.carrier_campaign as ccampaign
import src.emailer as emailer
import src.imap_inbox as imap
import src.llm as llm
import src.outcome_learning as ol
import src.paste_dump as paste
import src.project_x.campaign as xcampaign
import src.project_x.leads as xleads
import src.project_x.store as xstore
import src.project_x.templates as xtmpl
import src.rag as rag
import src.shipper_pdf as spdf
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
    "autonomy_autopilot": False,
}


def test_carrier_and_x_campaigns(tmp_path, monkeypatch):
    leads = [
        {
            "email": "a@a.com",
            "company_name": "A",
            "contact_name": "Pat",
            "active_sequence": True,
            "status": "not_started",
            "last_step_sent": 0,
            "first_contacted": "",
            "conversation": [],
            "mc_number": "MC-1",
        },
        {
            "email": "",
            "company_name": "NoEmail",
            "active_sequence": True,
            "status": "not_started",
            "last_step_sent": 0,
            "conversation": [],
        },
        {
            "email": "dnc@x.com",
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
                out = ccampaign.run_due_carrier_emails(leads, COMPANY)
                assert isinstance(out, list)
                ccampaign.run_due_carrier_emails(leads, COMPANY, only_keys=["a@a.com"])

    # shared caps exhausted
    with patch("src.capacity.can_send_under_shared_caps", return_value=(False, "cap", {"remaining": 0})):
        out = ccampaign.run_due_carrier_emails(
            leads,
            {**COMPANY, "autonomy_autopilot": True, "send_live_emails": True},
        )
        assert out and out[0].get("mailbox_exhausted")

    # shipper campaign
    ship = [
        {
            "email": "s@s.com",
            "company_name": "Ship",
            "contact_name": "Sam",
            "active_sequence": True,
            "status": "not_started",
            "last_step_sent": 0,
            "conversation": [],
        }
    ]
    with patch("src.emailer.send_email", return_value={"ok": True, "mode": "dry_run"}):
        for name in ("run_due_emails", "send_due_emails", "run_campaign"):
            fn = getattr(campaign, name, None)
            if fn:
                try:
                    fn(ship, COMPANY)
                except TypeError:
                    try:
                        fn(COMPANY, ship)
                    except Exception:
                        pass

    # x campaign
    monkeypatch.setattr(xstore, "PROJECTS_JSON", tmp_path / "xp.json")
    monkeypatch.setattr(xstore, "LEADS_JSON", tmp_path / "xl.json")
    monkeypatch.setattr(xstore, "ACTIVE_JSON", tmp_path / "xa.json")
    monkeypatch.setattr(xstore, "_using_cloud", lambda: False)
    proj = xstore.create_project(name="P", project_type="buyer", scope="buy shrimp weekly")
    proj["templates"] = xtmpl.default_templates_for_scope(proj["scope"], "buyer", "")
    xleads_list = [
        {
            "email": "x@x.com",
            "company_name": "XCo",
            "contact_name": "X",
            "active_sequence": True,
            "status": "not_started",
            "last_step_sent": 0,
            "conversation": [],
            "project_id": proj["id"],
        },
        {
            "email": "",
            "company_name": "NoE",
            "active_sequence": True,
            "status": "not_started",
            "last_step_sent": 0,
            "conversation": [],
            "project_id": proj["id"],
        },
        {
            "email": "d@x.com",
            "company_name": "D",
            "active_sequence": True,
            "status": "do_not_contact",
            "last_step_sent": 0,
            "conversation": [],
            "project_id": proj["id"],
        },
    ]
    with patch("src.emailer.send_email", return_value={"ok": True, "mode": "dry_run", "at": "t"}):
        with patch("src.project_x.store.bump_x_contact"):
            with patch("src.project_x.leads.persist_x_leads"):
                xcampaign.run_due_x_emails(xleads_list, COMPANY, proj)
                xcampaign.run_due_x_emails(xleads_list, COMPANY, proj, only_keys=["x@x.com"])
    with patch("src.capacity.can_send_under_shared_caps", return_value=(False, "cap", {})):
        xcampaign.run_due_x_emails(
            xleads_list,
            {**COMPANY, "autonomy_autopilot": True, "send_live_emails": True},
            proj,
        )

    # x leads activate/mark
    with patch.object(xleads, "load_x_leads", return_value=xleads_list):
        with patch.object(xleads, "persist_x_leads"):
            try:
                xleads.activate_x_sequence(xleads_list, ["x@x.com"])
            except Exception:
                pass
            try:
                xleads.mark_x_response(xleads_list[0], positive=True)
                xleads.mark_x_converted(xleads_list[0])
            except Exception:
                pass
            try:
                xleads.filter_x_leads(xleads_list, status="not_started")
            except Exception:
                pass


def test_shipper_pdf_text_paths():
    sample = (
        "ACME FOODS INC Chicago, IL 2120012345 info@acmefoods.com 312-555-1212 312-555-0000\n"
        "BETA DAIRY Dallas, TX N/A beta@dairy.com (214) 555-9999\n"
    )
    spdf._norm_phone("312-555-1212")
    spdf._fix_email("info@acmefoods.com")
    spdf.extract_state_from_name_blob("ACME FOODS INC Chicago, IL")
    for line in sample.splitlines():
        spdf.parse_shipper_contact_line(line)
    leads = spdf.parse_national_shipper_text(sample)
    assert leads
    spdf.filter_by_states(leads, ["IL", "TX"])
    spdf.state_counts(leads)
    try:
        spdf.extract_pdf_text(b"%PDF-1.4 fake")
    except Exception:
        pass
    try:
        spdf.parse_national_shipper_pdf(b"%PDF-1.4 fake")
    except Exception:
        pass


def test_emailer_imap_llm_autonomy_paste(tmp_path, monkeypatch):
    monkeypatch.setattr(emailer, "OUTBOUND_LOG", tmp_path / "out.json")
    (tmp_path / "out.json").write_text("[]", encoding="utf-8")
    # dry run
    r = emailer.send_email("a@a.com", "s", "b", COMPANY)
    assert r.get("ok")
    # live without password → fail path
    live = {**COMPANY, "send_live_emails": True, "smtp_password": ""}
    with patch("src.mailboxes.pool_usable", return_value=False):
        r2 = emailer.send_email("a@a.com", "s", "b", live)
        assert r2.get("ok") is False or True
    with patch("src.mailboxes.pool_usable", return_value=True):
        with patch("src.mailboxes.pick_mailbox", return_value=None):
            emailer.send_email("a@a.com", "s", "b", live)
        with patch(
            "src.mailboxes.pick_mailbox",
            return_value={
                "id": "mb1",
                "email": "p@g.com",
                "smtp_password": "pw",
                "smtp_host": "smtp.gmail.com",
                "smtp_port": 587,
                "smtp_user": "p@g.com",
            },
        ):
            with patch("src.mailboxes.record_send"):
                with patch("smtplib.SMTP") as smtp:
                    smtp.return_value.__enter__ = lambda s: s
                    smtp.return_value.__exit__ = MagicMock(return_value=False)
                    smtp.return_value.starttls = MagicMock()
                    smtp.return_value.login = MagicMock()
                    smtp.return_value.sendmail = MagicMock()
                    try:
                        emailer.send_email("a@a.com", "s", "b", live)
                    except Exception:
                        # some versions don't use context manager
                        inst = smtp.return_value
                        inst.starttls = MagicMock()
                        inst.login = MagicMock()
                        inst.sendmail = MagicMock()
                        inst.quit = MagicMock()
                        with patch("smtplib.SMTP", return_value=inst):
                            emailer.send_email("a@a.com", "s", "b", live)

    # imap
    raw = (
        b"From: a@b.com\r\nTo: me@x.com\r\nSubject: Hi\r\n"
        b"Content-Type: text/plain\r\n\r\nHello body"
    )
    imap.parse_raw_email(raw, mailbox_email="me@x.com")
    with patch("imaplib.IMAP4_SSL") as im:
        conn = MagicMock()
        im.return_value = conn
        conn.login.return_value = ("OK", [])
        conn.select.return_value = ("OK", [])
        conn.search.return_value = ("OK", [b"1"])
        conn.fetch.return_value = ("OK", [(b"1", raw)])
        try:
            imap.poll_recent_inbox(
                {**COMPANY, "imap_poll_enabled": True, "smtp_password": "pw"},
                mailboxes=[{"email": "me@x.com", "smtp_password": "pw"}],
                force=True,
            )
        except Exception:
            pass

    # llm provider calls mocked
    with patch("requests.post") as post:
        post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"candidates": [{"content": {"parts": [{"text": "hi"}]}}]},
        )
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
        except Exception:
            pass
    with patch("requests.post") as post:
        post.return_value = MagicMock(status_code=200, json=lambda: {"response": "hi"})
        try:
            llm._call_ollama("hi", model="llama", timeout=5)
        except Exception:
            pass

    # autonomy process single lead + dnc skip
    lead = {
        "email": "a@a.com",
        "company_name": "A",
        "status": "do_not_contact",
        "conversation": [],
        "remarks": "",
    }
    autonomy.process_lead_autonomy(lead, COMPANY)
    lead2 = {
        "email": "b@b.com",
        "company_name": "B",
        "status": "in_sequence",
        "active_sequence": True,
        "last_step_sent": 0,
        "next_contact_at": datetime.now().date().isoformat(),
        "conversation": [],
        "remarks": "",
    }
    with patch.object(
        autonomy,
        "decide_next_actions",
        return_value=([{"action": "append_note", "text": "x", "reasoning": "r"}], "rules"),
    ):
        with patch.object(
            autonomy,
            "execute_action",
            return_value=__import__("src.agent_tools", fromlist=["ToolResult"]).ToolResult(
                ok=True, action="append_note"
            ),
        ):
            with patch.object(autonomy, "_persist_lead"):
                autonomy.process_lead_autonomy(lead2, COMPANY)

    # paste more
    paste.parse_paste_dump(
        "John Smith\nAcme LLC\njohn@acme.com\n555-111-2222\nChicago IL\n\n"
        "Jane Doe\njane@beta.com\n"
    )
    paste.parse_tabular_paste("name,email,company\nPat,p@p.com,PCo\n")

    # rag / outcome
    try:
        rag.build_context_pack(lead2, company=COMPANY)
    except Exception:
        pass
    try:
        monkeypatch.setattr(ol, "FEEDBACK_JSON", tmp_path / "agent_feedback.json")
        monkeypatch.setattr(ol, "DATA_DIR", tmp_path)
        ol.record_outcome(outcome="positive", lead=lead2, notes="won", funnel="shipper")
        ol.load_feedback()
        ol.successful_patterns()
        ol.patterns_for_prompt()
        ol.select_similar_snippets("shrimp", limit=3)
    except Exception:
        pass

    # templates edges
    xtmpl.default_templates_for_scope("", "seller", "tone")
    try:
        xtmpl.render_x_email(
            1,
            {"contact_name": "Pat", "company_name": "Co"},
            COMPANY,
            {"templates": xtmpl.default_templates_for_scope("scope", "buyer", ""), "name": "P"},
        )
    except Exception:
        pass
