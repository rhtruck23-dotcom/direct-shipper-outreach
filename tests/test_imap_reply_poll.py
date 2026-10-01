"""IMAP reply discovery — poll, match From: to leads, apply + tasks."""
from __future__ import annotations

from email.mime.text import MIMEText
from pathlib import Path
from unittest.mock import patch

import src.imap_inbox as imap


COMPANY = {
    "imap_poll_enabled": False,
    "autonomy_autopilot": False,
    "my_email": "pool@g.com",
}


def _raw_from(addr: str, body: str, *, subject: str = "Re: hi", mid: str = "<m1@x>") -> bytes:
    msg = MIMEText(body)
    msg["From"] = addr
    msg["Subject"] = subject
    msg["Message-ID"] = mid
    return msg.as_bytes()


class FakeIMAP:
    def __init__(self, raws: list[bytes], *, unseen: bool = True):
        self._raws = raws
        self._unseen = unseen
        self.readonly = None

    def login(self, *a):
        return ("OK", [b""])

    def select(self, box, readonly=False):
        self.readonly = readonly
        assert readonly is True
        return ("OK", [b"1"])

    def search(self, _charset, criterion):
        if criterion == "UNSEEN":
            if self._unseen and self._raws:
                ids = b" ".join(str(i + 1).encode() for i in range(len(self._raws)))
                return ("OK", [ids])
            return ("OK", [b""])
        ids = b" ".join(str(i + 1).encode() for i in range(len(self._raws)))
        return ("OK", [ids])

    def fetch(self, uid, _spec):
        idx = int(uid) - 1 if not isinstance(uid, bytes) else int(uid.decode()) - 1
        raw = self._raws[idx]
        return ("OK", [(b"1 (RFC822)", raw)])

    def logout(self):
        return ("OK", [b""])


def test_imap_poll_defaults_off():
    assert imap.imap_poll_enabled({}) is False
    assert imap.should_auto_poll({}) is False
    assert imap.should_auto_poll({"autonomy_autopilot": True}) is True
    assert imap.should_auto_poll({"imap_poll_enabled": True}) is True
    pr = imap.poll_recent_inbox(COMPANY, mailboxes=[])
    assert pr.enabled is False


def test_poll_prefers_unseen_readonly(tmp_path):
    raw = _raw_from("Lead <ship@example.com>", "We need capacity next week.")
    factory = lambda *a, **k: FakeIMAP([raw], unseen=True)
    mbs = [{"email": "pool@g.com", "smtp_password": "app-pass"}]
    pr = imap.poll_recent_inbox(
        {**COMPANY, "imap_poll_enabled": True},
        mailboxes=mbs,
        imap_factory=factory,
        force=True,
    )
    assert pr.mailboxes_polled == 1
    assert len(pr.messages) == 1
    assert pr.messages[0].from_addr == "ship@example.com"


def test_apply_matches_shipper_and_creates_task(tmp_path, monkeypatch):
    monkeypatch.setattr(imap, "SEEN_JSON", tmp_path / "seen.json")
    tasks_path = tmp_path / "tasks.json"
    monkeypatch.setattr("src.lead_crm.TASKS_JSON", tasks_path)
    monkeypatch.setattr("src.paths.DATA_DIR", tmp_path)

    lead = {
        "company_name": "Acme Dairy",
        "email": "ship@example.com",
        "status": "emailed_1",
        "active_sequence": True,
        "responded": False,
        "conversation": [],
        "remarks": "",
    }
    index = imap.build_lead_email_index(shipper_leads=[lead])
    assert "ship@example.com" in index

    msg = imap.parse_raw_email(
        _raw_from("Shipper <ship@example.com>", "Yes interested — call me."),
        mailbox_email="pool@g.com",
    )

    persisted = []

    def _persist(l, funnel):
        persisted.append((funnel, dict(l)))

    with patch.object(imap, "_persist_funnel_lead", side_effect=_persist):
        with patch.object(imap, "_mark_responded") as mark:
            result = imap.apply_matched_replies(
                [msg],
                lead_index=index,
                seen_path=tmp_path / "seen.json",
                create_tasks=True,
            )
            mark.assert_called_once()

    assert result.applied == 1
    assert result.matches[0].applied is True
    assert result.matches[0].funnel == "shipper"
    assert persisted and persisted[0][0] == "shipper"
    assert any(m.get("direction") == "inbound" for m in persisted[0][1]["conversation"])
    assert result.matches[0].task_id


