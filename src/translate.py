"""
Email language helpers — English ↔ business Spanish via LLM failover.

Uses src.llm.complete() (gemini → groq → ollama → rules). Preserves merge
fields like {company_name}, MC/DOT numbers, emails, and proper names when possible.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

import streamlit as st

from .llm import LLMResult, complete, extract_json_object

LANG_LABELS = {"es": "Spanish", "en": "English"}

_MERGE_FIELD_RE = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")
_MC_RE = re.compile(r"\bMC[-\s]?\d{4,8}\b", re.I)
_DOT_RE = re.compile(r"\bDOT[-\s]?\d{5,10}\b", re.I)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def _protect_tokens(text: str) -> tuple[str, dict[str, str]]:
    """
    Replace merge fields / MC / DOT / emails with opaque tokens so the LLM
    is less likely to rewrite them. Restored after translation.
    """
    mapping: dict[str, str] = {}
    counter = 0

    def _sub(match: re.Match) -> str:
        nonlocal counter
        token = f"⟦LT{counter}⟧"
        mapping[token] = match.group(0)
        counter += 1
        return token

    out = text or ""
    for pattern in (_MERGE_FIELD_RE, _MC_RE, _DOT_RE, _EMAIL_RE):
        out = pattern.sub(_sub, out)
    return out, mapping


def _restore_tokens(text: str, mapping: dict[str, str]) -> str:
    out = text or ""
    for token, original in mapping.items():
        out = out.replace(token, original)
    return out


def _prompt_for(
    text: str,
    *,
    target_lang: str,
    is_email: bool = True,
) -> str:
    lang = LANG_LABELS.get(target_lang, target_lang)
    kind = "business email (freight / logistics outreach)" if is_email else "business note"
    return f"""You are a professional translator for U.S. trucking / freight outreach.

Translate the following {kind} into natural, polite {lang}.
Rules:
- Keep tone professional and concise (sales outreach, not slang).
- Preserve every token that looks like ⟦LT0⟧, ⟦LT1⟧, … exactly as written.
- Preserve proper company/person names, phone numbers, URLs, and dollar amounts.
- Do not add greetings/sign-offs that were not in the source.
- Return ONLY the translated text — no quotes, no preamble, no markdown fences.

SOURCE:
{text}
"""


def translate_text(
    text: str,
    *,
    target_lang: str = "es",
    company: Optional[dict] = None,
    is_email: bool = True,
) -> LLMResult:
    """
    Translate plain text to Spanish (`es`) or English (`en`).
    On total LLM failure, returns rules fallback = original text (provider='rules').
    """
    raw = (text or "").strip()
    if not raw:
        return LLMResult("", "none", error="empty text")

    target = (target_lang or "es").strip().lower()
    if target not in ("es", "en"):
        target = "es"

    protected, mapping = _protect_tokens(raw)
    prompt = _prompt_for(protected, target_lang=target, is_email=is_email)
    result = complete(
        prompt,
        company,
        timeout=60,
        rules_fallback=raw,
    )
    if not (result.text or "").strip():
        return result

    restored = _restore_tokens(result.text.strip(), mapping)
    # Drop accidental wrapping quotes
    if len(restored) >= 2 and restored[0] == restored[-1] and restored[0] in "\"'":
        restored = restored[1:-1].strip()
    return LLMResult(
        restored,
        result.provider,
        model=result.model,
        error=result.error,
        attempted=result.attempted,
    )


def translate_email_pair(
    subject: str,
    body: str,
    *,
    target_lang: str = "es",
    company: Optional[dict] = None,
) -> tuple[str, str, LLMResult]:
    """
    Translate subject + body together (one LLM call) for consistent tone.
    Returns (subject, body, llm_result). Falls back to per-field translate,
    then original text.
    """
    subj = subject or ""
    bod = body or ""
    if not subj.strip() and not bod.strip():
        return subj, bod, LLMResult("", "none", error="empty")

    target = (target_lang or "es").strip().lower()
    if target not in ("es", "en"):
        target = "es"
    lang = LANG_LABELS.get(target, target)

    prot_s, map_s = _protect_tokens(subj)
    prot_b, map_b = _protect_tokens(bod)
    prompt = f"""You translate logistics outreach emails into natural business {lang}.

Return ONLY valid JSON (no markdown):
{{"subject":"...","body":"..."}}

