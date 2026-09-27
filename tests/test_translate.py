"""Unit tests for email Spanish/English translation helpers (mocked LLM)."""
from __future__ import annotations

from unittest.mock import patch

import src.translate as tr
from src.llm import LLMResult


def test_protect_and_restore_merge_fields_and_mc():
    text = "Hi {contact_name}, our MC-1590829 covers {company_name} lanes."
    protected, mapping = tr._protect_tokens(text)
    assert "{contact_name}" not in protected or "⟦LT" in protected
    assert "MC-1590829" not in protected or any("MC" in v for v in mapping.values())
    restored = tr._restore_tokens(protected, mapping)
    assert restored == text


def test_translate_text_calls_complete_and_restores(monkeypatch):
    captured = {}

    def fake_complete(prompt, company=None, **kwargs):
        captured["prompt"] = prompt
        # Echo with Spanish-ish wrapper but keep tokens
        body = prompt.split("SOURCE:\n", 1)[-1].strip()
        return LLMResult(f"ES:{body}", "gemini", model="flash")

    monkeypatch.setattr(tr, "complete", fake_complete)
    result = tr.translate_text(
        "Hello {contact_name}, MC-123456 is ready.",
        target_lang="es",
        company={"gemini_api_key": "x"},
    )
    assert result.ok
    assert result.provider == "gemini"
    assert "{contact_name}" in result.text
    assert "MC-123456" in result.text
    assert "⟦LT" not in result.text
    assert "natural" in captured["prompt"].lower() or "Spanish" in captured["prompt"]


def test_translate_text_rules_fallback_on_empty_llm(monkeypatch):
    monkeypatch.setattr(
        tr,
        "complete",
        lambda *a, **k: LLMResult("Hello again", "rules", model="rules"),
    )
    result = tr.translate_text("Hello again", target_lang="es")
    assert result.provider == "rules"
    assert result.text == "Hello again"


def test_translate_email_pair_json(monkeypatch):
    def fake_complete(prompt, company=None, **kwargs):
        return LLMResult(
            json_dumps_ok(),
            "groq",
            model="llama",
        )

    def json_dumps_ok():
        return '{"subject":"Hola {contact_name}","body":"Nuestro MC-999999 lista."}'

    monkeypatch.setattr(tr, "complete", fake_complete)
    subj, body, result = tr.translate_email_pair(
        "Hi {contact_name}",
        "Our MC-999999 is ready.",
        target_lang="es",
    )
    assert result.provider == "groq"
    assert "{contact_name}" in subj
    assert "MC-999999" in body
    assert "Hola" in subj or "MC-999999" in body


def test_translate_email_pair_falls_back_to_per_field(monkeypatch):
    calls = {"n": 0}

    def fake_complete(prompt, company=None, **kwargs):
        calls["n"] += 1
        # First call (pair) returns non-JSON; subsequent per-field calls return ES:
        if "Return ONLY valid JSON" in prompt or '"subject"' in prompt and "BODY:" in prompt:
            return LLMResult("not json", "gemini")
        src = prompt.split("SOURCE:\n", 1)[-1].strip()
        return LLMResult(f"ES-{src}", "gemini")

    monkeypatch.setattr(tr, "complete", fake_complete)
    subj, body, result = tr.translate_email_pair("Hello", "World", target_lang="es")
    assert "ES-" in subj or "ES-" in body
    assert result.provider == "gemini"
    assert calls["n"] >= 2


def test_empty_translate():
    r = tr.translate_text("  ", target_lang="es")
    assert not r.ok
    s, b, r2 = tr.translate_email_pair("", "", target_lang="es")
    assert s == "" and b == ""
