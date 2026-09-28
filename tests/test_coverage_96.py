"""Extra coverage for capacity, imap, llm failover edges, emailer pool messages."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import src.agent_tools as tools
import src.capacity as capacity
import src.imap_inbox as imap
import src.llm as llm
from src.emailer import send_email


def test_capacity_with_pool(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "OUTBOUND_LOG", tmp_path / "o.json")
    (tmp_path / "o.json").write_text("[]", encoding="utf-8")
    usage = [
        {
            "id": "mb1",
            "email": "a@g.com",
            "enabled": True,
            "has_password": True,
            "sent": 50,
            "cap": 200,
            "remaining": 150,
        },
        {
            "id": "mb2",
            "email": "b@g.com",
            "enabled": True,
            "has_password": True,
            "sent": 200,
            "cap": 200,
            "remaining": 0,
        },
    ]
    with patch("src.mailboxes.pool_usable", return_value=True):
        with patch("src.mailboxes.today_usage", return_value=usage):
            with patch("src.mailboxes.total_remaining_capacity", return_value=150):
                snap = capacity.today_capacity(
                    {
                        "autonomy_daily_email_cap": 500,
                        "send_live_emails": True,
                        "autonomy_autopilot": True,
                    }
                )
    assert snap["pool_on"] is True
    assert snap["pool_remaining"] == 150
    assert snap["remaining"] == 150  # min(soft 500, pool 150)
    assert snap["share_caps"] is True


def test_capacity_pool_exhausted_message(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "OUTBOUND_LOG", tmp_path / "o.json")
    (tmp_path / "o.json").write_text("[]", encoding="utf-8")
    with patch("src.mailboxes.pool_usable", return_value=True):
        with patch(
            "src.mailboxes.today_usage",
            return_value=[
                {
                    "id": "mb1",
                    "email": "a@g.com",
                    "enabled": True,
                    "has_password": True,
                    "sent": 200,
                    "cap": 200,
                    "remaining": 0,
                }
            ],
        ):
            with patch("src.mailboxes.total_remaining_capacity", return_value=0):
                snap = capacity.today_capacity(
                    {"autonomy_daily_email_cap": 500, "send_live_emails": True}
                )
    assert snap["exhausted"] is True
    assert "Gmail pool" in snap["resumes_msg"]


def test_under_daily_email_cap_uses_capacity(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "OUTBOUND_LOG", tmp_path / "o.json")
    day = date.today().isoformat()
    (tmp_path / "o.json").write_text(
        json.dumps([{"at": f"{day}T09:00:00"}] * 5), encoding="utf-8"
    )
    with patch("src.mailboxes.pool_usable", return_value=False):
        ok, sent, cap = tools.under_daily_email_cap(
            {"autonomy_daily_email_cap": 5, "autopilot_daily_target": 0}
        )
    assert sent == 5
    assert cap == 5
    assert ok is False


def test_imap_force_with_empty_password():
    pr = imap.poll_recent_inbox(
        {"imap_poll_enabled": True},
        mailboxes=[{"email": "x@y.com", "smtp_password": ""}],
        force=True,
    )
    assert pr.mailboxes_polled == 1
    assert pr.errors


def test_imap_html_body_fallback():
    raw = (
        b"From: a@b.com\r\nSubject: Hi\r\nContent-Type: text/html\r\n\r\n"
        b"<html><body><p>Hello <b>there</b></p></body></html>"
    )
    msg = imap.parse_raw_email(raw, mailbox_email="m@m.com")
    assert "Hello" in msg.body


def test_llm_complete_all_fail_empty_rules():
    company = {"llm_provider": "gemini", "gemini_api_key": "x"}
    with patch.object(llm, "_call_gemini", return_value=""):
        with patch.object(llm, "_call_groq", return_value=""):
            with patch.object(llm, "_call_ollama", return_value=""):
                result = llm.complete("hi", company, rules_fallback="")
    # empty rules_fallback → still returns a result object
    assert result is not None


def test_emailer_pool_exhausted_message(tmp_path, monkeypatch):
    monkeypatch.setattr("src.emailer.OUTBOUND_LOG", tmp_path / "out.json")
    company = {
        "send_live_emails": True,
        "smtp_password": "should-not-use",
        "my_email": "a@b.com",
    }
    with patch("src.mailboxes.pool_usable", return_value=True):
        with patch("src.mailboxes.pick_mailbox", return_value=None):
            r = send_email("to@x.com", "subj", "body", company)
    assert r["ok"] is False
    assert r.get("mailbox_exhausted") is True
    assert "daily cap" in (r.get("error") or "").lower()


def test_tool_send_email_pool_cap_message(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "OUTBOUND_LOG", tmp_path / "out.json")
    (tmp_path / "out.json").write_text("[]", encoding="utf-8")
    lead = {
        "company_name": "A",
        "email": "a@a.com",
        "status": "not_started",
        "crm_status": "open",
    }
    with patch.object(
        tools,
        "under_daily_email_cap",
        return_value=(False, 50, 50),
    ):
        with patch("src.mailboxes.pool_usable", return_value=True):
            with patch("src.mailboxes.pool_exhausted", return_value=True):
                tr = tools.tool_send_email(
                    lead,
                    {"send_live_emails": True},
                    subject="Hi",
                    body="Hello world",
                )
    assert tr.skipped
    assert "pool" in tr.message.lower() or "cap" in tr.message.lower()
