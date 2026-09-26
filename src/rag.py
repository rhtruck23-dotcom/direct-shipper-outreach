"""
Lightweight RAG v1 — context pack for prompts (no vector DB).

Packs: project scope + recent conversation + lead notes/remarks.
Optional simple TF-IDF ranking when comparing against a corpus of snippets.
True embedding/vector RAG can replace this later without changing call sites.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Optional

_TOKEN = re.compile(r"[a-z0-9]{2,}", re.I)


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text or "")]


def truncate(text: str, max_chars: int) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[: max(0, max_chars - 1)].rstrip() + "…"


def _snip_conversation(conversation: list, *, max_msgs: int = 6, max_each: int = 280) -> str:
    msgs = conversation or []
    recent = msgs[-max_msgs:]
    lines = []
    for m in recent:
        direction = m.get("direction") or "?"
        body = truncate(str(m.get("body") or m.get("subject") or ""), max_each)
        at = str(m.get("at") or "")[:19]
        if body:
            lines.append(f"[{at}] {direction}: {body}")
    return "\n".join(lines)


def _snip_notes_timeline(timeline: list, *, max_notes: int = 8, max_each: int = 200) -> str:
    notes = timeline or []
    recent = notes[-max_notes:]
    lines = []
    for n in recent:
        text = truncate(str(n.get("text") or ""), max_each)
        at = str(n.get("at") or "")[:19]
        if text:
            lines.append(f"[{at}] {text}")
    return "\n".join(lines)


def build_context_pack(
    *,
    project: Optional[dict] = None,
    lead: Optional[dict] = None,
    extra_snippets: Optional[list[str]] = None,
    max_chars: int = 3500,
) -> str:
    """
    Concatenate the most useful CRM/agent context with soft truncation.
    """
    sections: list[str] = []
    if project:
        scope = (project.get("scope") or "").strip()
        name = project.get("name") or ""
        ptype = project.get("project_type") or ""
        tone = project.get("tone_notes") or ""
        header = f"PROJECT: {name} ({ptype})"
        if tone:
            header += f"\nTone: {tone}"
        if scope:
            sections.append(f"{header}\nSCOPE:\n{truncate(scope, 1600)}")
        else:
            sections.append(header)

    if lead:
        bits = [
            f"Company: {lead.get('company_name') or ''}",
            f"Contact: {lead.get('contact_name') or ''}",
            f"Email: {lead.get('email') or ''}",
            f"State: {lead.get('state') or ''}",
            f"CRM status: {lead.get('crm_status') or ''}",
            f"Sales stage: {lead.get('sales_stage') or ''}",
            f"Priority: {lead.get('priority') or ''}",
        ]
        rem = (lead.get("remarks") or "").strip()
        notes = (lead.get("notes") or "").strip()
        if rem:
            bits.append(f"Remarks: {truncate(rem, 400)}")
        if notes:
            bits.append(f"Notes: {truncate(notes, 400)}")
        tl = _snip_notes_timeline(lead.get("notes_timeline") or [])
        if tl:
            bits.append(f"Notes timeline:\n{tl}")
        conv = _snip_conversation(lead.get("conversation") or [])
        if conv:
            bits.append(f"Recent conversation:\n{conv}")
        sections.append("LEAD:\n" + "\n".join(bits))

    for snip in extra_snippets or []:
        s = (snip or "").strip()
        if s:
            sections.append(truncate(s, 800))

    pack = "\n\n---\n\n".join(sections)
    return truncate(pack, max_chars)


def tfidf_rank(
    query: str,
    documents: list[str],
    *,
    top_k: int = 3,
) -> list[tuple[int, float]]:
    """
    Tiny TF-IDF scorer. Returns [(doc_index, score), ...] best first.
    Enough for outcome-learning pattern recall without a vector DB.
    """
    if not documents:
        return []
    q_toks = _tokens(query)
    if not q_toks:
        return [(i, 0.0) for i in range(min(top_k, len(documents)))]

    docs_toks = [_tokens(d) for d in documents]
    df: Counter[str] = Counter()
    for toks in docs_toks:
        for t in set(toks):
            df[t] += 1
    n = len(documents)
    idf = {t: math.log((1 + n) / (1 + c)) + 1.0 for t, c in df.items()}

    def vec(toks: list[str]) -> dict[str, float]:
        tf = Counter(toks)
        total = max(len(toks), 1)
        return {t: (tf[t] / total) * idf.get(t, 0.0) for t in tf}

    qv = vec(q_toks)

    def cosine(a: dict[str, float], b: dict[str, float]) -> float:
        keys = set(a) | set(b)
        dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in keys)
        na = math.sqrt(sum(v * v for v in a.values())) or 1e-9
        nb = math.sqrt(sum(v * v for v in b.values())) or 1e-9
        return dot / (na * nb)

    scored = [(i, cosine(qv, vec(toks))) for i, toks in enumerate(docs_toks)]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def select_similar_snippets(
    query: str,
    snippets: list[str],
    *,
    top_k: int = 3,
    min_score: float = 0.05,
) -> list[str]:
    ranked = tfidf_rank(query, snippets, top_k=top_k)
    out = []
    for i, score in ranked:
        if score < min_score and out:
            continue
        out.append(snippets[i])
    return out
