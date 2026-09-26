"""
Unified LLM interface — optional free/local providers.

Providers:
  - gemini  (Google AI Studio key)
  - ollama  (local Llama/Mistral via http://127.0.0.1:11434)
  - groq    (optional free-tier key)

Fallback chain (preferred → gemini → ollama → empty):
  Prefer company.llm_provider, then try remaining providers that have credentials.
  Callers supply rule-based fallback when generate() returns empty.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Optional

PROVIDERS = ("gemini", "ollama", "groq")
DEFAULT_OLLAMA_MODEL = "llama3.2"
OLLAMA_BASE = "http://127.0.0.1:11434"


@dataclass
class LLMResult:
    text: str
    provider: str  # gemini | ollama | groq | none
    model: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool((self.text or "").strip())


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
    raw = ""
    if company:
        raw = (company.get("llm_provider") or "").strip().lower()
    if not raw:
        raw = (_secret("llm_provider") or "gemini").strip().lower()
    if raw not in PROVIDERS:
        return "gemini"
    return raw


def ollama_model(company: Optional[dict] = None) -> str:
    if company:
        m = (company.get("ollama_model") or "").strip()
        if m:
            return m
    return (_secret("ollama_model") or DEFAULT_OLLAMA_MODEL).strip() or DEFAULT_OLLAMA_MODEL


def provider_available(name: str, company: Optional[dict] = None) -> bool:
    name = (name or "").strip().lower()
    if name == "gemini":
        return bool(gemini_key(company))
    if name == "groq":
        return bool(groq_key(company))
    if name == "ollama":
        return True  # try localhost; call may fail → next in chain
    return False


def fallback_chain(company: Optional[dict] = None) -> list[str]:
    """preferred → gemini → ollama → (groq if keyed). Deduped."""
    pref = preferred_provider(company)
    ordered = [pref, "gemini", "ollama"]
    if groq_key(company):
        ordered.append("groq")
    seen: set[str] = set()
    out: list[str] = []
    for p in ordered:
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


def _call_gemini(prompt: str, key: str, *, timeout: int = 60) -> str:
    import requests

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.0-flash:generateContent"
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
    model: str = "llama-3.1-8b-instant",
    timeout: int = 60,
) -> str:
    import requests

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
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
    try:
        if name == "gemini":
            key = gemini_key(company)
            if not key:
                return LLMResult("", "none", error="no gemini key")
            text = _call_gemini(prompt, key, timeout=timeout)
            return LLMResult(text, "gemini" if text else "none", model="gemini-2.0-flash",
                             error="" if text else "gemini empty")
        if name == "ollama":
            model = ollama_model(company)
            text = _call_ollama(prompt, model, timeout=timeout)
            return LLMResult(text, "ollama" if text else "none", model=model,
                             error="" if text else "ollama unavailable")
        if name == "groq":
            key = groq_key(company)
            if not key:
                return LLMResult("", "none", error="no groq key")
            text = _call_groq(prompt, key, timeout=timeout)
            return LLMResult(text, "groq" if text else "none", model="llama-3.1-8b-instant",
                             error="" if text else "groq empty")
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
    Try providers in fallback order. Returns first non-empty text.
    If all fail → LLMResult with provider='none' (caller uses rules).
    """
    chain = providers or fallback_chain(company)
    last_err = ""
    for name in chain:
        # Skip groq/gemini when no key (ollama always attempted if in chain)
        if name in ("gemini", "groq") and not provider_available(name, company):
            continue
        result = _try_provider(name, prompt, company, timeout=timeout)
        if result.ok:
            return result
        last_err = result.error or last_err
    return LLMResult("", "none", error=last_err or "all providers failed")


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