def test_dnc_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(imap, "SEEN_JSON", tmp_path / "seen.json")
    lead = {
        "company_name": "No Contact Co",
        "email": "dnc@example.com",
        "status": "do_not_contact",
        "conversation": [],
        "remarks": "STOP",
    }
    index = imap.build_lead_email_index(shipper_leads=[lead])
    msg = imap.parse_raw_email(
        _raw_from("dnc@example.com", "leave us alone"),
        mailbox_email="pool@g.com",
    )
    with patch.object(imap, "_persist_funnel_lead") as pers:
        result = imap.apply_matched_replies(
            [msg], lead_index=index, seen_path=tmp_path / "seen2.json"
        )
        pers.assert_not_called()
    assert result.applied == 0
    assert result.skipped_dnc == 1
    assert result.matches[0].skipped_reason == "dnc"


def test_unknown_from_ignored(tmp_path):
    msg = imap.parse_raw_email(
        _raw_from("stranger@nowhere.com", "hi"),
        mailbox_email="pool@g.com",
    )
    result = imap.apply_matched_replies(
        [msg],
        lead_index={},
        seen_path=tmp_path / "seen3.json",
        create_tasks=False,
    )
    assert result.applied == 0
    assert result.skipped_unknown == 1


def test_duplicate_message_id(tmp_path, monkeypatch):
    monkeypatch.setattr(imap, "SEEN_JSON", tmp_path / "seen.json")
    lead = {
        "company_name": "Acme",
        "email": "ship@example.com",
        "status": "emailed_1",
        "conversation": [],
        "remarks": "",
    }
    index = imap.build_lead_email_index(shipper_leads=[lead])
    raw = _raw_from("ship@example.com", "hello again", mid="<dup@x>")
    msg = imap.parse_raw_email(raw, mailbox_email="pool@g.com")

    with patch.object(imap, "_persist_funnel_lead"):
        with patch.object(imap, "_mark_responded"):
            with patch.object(imap, "_create_reply_task", return_value="t1"):
                r1 = imap.apply_matched_replies(
                    [msg], lead_index=index, seen_path=tmp_path / "seen_d.json"
                )
                r2 = imap.apply_matched_replies(
                    [msg], lead_index=index, seen_path=tmp_path / "seen_d.json"
                )
    assert r1.applied == 1
    assert r2.applied == 0
    assert r2.skipped_dup == 1


def test_check_inbox_force_with_mock(tmp_path, monkeypatch):
    monkeypatch.setattr(imap, "SEEN_JSON", tmp_path / "seen.json")
    raw = _raw_from("Lead <car@fleet.com>", "I want to lease on.")
    lead = {
        "company_name": "Fleet LLC",
        "email": "car@fleet.com",
        "status": "emailed_2",
        "conversation": [],
        "remarks": "",
    }
    index = imap.build_lead_email_index(carrier_leads=[lead])
    factory = lambda *a, **k: FakeIMAP([raw])

    with patch.object(imap, "_persist_funnel_lead"):
        with patch.object(imap, "_mark_responded"):
            with patch.object(imap, "_create_reply_task", return_value="task-9"):
                with patch("src.mailboxes.enabled_with_password", return_value=[]):
                    chk = imap.check_inbox_for_replies(
                        COMPANY,
                        mailboxes=[
                            {"email": "pool@g.com", "smtp_password": "pw"}
                        ],
                        imap_factory=factory,
                        force=True,
                        lead_index=index,
                        seen_path=tmp_path / "seen_c.json",
                    )
    assert chk.applied == 1
    assert chk.matches[0].funnel == "carrier"
    assert "Matched & recorded 1" in imap.format_check_summary(chk)


def test_check_inbox_disabled_without_force():
    chk = imap.check_inbox_for_replies(COMPANY, mailboxes=[], force=False)
    assert chk.poll.enabled is False
    assert chk.applied == 0


def test_mailto_helpers():
    assert "mailto:a@b.com" in imap.mailto_compose_link("a@b.com", subject="Hi")
    assert "mail.google.com" in imap.gmail_web_inbox_url("x@y.com")
