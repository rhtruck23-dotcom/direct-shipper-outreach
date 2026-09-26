"""CRM picklists, task due buckets, LLM provider fallback."""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import src.crm_picklists as pick
import src.lead_crm as lcrm
import src.llm as llm


def test_picklist_normalize():
    assert pick.normalize_sales_stage("NEW") == "new"
    assert pick.normalize_sales_stage("emailed_1") == "contacted"
    assert pick.normalize_sales_stage("won") == "converted"
    assert pick.normalize_sales_stage("bogus") == "new"
    assert pick.normalize_crm_status("Waiting Reply") == "waiting_reply"
    assert pick.normalize_crm_status("do_not_contact") == "dnc"
    assert pick.normalize_crm_status("") == "open"
    assert pick.normalize_priority("MED") == "medium"
    assert pick.normalize_priority("critical") == "urgent"
    assert pick.normalize_priority("nope") == "medium"
    lead = pick.apply_crm_defaults({})
    assert lead["sales_stage"] == "new"
    assert lead["crm_status"] == "open"
    assert lead["priority"] == "medium"
    assert lead["notes_timeline"] == []


def test_tasks_due_logic(tmp_path, monkeypatch):
    monkeypatch.setattr(lcrm, "TASKS_JSON", tmp_path / "lead_tasks.json")
    monkeypatch.setattr(lcrm, "_try_save_sheet_tasks", lambda *_a, **_k: None)
    monkeypatch.setattr(lcrm, "_try_load_sheet_tasks", lambda: None)

    today = date(2026, 9, 26)
    tasks = [
        lcrm._normalize_task(
            {"id": "1", "title": "Past", "due_at": "2026-09-20T10:00", "status": "open", "lead_id": "L1"}
        ),
        lcrm._normalize_task(
            {"id": "2", "title": "Today", "due_at": "2026-09-26T17:00", "status": "open", "lead_id": "L1"}
        ),
        lcrm._normalize_task(
            {
                "id": "3",
                "title": "Soon",
                "due_at": (today + timedelta(days=3)).isoformat() + "T09:00",
                "status": "open",
                "lead_id": "L2",
            }
        ),
        lcrm._normalize_task(
            {
                "id": "4",
                "title": "Later",
                "due_at": (today + timedelta(days=20)).isoformat() + "T09:00",
                "status": "open",
                "lead_id": "L2",
            }
        ),
        lcrm._normalize_task(
            {"id": "5", "title": "Done", "due_at": "2026-09-01", "status": "done", "lead_id": "L1"}
        ),
    ]
    lcrm.save_tasks(tasks)

    assert lcrm.classify_task_bucket(tasks[0], today=today) == "past_due"
    assert lcrm.classify_task_bucket(tasks[1], today=today) == "due_today"
    assert lcrm.classify_task_bucket(tasks[2], today=today) == "upcoming"
    assert lcrm.classify_task_bucket(tasks[3], today=today) == "later"
    assert lcrm.classify_task_bucket(tasks[4], today=today) == "done"

    buckets = lcrm.group_open_tasks(tasks, today=today, upcoming_days=7)
    assert [t["id"] for t in buckets["past_due"]] == ["1"]
    assert [t["id"] for t in buckets["due_today"]] == ["2"]
    assert [t["id"] for t in buckets["upcoming"]] == ["3"]
    assert [t["id"] for t in buckets["later"]] == ["4"]

    created = lcrm.create_task(
        lead_id="L9", title="Call back", due_at="2026-09-27T12:00", funnel="shipper"
    )
    assert created["id"]
    assert created["status"] == "open"
    done = lcrm.mark_task_done(created["id"])
    assert done and done["status"] == "done"

    lead = {"id": "L1", "company_name": "Acme", "email": "a@a.com", "remarks": ""}
    lcrm.append_note(lead, "Left voicemail", author="Sam")
    assert len(lead["notes_timeline"]) == 1
    assert "voicemail" in (lead["remarks"] or "").lower()


def test_llm_fallback_chain_and_rules():
    company = {"llm_provider": "ollama", "gemini_api_key": "", "groq_api_key": ""}
    chain0 = llm.fallback_chain(company)
    assert chain0[0] == "ollama"
    assert "gemini" in chain0
    assert "groq" in chain0

    company2 = {
        "llm_provider": "gemini",
        "gemini_api_key": "gk",
        "groq_api_key": "gq",
    }
    chain = llm.fallback_chain(company2)
    assert chain[0] == "gemini"
    assert "ollama" in chain
    assert "groq" in chain

    # All providers fail → none (caller uses rules)
    with patch.object(llm, "_call_gemini", return_value=""):
        with patch.object(llm, "_call_ollama", side_effect=ConnectionError("down")):
            with patch.object(llm, "_call_groq", return_value=""):
                result = llm.generate("hi", {"llm_provider": "gemini", "gemini_api_key": "x", "groq_api_key": "y"})
    assert result.provider == "none"
    assert not result.ok

    # Preferred fails, gemini succeeds
    with patch.object(llm, "_call_ollama", return_value=""):
        with patch.object(llm, "_call_gemini", return_value="hello from gemini"):
            result = llm.generate(
                "hi",
                {"llm_provider": "ollama", "gemini_api_key": "gk", "ollama_model": "llama3.2"},
            )
    assert result.ok
    assert result.provider == "gemini"
    assert "gemini" in result.text.lower() or result.text == "hello from gemini"


def test_llm_extract_json():
    data = llm.extract_json_object('Sure:\n{"subject":"Hi","body":"There"}\n')
    assert data == {"subject": "Hi", "body": "There"}
    assert llm.extract_json_object("no json here") is None
