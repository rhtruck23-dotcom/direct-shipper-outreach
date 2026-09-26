"""
Unified LLM interface — optional free/local providers with priority failover.

Providers:
  - gemini  (Google AI Studio key)
  - groq    (optional free-tier key)
  - ollama  (local Llama/Mistral via http://127.0.0.1:11434)

Priority failover (default: gemini → groq → ollama → rules):
  Org Setup sets Priority 1/2/3 providers + models (llm_provider_1..3 / llm_priority).
  complete()/generate() try each in order until one succeeds; log which engine answered.
  Callers supply rule-based fallback when result.provider == 'none' / not ok.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Optional

PROVIDERS = ("gemini", "groq", "ollama")
DEFAULT_PRIORITY = ["gemini", "groq", "ollama"]
DEFAULT_OLLAMA_MODEL = "llama3.2"
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"
OLLAMA_BASE = "http://127.0.0.1:11434"

_log = logging.getLogger("llm")


@dataclass
class LLMResult:
    text: str
    provider: str  # gemini | ollama | groq | none | rules
    model: str = ""
    error: str = ""
    attempted: tuple = ()

    @property
    def ok(self) -> bool:
        return bool((self.text or "").strip()) and self.provider not in ("none", "")


def _secret(name: str) -> str:
    env = os.getenv(name.upper(), "") or os.getenv(name, "")
    if env.strip():
        return env.strip()
    try:
        import streamlit as st

        return str(st.secrets.get(name, "") or "").strip()
    except Exception:
        return ""


def gemini_key(company: Optional[dict] = None) -> str:
    if company:
        k = (company.get("gemini_api_key") or "").strip()
        if k:
            return k
    return _secret("gemini_api_key") or _secret("GEMINI_API_KEY")


def groq_key(company: Optional[dict] = None) -> str:
    if company:
        k = (company.get("groq_api_key") or "").strip()
        if k:
            return k
    return _secret("groq_api_key") or _secret("GROQ_API_KEY")


def preferred_provider(company: Optional[dict] = None) -> str:
    """First entry in priority list (backward-compatible helper)."""
    chain = llm_priority(company)
    return chain[0] if chain else "gemini"


def ollama_model(company: Optional[dict] = None) -> str:
    return provider_model("ollama", company)


def provider_model(name: str, company: Optional[dict] = None) -> str:
    """Resolve model string for a provider from company config / secrets."""
    name = (name or "").strip().lower()
    cfg = company or {}
    # Per-slot models when priority slots are used
    for i in (1, 2, 3):
        slot = (cfg.get(f"llm_provider_{i}") or "").strip().lower()
        if slot == name:
            m = (cfg.get(f"llm_model_{i}") or "").strip()
            if m:
                return m
    if name == "gemini":
        return (
            (cfg.get("gemini_model") or "").strip()
            or (_secret("gemini_model") or DEFAULT_GEMINI_MODEL)
        )
    if name == "groq":
        return (
            (cfg.get("groq_model") or "").strip()
            or (_secret("groq_model") or DEFAULT_GROQ_MODEL)
        )
    if name == "ollama":
        return (
            (cfg.get("ollama_model") or "").strip()
            or (_secret("ollama_model") or DEFAULT_OLLAMA_MODEL)
        ) or DEFAULT_OLLAMA_MODEL
    return ""


def provider_available(name: str, company: Optional[dict] = None) -> bool:
    name = (name or "").strip().lower()
    if name == "gemini":
        return bool(gemini_key(company))
    if name == "groq":
        return bool(groq_key(company))
    if name == "ollama":
        return True  # try localhost; call may fail → next in chain
    if name == "rules":
        return True
    return False


def _normalize_provider(raw: str) -> str:
    s = (raw or "").strip().lower()
    if s in PROVIDERS or s == "rules":
        return s
    return ""


def llm_priority(company: Optional[dict] = None) -> list[str]:
    """
    Ordered provider list (no 'rules' — callers handle rules).

    Sources (first match wins):
      1. company['llm_priority'] list
      2. llm_provider_1 / _2 / _3
      3. legacy llm_provider preference + DEFAULT_PRIORITY
    """
    cfg = company or {}
    ordered: list[str] = []

    raw_list = cfg.get("llm_priority")
    if isinstance(raw_list, str) and raw_list.strip():
        raw_list = [p.strip() for p in raw_list.replace(";", ",").split(",") if p.strip()]
    if isinstance(raw_list, (list, tuple)) and raw_list:
        for p in raw_list:
            n = _normalize_provider(str(p))
            if n and n != "rules" and n not in ordered:
                ordered.append(n)

    if not ordered:
        for i in (1, 2, 3):
            n = _normalize_provider(str(cfg.get(f"llm_provider_{i}") or ""))
            if n and n != "rules" and n not in ordered:
                ordered.append(n)

    if not ordered:
        legacy = _normalize_provider(
            str(cfg.get("llm_provider") or _secret("llm_provider") or "")
        )
        if legacy and legacy != "rules":
            ordered.append(legacy)
        for p in DEFAULT_PRIORITY:
            if p not in ordered:
                ordered.append(p)

    # Ensure we always have a full chain for failover
    for p in DEFAULT_PRIORITY:
        if p not in ordered:
            ordered.append(p)
    return ordered


def fallback_chain(company: Optional[dict] = None) -> list[str]:
    """Alias used by older callers — same as llm_priority."""
    return llm_priority(company)


def _call_gemini(prompt: str, key: str, *, model: str = DEFAULT_GEMINI_MODEL, timeout: int = 60) -> str:
    import requests

    model = (model or DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    resp = requests.post(
        url,
        params={"key": key},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=timeout,
    )
    if resp.status_code != 200:
        return ""
    data = resp.json()
    return (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
        or ""
    )


def _call_ollama(
    prompt: str,
    model: str,
    *,
    base: str = OLLAMA_BASE,
    timeout: int = 90,
) -> str:
    import requests

    resp = requests.post(
        f"{base.rstrip('/')}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=timeout,
    )
    if resp.status_code != 200:
        return ""
    data = resp.json()
    return str(data.get("response") or "").strip()


def _call_groq(
    prompt: str,
    key: str,
    *,
    model: str = DEFAULT_GROQ_MODEL,
    timeout: int = 60,
) -> str:
    import requests

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model or DEFAULT_GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.4,
        },
        timeout=timeout,
    )
    if resp.status_code != 200:
        return ""
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        return ""
    return str((choices[0].get("message") or {}).get("content") or "").strip()


def _try_provider(
    name: str,
    prompt: str,
    company: Optional[dict],
    *,
    timeout: int,
) -> LLMResult:
    name = name.lower()
    model = provider_model(name, company)
    try:
        if name == "gemini":
            key = gemini_key(company)
            if not key:
                return LLMResult("", "none", error="no gemini key")
            text = _call_gemini(prompt, key, model=model, timeout=timeout)
            return LLMResult(
                text,
                "gemini" if text else "none",
                model=model or DEFAULT_GEMINI_MODEL,
                error="" if text else "gemini empty",
            )
        if name == "ollama":
            text = _call_ollama(prompt, model, timeout=timeout)
            return LLMResult(
                text,
                "ollama" if text else "none",
                model=model,
                error="" if text else "ollama unavailable",
            )
        if name == "groq":
            key = groq_key(company)
            if not key:
                return LLMResult("", "none", error="no groq key")
            text = _call_groq(prompt, key, model=model, timeout=timeout)
            return LLMResult(
                text,
                "groq" if text else "none",
                model=model or DEFAULT_GROQ_MODEL,
                error="" if text else "groq empty",
            )
    except Exception as e:
        return LLMResult("", "none", error=f"{name}: {e}")
    return LLMResult("", "none", error=f"unknown provider {name}")


def generate(
    prompt: str,
    company: Optional[dict] = None,
    *,
    timeout: int = 60,
    providers: Optional[list[str]] = None,
) -> LLMResult:
    """
    Try providers in priority order. Returns first non-empty text.
    If all fail → LLMResult with provider='none' (caller uses rules).
    """
    chain = [p for p in (providers or llm_priority(company)) if p != "rules"]
    attempted: list[str] = []
    last_err = ""
    for name in chain:
        if name in ("gemini", "groq") and not provider_available(name, company):
            attempted.append(f"{name}:skip")
            continue
        attempted.append(name)
        result = _try_provider(name, prompt, company, timeout=timeout)
        if result.ok:
            result.attempted = tuple(attempted)
            _log.info("LLM answered via %s (%s)", result.provider, result.model or "")
            return result
        last_err = result.error or last_err
    _log.warning("LLM all providers failed: %s (tried %s)", last_err, attempted)
    return LLMResult(
        "",
        "none",
        error=last_err or "all providers failed",
        attempted=tuple(attempted),
    )


def complete(
    prompt: str,
    company: Optional[dict] = None,
    *,
    timeout: int = 60,
    providers: Optional[list[str]] = None,
    rules_fallback: str = "",
) -> LLMResult:
    """
    Priority failover complete(). On total LLM failure, optionally return
    rules_fallback text with provider='rules' so email/reply never hard-fails.
    """
    result = generate(prompt, company, timeout=timeout, providers=providers)
    if result.ok:
        return result
    if (rules_fallback or "").strip():
        return LLMResult(
            rules_fallback.strip(),
            "rules",
            model="rules",
            error=result.error,
            attempted=result.attempted,
        )
    return result


def chat(
    messages: list[dict[str, str]],
    company: Optional[dict] = None,
    *,
    system: str = "",
    timeout: int = 60,
) -> LLMResult:
    """
    Simple chat: flatten messages into one prompt for provider-agnostic call.
    messages: [{role: user|assistant, content: ...}, ...]
    """
    parts: list[str] = []
    if system:
        parts.append(f"SYSTEM:\n{system.strip()}\n")
    for m in messages:
        role = (m.get("role") or "user").upper()
        parts.append(f"{role}:\n{(m.get('content') or '').strip()}\n")
    parts.append("ASSISTANT:")
    return generate("\n".join(parts), company, timeout=timeout)


def extract_json_object(text: str) -> Optional[dict[str, Any]]:
    """Pull first JSON object from LLM text."""
    import json

    if not text:
        return None
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else None
    except Exception:
        return None
