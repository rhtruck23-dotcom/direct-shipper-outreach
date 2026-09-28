"""Capacity sharing, IMAP poll mocks, expanded bot intents, escalate→task."""
from __future__ import annotations

import email
from email.mime.text import MIMEText
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import src.agent_tools as tools
import src.bot as bot
import src.capacity as capacity
import src.imap_inbox as imap_inbox


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
    "send_live_emails": False,
    "autonomy_autopilot": False,
    "autonomy_daily_email_cap": 50,
    "autopilot_daily_target": 0,
    "imap_poll_enabled": False,
    "owner_notify_email": "",
}


def test_today_capacity_soft_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "OUTBOUND_LOG", tmp_path / "out.json")
    (tmp_path / "out.json").write_text("[]", encoding="utf-8")
    snap = capacity.today_capacity({**COMPANY, "autonomy_daily_email_cap": 40})
    assert snap["capacity"] == 40
    assert snap["sent"] == 0
    assert snap["remaining"] == 40
    assert snap["share_caps"] is False
    assert snap["exhausted"] is False


def test_share_caps_when_autopilot_live(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "OUTBOUND_LOG", tmp_path / "out.json")
    (tmp_path / "out.json").write_text("[]", encoding="utf-8")
    with patch("src.mailboxes.pool_usable", return_value=False):
        snap = capacity.today_capacity(
            {
                **COMPANY,
                "send_live_emails": True,
                "autonomy_autopilot": True,
                "autonomy_daily_email_cap": 100,
                "autopilot_daily_target": 25,
            }
        )
    assert snap["capacity"] == 25
    assert snap["share_caps"] is True
    assert snap["remaining"] == 25


def test_estimate_week_plan_4000():
    with patch("src.mailboxes.pool_usable", return_value=False):
        with patch.object(tools, "emails_sent_today", return_value=0):
            plan = capacity.estimate_week_plan(
                lead_count=4000,
                company={**COMPANY, "autonomy_daily_email_cap": 500},
            )
    assert plan["daily_throughput"] == 500
    assert plan["days_needed"] == 8
    assert "4000" in plan["message"] or "4,000" in plan["message"]


def test_can_send_under_shared_caps_exhausted(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "OUTBOUND_LOG", tmp_path / "out.json")
    # 2 sends already logged today
    import json
    from datetime import date

    day = date.today().isoformat()
    (tmp_path / "out.json").write_text(
        json.dumps([{"at": f"{day}T10:00:00"}, {"at": f"{day}T11:00:00"}]),
        encoding="utf-8",
    )
    with patch("src.mailboxes.pool_usable", return_value=False):
        ok, reason, snap = capacity.can_send_under_shared_caps(
            {**COMPANY, "autonomy_daily_email_cap": 2}
        )
    assert ok is False
    assert snap["exhausted"] is True
    assert "cap" in reason.lower() or "resume" in reason.lower()


def test_bot_routine_intents_no_escalate():
    lead = {"company_name": "Acme", "contact_name": "Pat", "email": "a@a.com"}
    for text, intent in [
        ("Out of office until Monday", "ooo"),
        ("Thanks!", "thanks"),
        ("Not right now — check back next quarter", "timing"),
        ("We already have a carrier, thanks", "covered"),
        ("What equipment do you haul?", "info"),
        ("Yes interested — tell me more", "positive"),
        ("Wrong person, talk to Jane", "referral"),
        ("asdf qwer zxcv", "unclear"),
    ]:
        assert bot.classify_reply(text) == intent
        d = bot.handle_reply(lead, text, COMPANY)
        assert d.intent == intent
        assert d.escalate_to_owner is False


def test_bot_escalate_still_requires_human():
    d = bot.handle_reply(
        {"company_name": "X", "email": "x@x.com"},
        "What is your rate per mile?",
        COMPANY,
    )
    assert d.intent == "escalate"
    assert d.escalate_to_owner is True
    assert d.auto_send is False


