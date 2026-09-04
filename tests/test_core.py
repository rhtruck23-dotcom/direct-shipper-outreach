"""QA: scheduling, templates, bot, leads CSV."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# Ensure project root on path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.bot import classify_reply, handle_reply
from src.leads import filter_leads, lead_key, parse_import_csv
from src.schedule import days_until_next, next_action_for_lead
from src.templates import SEQUENCE_SCHEDULE_DAYS, render_email


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
    "unsubscribe_note": "LogixTrek LLC | Macomb IL | Reply STOP",
}


def test_sequence_schedule_days():
    assert SEQUENCE_SCHEDULE_DAYS == {1: 0, 2: 4, 3: 9, 4: 16}


def test_not_started_active_gets_email_1():
    lead = {"status": "not_started", "active_sequence": True, "last_step_sent": 0}
    assert next_action_for_lead(lead) == 1


def test_inactive_gets_nothing():
    lead = {"status": "not_started", "active_sequence": False, "last_step_sent": 0}
    assert next_action_for_lead(lead) is None


def test_email_2_due_on_day_4():
    first = datetime(2026, 1, 1)
    lead = {
        "status": "emailed_1",
        "active_sequence": True,
        "last_step_sent": 1,
        "first_contacted": first.isoformat(),
        "last_emailed": first.isoformat(),
    }
    assert next_action_for_lead(lead, first + timedelta(days=3)) is None
    assert next_action_for_lead(lead, first + timedelta(days=4)) == 2


def test_email_3_and_4_schedule():
    first = datetime(2026, 1, 1)
    lead = {
        "status": "emailed_2",
        "active_sequence": True,
        "last_step_sent": 2,
        "first_contacted": first.isoformat(),
        "last_emailed": (first + timedelta(days=4)).isoformat(),
    }
    assert next_action_for_lead(lead, first + timedelta(days=8)) is None
    assert next_action_for_lead(lead, first + timedelta(days=9)) == 3

    lead["last_step_sent"] = 3
    lead["status"] = "emailed_3"
    assert next_action_for_lead(lead, first + timedelta(days=15)) is None
    assert next_action_for_lead(lead, first + timedelta(days=16)) == 4


def test_responded_stops_sequence():
    lead = {
        "status": "responded",
        "active_sequence": True,
        "last_step_sent": 1,
        "first_contacted": datetime.now().isoformat(),
    }
    assert next_action_for_lead(lead) is None


def test_render_email_merges_logixtrek():
    lead = {
        "contact_name": "Sam",
        "company_name": "Fresh Co",
        "freight_type": "Reefer",
        "lane_or_region": "IL",
    }
    subj, body = render_email(1, lead, COMPANY)
    assert "Fresh Co" in subj
    assert "LogixTrek LLC" in body
    assert "MC-1590829" in body
    assert "Sam" in body


def test_bot_opt_out():
    assert classify_reply("Please unsubscribe me") == "opt_out"
    d = handle_reply(
        {"company_name": "X", "contact_name": "Bob", "email": "a@b.com"},
        "Not interested, stop emailing",
        COMPANY,
    )
    assert d.intent == "opt_out"
    assert d.auto_send is True
    assert d.stop_sequence is True
    assert d.mark_positive is False


def test_bot_escalate_on_rate():
    d = handle_reply(
        {"company_name": "X", "email": "a@b.com"},
        "What is your rate per mile for Chicago to Dallas?",
        COMPANY,
    )
    assert d.intent == "escalate"
    assert d.auto_send is False
    assert d.escalate_to_owner is True


def test_bot_positive():
    d = handle_reply(
        {"company_name": "X", "contact_name": "Pat", "email": "a@b.com"},
        "Yes interested — tell me more and send info",
        COMPANY,
    )
    assert d.intent == "positive"
    assert d.auto_send is True
    assert "MC-1590829" in d.reply_body


def test_filter_by_state_zip():
    leads = [
        {"state": "IL", "zip": "61455", "freight_type": "Reefer", "company_name": "A"},
        {"state": "TX", "zip": "75001", "freight_type": "Dry Van", "company_name": "B"},
    ]
    assert len(filter_leads(leads, state="IL")) == 1
    assert len(filter_leads(leads, zip_prefix="75")) == 1
    assert len(filter_leads(leads, freight_type="Reefer")) == 1


def test_parse_import_csv_aliases():
    raw = b"Company Name,Contact,Email Address,ST,Zip Code\nAcme,Jo,jo@acme.com,IL,61455\n"
    rows = parse_import_csv(raw)
    assert len(rows) == 1
    assert rows[0]["company_name"] == "Acme"
    assert rows[0]["email"] == "jo@acme.com"
    assert rows[0]["state"] == "IL"
    assert rows[0]["zip"] == "61455"


def test_days_until_next():
    first = datetime(2026, 1, 1)
    lead = {
        "status": "emailed_1",
        "active_sequence": True,
        "last_step_sent": 1,
        "first_contacted": first.isoformat(),
    }
    assert days_until_next(lead, first + timedelta(days=2)) == 2
    assert days_until_next(lead, first + timedelta(days=4)) == 0