Rules:
- Preserve ⟦LTn⟧ tokens exactly.
- Preserve names, MC/DOT numbers, emails, URLs, dollar amounts.
- Keep professional freight/sales tone. Do not invent new content.

SUBJECT:
{prot_s}

BODY:
{prot_b}
"""
    result = complete(prompt, company, timeout=75, rules_fallback="")
    data = extract_json_object(result.text) if result.ok else None
    if isinstance(data, dict) and (data.get("subject") is not None or data.get("body") is not None):
        out_s = _restore_tokens(str(data.get("subject") or subj).strip(), map_s)
        out_b = _restore_tokens(str(data.get("body") or bod).strip(), map_b)
        return out_s, out_b, result

    # Fallback: translate fields separately
    rs = translate_text(subj, target_lang=target, company=company) if subj.strip() else LLMResult(subj, "rules")
    rb = translate_text(bod, target_lang=target, company=company) if bod.strip() else LLMResult(bod, "rules")
    via = rb.provider if rb.ok else rs.provider
    return (
        rs.text if rs.text else subj,
        rb.text if rb.text else bod,
        LLMResult(
            (rb.text or rs.text or ""),
            via or "rules",
            model=rb.model or rs.model,
            error=rb.error or rs.error,
            attempted=rb.attempted or rs.attempted,
        ),
    )


def _store_original(key_prefix: str, subject: str, body: str) -> None:
    st.session_state[f"{key_prefix}_lang_orig_subj"] = subject
    st.session_state[f"{key_prefix}_lang_orig_body"] = body


def render_email_lang_toolbar(  # pragma: no cover
    *,
    key_prefix: str,
    company: Optional[dict] = None,
    subject_key: Optional[str] = None,
    body_key: Optional[str] = None,
    show_to_spanish: bool = True,
    show_to_english: bool = False,
    side_by_side: bool = True,
    subject_value: Optional[str] = None,
    body_value: Optional[str] = None,
) -> dict[str, Any]:
    """
    Streamlit toolbar: Convert to Spanish / Convert to English.

    Writes translated text into `subject_key` / `body_key` session state (widget keys)
    when provided; otherwise stores under `{key_prefix}_translated_*`.

    Returns {"changed": bool, "subject": str, "body": str, "provider": str}.
    """
    cols = st.columns([1, 1, 2] if (show_to_spanish and show_to_english) else [1, 3])
    changed = False
    out_subj = ""
    out_body = ""
    provider = ""

    def _current_subject() -> str:
        if subject_value is not None:
            return subject_value
        if subject_key and subject_key in st.session_state:
            return str(st.session_state.get(subject_key) or "")
        return str(st.session_state.get(f"{key_prefix}_translated_subj") or "")

    def _current_body() -> str:
        if body_value is not None:
            return body_value
        if body_key and body_key in st.session_state:
            return str(st.session_state.get(body_key) or "")
        return str(st.session_state.get(f"{key_prefix}_translated_body") or "")

    def _apply(target: str) -> None:
        nonlocal changed, out_subj, out_body, provider
        cur_s = _current_subject()
        cur_b = _current_body()
        if not (cur_s.strip() or cur_b.strip()):
            st.warning("Nothing to translate — enter subject/body first.")
            return
        _store_original(key_prefix, cur_s, cur_b)
        new_s, new_b, result = translate_email_pair(
            cur_s, cur_b, target_lang=target, company=company
        )
        out_subj, out_body, provider = new_s, new_b, result.provider
        if subject_key:
            st.session_state[subject_key] = new_s
        else:
            st.session_state[f"{key_prefix}_translated_subj"] = new_s
        if body_key:
            st.session_state[body_key] = new_b
        else:
            st.session_state[f"{key_prefix}_translated_body"] = new_b
        st.session_state[f"{key_prefix}_lang_via"] = result.provider
        st.session_state[f"{key_prefix}_lang_target"] = target
        changed = True
        label = LANG_LABELS.get(target, target)
        if result.provider == "rules":
            st.info(f"Translated to {label} via rules fallback (LLM unavailable).")
        else:
            st.success(f"Converted to {label} (via {result.provider}). Edit before send.")
        st.rerun()

    idx = 0
    if show_to_spanish:
        if cols[idx].button(
            "🇪🇸 Convert to Spanish",
            key=f"{key_prefix}_to_es",
            help="Translate subject/body to natural business Spanish (LLM failover).",
        ):
            _apply("es")
        idx += 1
    if show_to_english:
        if cols[idx].button(
            "🇬🇧 Convert to English",
            key=f"{key_prefix}_to_en",
            help="Translate Spanish (or other) text to English.",
        ):
            _apply("en")

    via = st.session_state.get(f"{key_prefix}_lang_via")
    if via:
        st.caption(f"Last language convert via **{via}** — edit freely before send.")

    if side_by_side:
        orig_s = st.session_state.get(f"{key_prefix}_lang_orig_subj")
        orig_b = st.session_state.get(f"{key_prefix}_lang_orig_body")
        if orig_b or orig_s:
            with st.expander("Original (before translate)", expanded=False):
                if orig_s:
                    st.markdown(f"**Subject:** {orig_s}")
                if orig_b:
                    st.code(orig_b)

    return {
        "changed": changed,
        "subject": out_subj,
        "body": out_body,
        "provider": provider,
    }


def render_inbound_translate(  # pragma: no cover
    *,
    key_prefix: str,
    inbound_key: str,
    company: Optional[dict] = None,
    inbound_value: Optional[str] = None,
) -> None:
    """Convert pasted inbound reply to English (in-place on the text_area key)."""
    if st.button(
        "🇬🇧 Convert to English",
        key=f"{key_prefix}_inbound_en",
        help="Translate a Spanish (or other) inbound reply to English.",
    ):
        cur = (
            inbound_value
            if inbound_value is not None
            else str(st.session_state.get(inbound_key) or "")
        )
        if not cur.strip():
            st.warning("Paste their reply first.")
            return
        st.session_state[f"{key_prefix}_inbound_orig"] = cur
        result = translate_text(cur, target_lang="en", company=company, is_email=True)
        st.session_state[inbound_key] = result.text or cur
        st.session_state[f"{key_prefix}_inbound_via"] = result.provider
        st.rerun()

    orig = st.session_state.get(f"{key_prefix}_inbound_orig")
    if orig:
        with st.expander("Original inbound (before English)", expanded=False):
            st.code(orig)


def render_preview_translate(  # pragma: no cover
    subject: str,
    body: str,
    *,
    key_prefix: str,
    company: Optional[dict] = None,
) -> None:
    """
    For read-only email previews (st.code): Convert to Spanish and show
    editable side-by-side / replace draft the user can copy or tweak.
    """
    st.markdown(f"**{subject}**")
    st.code(body)
    c1, c2 = st.columns(2)
    if c1.button("🇪🇸 Convert to Spanish", key=f"{key_prefix}_prev_es"):
        new_s, new_b, result = translate_email_pair(
            subject, body, target_lang="es", company=company
        )
        st.session_state[f"{key_prefix}_prev_subj"] = new_s
        st.session_state[f"{key_prefix}_prev_body"] = new_b
        st.session_state[f"{key_prefix}_prev_via"] = result.provider
        st.session_state[f"{key_prefix}_prev_orig_subj"] = subject
        st.session_state[f"{key_prefix}_prev_orig_body"] = body
        st.rerun()
    if c2.button("🇬🇧 Convert to English", key=f"{key_prefix}_prev_en"):
        new_s, new_b, result = translate_email_pair(
            subject, body, target_lang="en", company=company
        )
        st.session_state[f"{key_prefix}_prev_subj"] = new_s
        st.session_state[f"{key_prefix}_prev_body"] = new_b
        st.session_state[f"{key_prefix}_prev_via"] = result.provider
        st.session_state[f"{key_prefix}_prev_orig_subj"] = subject
        st.session_state[f"{key_prefix}_prev_orig_body"] = body
        st.rerun()

    tr_body = st.session_state.get(f"{key_prefix}_prev_body")
    if tr_body is not None:
        via = st.session_state.get(f"{key_prefix}_prev_via") or ""
        st.caption(f"Editable translation (via {via}) — copy or tweak before sending elsewhere.")
        left, right = st.columns(2)
        with left:
            st.markdown("**Original**")
            st.code(st.session_state.get(f"{key_prefix}_prev_orig_body") or body)
        with right:
            st.markdown("**Translation**")
            st.text_input(
                "Subject (translated)",
                key=f"{key_prefix}_prev_subj",
            )
            st.text_area(
                "Body (translated)",
                height=180,
                key=f"{key_prefix}_prev_body",
            )
