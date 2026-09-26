"""Multi-Gmail mailbox pool + emailer integration."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import src.emailer as emailer
import src.mailboxes as mailboxes


def _seed_pool(tmp_path, monkeypatch, rows):
    monkeypatch.setattr(mailboxes, "MAILBOXES_JSON", tmp_path / "mailboxes.json")
    monkeypatch.setattr(mailboxes, "SEND_COUNTS_JSON", tmp_path / "counts.json")
    monkeypatch.setattr(mailboxes, "_using_cloud", lambda: False)
    mailboxes.save_mailboxes(rows)


def test_pick_mailbox_round_robin(tmp_path, monkeypatch):
    _seed_pool(
        tmp_path,
        monkeypatch,
        [
            {
                "id": "a",
                "email": "a@gmail.com",
                "smtp_password": "pw-a",
                "daily_cap": 200,
                "enabled": True,
            },
            {
                "id": "b",
                "email": "b@gmail.com",
                "smtp_password": "pw-b",
                "daily_cap": 200,
                "enabled": True,
            },
            {
                "id": "c",
                "email": "c@gmail.com",
                "smtp_password": "pw-c",
                "daily_cap": 200,
                "enabled": True,
            },
        ],
    )
    first = mailboxes.pick_mailbox()
    second = mailboxes.pick_mailbox()
    third = mailboxes.pick_mailbox()
    fourth = mailboxes.pick_mailbox()
    assert first["id"] == "a"
    assert second["id"] == "b"
    assert third["id"] == "c"
    assert fourth["id"] == "a"


def test_pick_mailbox_skips_at_cap(tmp_path, monkeypatch):
    _seed_pool(
        tmp_path,
        monkeypatch,
        [
            {
                "id": "a",
                "email": "a@gmail.com",
                "smtp_password": "pw-a",
                "daily_cap": 1,
                "enabled": True,
            },
            {
                "id": "b",
                "email": "b@gmail.com",
                "smtp_password": "pw-b",
                "daily_cap": 200,
                "enabled": True,
            },
        ],
    )
    mailboxes.record_send("a")
    picked = mailboxes.pick_mailbox()
    assert picked is not None
    assert picked["id"] == "b"


def test_all_exhausted_returns_none(tmp_path, monkeypatch):
    _seed_pool(
        tmp_path,
        monkeypatch,
        [
            {
                "id": "a",
                "email": "a@gmail.com",
                "smtp_password": "pw-a",
                "daily_cap": 1,
                "enabled": True,
            },
            {
                "id": "b",
                "email": "b@gmail.com",
                "smtp_password": "pw-b",
                "daily_cap": 1,
                "enabled": True,
            },
        ],
    )
    mailboxes.record_send("a")
    mailboxes.record_send("b")
    assert mailboxes.pick_mailbox() is None
    assert mailboxes.pool_exhausted() is True
    assert mailboxes.total_remaining_capacity() == 0


def test_counters_increment_only_on_live(tmp_path, monkeypatch):
    _seed_pool(
        tmp_path,
        monkeypatch,
        [
            {
                "id": "a",
                "email": "a@gmail.com",
                "smtp_password": "pw-a",
                "daily_cap": 200,
                "enabled": True,
            },
        ],
    )
    monkeypatch.setattr(emailer, "OUTBOUND_LOG", tmp_path / "outbound.json")

    dry = emailer.send_email(
        "t@t.com",
        "s",
        "b",
        {"send_live_emails": False},
        meta={"type": "test"},
    )
    assert dry["mode"] == "dry_run"
    assert mailboxes.get_send_count("a") == 0

    smtp = MagicMock()
    smtp.__enter__ = MagicMock(return_value=smtp)
    smtp.__exit__ = MagicMock(return_value=False)
    with patch("smtplib.SMTP", return_value=smtp):
        live = emailer.send_email(
            "t@t.com",
            "s",
            "b",
            {"send_live_emails": True, "smtp_password": ""},
        )
    assert live["ok"]
    assert live["mode"] == "live"
    assert live.get("mailbox_id") == "a"
    assert live.get("mailbox_email") == "a@gmail.com"
    assert mailboxes.get_send_count("a") == 1


def test_emailer_uses_pool_when_present(tmp_path, monkeypatch):
    _seed_pool(
        tmp_path,
        monkeypatch,
        [
            {
                "id": "pool1",
                "email": "heronmb3@gmail.com",
                "smtp_password": "app-password-here",
                "daily_cap": 200,
                "enabled": True,
            },
        ],
    )
    monkeypatch.setattr(emailer, "OUTBOUND_LOG", tmp_path / "outbound.json")
    smtp = MagicMock()
    smtp.__enter__ = MagicMock(return_value=smtp)
    smtp.__exit__ = MagicMock(return_value=False)
    with patch("smtplib.SMTP", return_value=smtp) as smtp_cls:
        r = emailer.send_email(
            "shipper@example.com",
            "Capacity",
            "Hello",
            {
                "send_live_emails": True,
                # Company SMTP should be ignored when pool is usable
                "smtp_user": "accounts@logixtrek.com",
                "smtp_password": "company-pw-should-not-login",
                "my_email": "accounts@logixtrek.com",
            },
        )
    assert r["ok"]
    assert r["from"] == "heronmb3@gmail.com"
    assert r["mailbox_id"] == "pool1"
    smtp_cls.assert_called()
    smtp.login.assert_called_with("heronmb3@gmail.com", "app-password-here")


def test_emailer_fails_when_pool_exhausted(tmp_path, monkeypatch):
    _seed_pool(
        tmp_path,
        monkeypatch,
        [
            {
                "id": "a",
                "email": "a@gmail.com",
                "smtp_password": "pw",
                "daily_cap": 1,
                "enabled": True,
            },
        ],
    )
    mailboxes.record_send("a")
    monkeypatch.setattr(emailer, "OUTBOUND_LOG", tmp_path / "outbound.json")
    r = emailer.send_email(
        "t@t.com",
        "s",
        "b",
        {"send_live_emails": True, "smtp_password": "fallback-should-not-use"},
    )
    assert not r["ok"]
    assert r.get("mailbox_exhausted")
    assert "cap" in (r.get("error") or "").lower()


def test_emailer_falls_back_to_company_when_pool_empty(tmp_path, monkeypatch):
    _seed_pool(tmp_path, monkeypatch, [])
    monkeypatch.setattr(emailer, "OUTBOUND_LOG", tmp_path / "outbound.json")
    smtp = MagicMock()
    smtp.__enter__ = MagicMock(return_value=smtp)
    smtp.__exit__ = MagicMock(return_value=False)
    with patch("smtplib.SMTP", return_value=smtp):
        r = emailer.send_email(
            "t@t.com",
            "s",
            "b",
            {
                "send_live_emails": True,
                "smtp_host": "smtp.gmail.com",
                "smtp_port": 587,
                "smtp_user": "accounts@logixtrek.com",
                "smtp_password": "company-pw",
                "my_email": "accounts@logixtrek.com",
            },
        )
    assert r["ok"]
    assert r["from"] == "accounts@logixtrek.com"
    assert "mailbox_id" not in r
    smtp.login.assert_called_with("accounts@logixtrek.com", "company-pw")


def test_under_daily_cap_respects_autopilot_target(tmp_path, monkeypatch):
    import src.agent_tools as tools

    monkeypatch.setattr(tools, "OUTBOUND_LOG", tmp_path / "outbound.json")
    monkeypatch.setattr(tools, "emails_sent_today", lambda today=None: 400)
    ok, sent, cap = tools.under_daily_email_cap(
        {"autonomy_daily_email_cap": 600, "autopilot_daily_target": 400}
    )
    assert not ok
    assert sent == 400
    assert cap == 400
