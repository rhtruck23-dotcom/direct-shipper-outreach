"""LLM priority failover, agent tool guards, action JSON parse, autonomy."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import patch

import src.agent_tools as tools
import src.autonomy as autonomy
import src.llm as llm


def test_llm_priority_order_default():
    company = {"gemini_api_key": "", "groq_api_key": ""}
    chain = llm.llm_priority(company)
    assert chain[0] == "gemini"
    assert "groq" in chain
    assert "ollama" in chain
    assert chain.index("gemini") < chain.index("groq") < chain.index("ollama")


def test_llm_priority_from_slots():
    company = {
        "llm_provider_1": "groq",
        "llm_provider_2": "ollama",
        "llm_provider_3": "gemini",
        "llm_model_1": "llama-3.1-8b-instant",
        "groq_api_key": "gk",
    }
    assert llm.llm_priority(company)[:3] == ["groq", "ollama", "gemini"]
    assert llm.preferred_provider(company) == "groq"
    assert llm.provider_model("groq", company) == "llama-3.1-8b-instant"


def test_llm_priority_list_config():
    company = {"llm_priority": ["ollama", "gemini"]}
    chain = llm.llm_priority(company)
    assert chain[0] == "ollama"
    assert "gemini" in chain
    assert "groq" in chain  # filled from DEFAULT_PRIORITY


def test_complete_failover_order_and_log():
    company = {
        "llm_provider_1": "gemini",
        "llm_provider_2": "groq",
        "llm_provider_3": "ollama",
        "gemini_api_key": "gk",
        "groq_api_key": "gq",
    }
    calls = []

    def fake_gemini(*_a, **_k):
        calls.append("gemini")
        return ""

    def fake_groq(*_a, **_k):
        calls.append("groq")
        return "answered by groq"

    def fake_ollama(*_a, **_k):
        calls.append("ollama")
        return "should not reach"

    with patch.object(llm, "_call_gemini", side_effect=fake_gemini):
        with patch.object(llm, "_call_groq", side_effect=fake_groq):
            with patch.object(llm, "_call_ollama", side_effect=fake_ollama):
                result = llm.complete("hi", company)
    assert result.ok
    assert result.provider == "groq"
    assert calls == ["gemini", "groq"]
    assert "ollama" not in calls


def test_complete_rules_fallback_never_total_fail():
    company = {"llm_provider": "gemini", "gemini_api_key": "x"}
    with patch.object(llm, "_call_gemini", return_value=""):
        with patch.object(llm, "_call_ollama", side_effect=ConnectionError("down")):
            with patch.object(llm, "_call_groq", return_value=""):
                result = llm.complete(
                    "hi",
                    company,
                    rules_fallback='{"action":"noop","reasoning":"rules"}',
                )
    assert result.ok
    assert result.provider == "rules"
    assert "noop" in result.text


def test_parse_action_json():
    single = tools.parse_action_json(
        'Sure:\n{"action":"append_note","text":"Called","reasoning":"nurture"}\n'
    )
    assert single["action"] == "append_note"
    assert single["text"] == "Called"

    batch = tools.parse_actions_json(
        '{"actions":[{"action":"create_task","title":"Call"},{"action":"noop"}],'
        '"reasoning":"batch"}'
    )
    assert len(batch) == 2
    assert batch[0]["action"] == "create_task"
    assert tools.parse_action_json("no json") is None


def test_send_email_blocked_for_dnc(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "OUTBOUND_LOG", tmp_path / "outbound.json")
    lead = {
        "company_name": "DNC Co",
        "email": "x@y.com",
        "status": "do_not_contact",
        "crm_status": "dnc",
    }
    company = {"send_live_emails": True, "autonomy_daily_email_cap": 50}
    with patch.object(tools, "send_one_off_email") as send_mock:
        tr = tools.tool_send_email(
            lead, company, subject="Hi", body="Hello there", funnel="shipper"
        )
        send_mock.assert_not_called()
    assert not tr.ok
    assert tr.skipped
    assert "do_not_contact" in tr.message


def test_send_email_dry_run_still_sends(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "OUTBOUND_LOG", tmp_path / "outbound.json")
    lead = {
        "id": "L1",
        "company_name": "Acme",
        "email": "a@a.com",
        "status": "not_started",
        "crm_status": "open",
        "conversation": [],
    }
    company = {"send_live_emails": False, "autonomy_daily_email_cap": 50}

    def fake_send(lead, company, *, subject, body, funnel="shipper"):
        return {"ok": True, "mode": "dry_run", "at": datetime.now().isoformat()}

    with patch.object(tools, "send_one_off_email", side_effect=fake_send):
        tr = tools.tool_send_email(
            lead, company, subject="Hi", body="Checking in", funnel="shipper"
        )
    assert tr.ok
    assert tr.data.get("mode") == "dry_run"


def test_execute_update_and_escalate(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.lead_crm.TASKS_JSON", tmp_path / "tasks.json"
    )
    monkeypatch.setattr("src.lead_crm._try_save_sheet_tasks", lambda *_a, **_k: None)
    lead = {
        "id": "L2",
        "company_name": "Beta",
        "email": "b@b.com",
        "status": "emailed_1",
        "crm_status": "open",
        "sales_stage": "contacted",
        "priority": "medium",
        "notes_timeline": [],
        "remarks": "",
    }
    company = {"owner_notify_email": "", "send_live_emails": False}
    with patch.object(tools, "notify_owner", return_value=None):
        tr = tools.execute_action(
            {
                "action": "update_lead_fields",
                "stage": "engaged",
                "priority": "high",
                "next_contact_at": "2026-09-28T09:00",
            },
            lead=lead,
            company=company,
        )
    assert tr.ok
    assert lead["sales_stage"] == "engaged"
    assert lead["priority"] == "high"

    with patch.object(tools, "notify_owner") as n:
        tr2 = tools.execute_action(
            {"action": "escalate_to_owner", "reason": "They asked for a rate"},
            lead=lead,
            company=company,
        )
        n.assert_called_once()
    assert tr2.escalated
    assert lead["active_sequence"] is False


def test_autonomy_rules_fallback_and_skip_dnc(tmp_path, monkeypatch):
    monkeypatch.setattr("src.lead_crm.TASKS_JSON", tmp_path / "tasks.json")
    monkeypatch.setattr("src.lead_crm._try_save_sheet_tasks", lambda *_a, **_k: None)
    monkeypatch.setattr(tools, "OUTBOUND_LOG", tmp_path / "outbound.json")

    dnc = {
        "id": "D1",
        "company_name": "Nope",
        "email": "n@n.com",
        "status": "do_not_contact",
        "crm_status": "dnc",
        "next_contact_at": "2026-09-01T09:00",
        "active_sequence": False,
    }
    due = {
        "id": "D2",
        "company_name": "Due Co",
        "email": "d@d.com",
        "status": "emailed_1",
        "crm_status": "waiting_reply",
        "sales_stage": "contacted",
        "priority": "medium",
        "next_contact_at": "2026-09-20T09:00",
        "active_sequence": False,
        "notes_timeline": [],
        "remarks": "",
        "conversation": [],
    }
    company = {
        "autonomy_autopilot": False,
        "autonomy_max_leads": 5,
        "send_live_emails": False,
        "gemini_api_key": "",
        "groq_api_key": "",
    }

    # Autopilot off without force → idle
    idle = autonomy.run_autonomy_pass(
        company, shipper_leads=[due], x_leads=[], force=False
    )
    assert idle["ran"] is False
    assert idle["reason"] == "autopilot_off"

    with patch.object(llm, "generate", return_value=llm.LLMResult("", "none", error="fail")):
        with patch.object(autonomy, "_persist_lead"):
            result = autonomy.run_autonomy_pass(
                company,
                shipper_leads=[dnc, due],
                x_leads=[],
                force=True,
                max_leads=5,
            )
    assert result["ran"] is True
    # DNC skipped from candidates
    names = [s["lead"] for s in result["summaries"]]
    assert "Nope" not in names
    assert "Due Co" in names
    # Rules fallback produced an action
    assert result["summaries"][0]["provider"] in ("rules", "none") or result["summaries"][0][
        "actions"
    ]


def test_lead_needs_autonomy():
    today = date(2026, 9, 26)
    lead = {
        "status": "emailed_1",
        "crm_status": "open",
        "next_contact_at": "2026-09-25T10:00",
        "active_sequence": False,
    }
    assert autonomy.lead_needs_autonomy(lead, today=today) is True
    lead["status"] = "converted"
    lead["crm_status"] = "converted"
    lead["sales_stage"] = "converted"
    assert autonomy.lead_needs_autonomy(lead, today=today) is False