def test_escalate_creates_high_priority_task(tmp_path, monkeypatch):
    monkeypatch.setattr("src.lead_crm.TASKS_JSON", tmp_path / "tasks.json")
    monkeypatch.setattr("src.lead_crm._try_save_sheet_tasks", lambda *_a, **_k: None)
    lead = {
        "id": "L99",
        "company_name": "Hot Lead",
        "email": "h@h.com",
        "status": "emailed_1",
        "crm_status": "open",
        "sales_stage": "contacted",
        "priority": "medium",
        "notes_timeline": [],
        "remarks": "",
        "active_sequence": True,
    }
    with patch.object(tools, "notify_owner") as n:
        tr = tools.tool_escalate_to_owner(
            lead, COMPANY, reason="Asked for a rate quote", funnel="shipper"
        )
        n.assert_called_once()
    assert tr.escalated
    assert lead["priority"] == "high"
    assert lead["active_sequence"] is False
    assert tr.data.get("task_id")
    from src.lead_crm import load_tasks

    tasks = load_tasks()
    assert any(t.get("priority") == "high" and "ESCALATE" in (t.get("title") or "") for t in tasks)


def test_imap_poll_disabled_by_default():
    assert imap_inbox.imap_poll_enabled({}) is False
    assert imap_inbox.imap_poll_enabled({"imap_poll_enabled": False}) is False
    pr = imap_inbox.poll_recent_inbox(COMPANY, mailboxes=[])
    assert pr.enabled is False
    assert pr.messages == []


def test_imap_parse_and_poll_with_mock():
    msg = MIMEText("Hello from shipper — interested in capacity.")
    msg["From"] = "Shipper <ship@example.com>"
    msg["Subject"] = "Re: capacity"
    msg["Message-ID"] = "<abc@x>"
    raw = msg.as_bytes()

    parsed = imap_inbox.parse_raw_email(raw, mailbox_email="pool@g.com")
    assert parsed.from_addr == "ship@example.com"
    assert "interested" in parsed.body.lower()
    assert parsed.subject == "Re: capacity"

    class FakeIMAP:
        def __init__(self, *a, **k):
            pass

        def login(self, *a):
            return ("OK", [b""])

        def select(self, box, readonly=False):
            assert readonly is True
            return ("OK", [b"1"])

        def search(self, *_a):
            return ("OK", [b"1"])

        def fetch(self, uid, _spec):
            return ("OK", [(b"1 (RFC822)", raw)])

        def logout(self):
            return ("OK", [b""])

    mbs = [
        {
            "email": "pool@g.com",
            "smtp_password": "app-pass-xxxx",
            "enabled": True,
        }
    ]
    pr = imap_inbox.poll_recent_inbox(
        {**COMPANY, "imap_poll_enabled": True},
        mailboxes=mbs,
        imap_factory=FakeIMAP,
        force=True,
    )
    assert pr.enabled
    assert pr.mailboxes_polled == 1
    assert len(pr.messages) == 1
    assert pr.messages[0].from_addr == "ship@example.com"


def test_mailto_and_gmail_links():
    link = imap_inbox.mailto_compose_link(
        "a@b.com", subject="Hi there", body="Hello"
    )
    assert link.startswith("mailto:a@b.com?")
    assert "subject=" in link
    assert "mail.google.com" in imap_inbox.gmail_web_inbox_url("x@y.com")


def test_campaign_shared_cap_blocks(tmp_path, monkeypatch):
    from src.campaign import run_due_emails

    monkeypatch.setattr("src.leads.persist_lead_tracking", lambda *_a, **_k: None)
    leads = [
        {
            "company_name": "A",
            "email": "a@a.com",
            "status": "not_started",
            "active_sequence": True,
            "last_step_sent": 0,
        }
    ]
    company = {
        **COMPANY,
        "send_live_emails": True,
        "autonomy_autopilot": True,
        "autonomy_daily_email_cap": 1,
        "unsubscribe_note": "STOP",
    }
    with patch("src.capacity.can_send_under_shared_caps", return_value=(False, "exhausted", {"remaining": 0})):
        results = run_due_emails(leads, company)
    assert len(results) == 1
    assert results[0].get("ok") is False
    assert results[0].get("mailbox_exhausted") is True
