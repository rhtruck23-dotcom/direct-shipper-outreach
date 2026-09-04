"""QA for stages + never-recontact rules."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.stages import already_contacted, contact_indicator, may_start_outreach, stage_label


def test_dnc_blocked_forever():
    lead = {"status": "do_not_contact", "email": "a@b.com"}
    ok, reason = may_start_outreach(lead, force=True)
    assert ok is False
    assert "Do Not Contact" in reason or "never" in reason.lower()


def test_converted_blocked():
    ok, _ = may_start_outreach({"status": "converted", "email": "a@b.com"})
    assert ok is False


def test_new_lead_ok():
    ok, _ = may_start_outreach(
        {"status": "not_started", "email": "a@b.com", "last_step_sent": 0}
    )
    assert ok is True


def test_indicators():
    assert "Never" in contact_indicator({"status": "do_not_contact"})
    assert "Customer" in contact_indicator({"status": "converted"})
    assert stage_label("emailed_1") == "Email 1 sent"


def test_already_contacted():
    assert already_contacted({"first_contacted": "2026-01-01"}) is True
    assert already_contacted({"status": "not_started", "last_step_sent": 0}) is False
