"""
Logistics LLM vetting — score candidates as real direct-shipper prospects.

Uses Gemini when GEMINI_API_KEY / secrets are set.
Falls back to rule-based logistics scoring so the app still works.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

# Strong positive = likely shipper / freight owner
POSITIVE = [
    "produce",
    "packer",
    "cold storage",
    "refrigerat",
    "dairy",
    "meat",
    "frozen",
    "distributor",
    "distribution",
    "wholesale",
    "warehouse",
    "processor",
    "processing",
    "shipper",
    "beverage",
    "grocery",
    "food",
    "farm",
    "grower",
    "manufactur",
    "cpg",
]

# Hard reject = not a direct shipper you want to chase this way
NEGATIVE = [
    "freight broker",
    "truck broker",
    "load board",
    "3pl broker",
    "trucking company",
    "truck line",
    "motor carrier",
    "owner operator",
    "restaurant",
    "cafe",
    "diner",
    "motel",
    "hotel",
    "church",
    "school",
    "hospital",
    "lawyer",
    "attorney",
    "real estate",
    "insurance agent",
]


def _blob(lead: dict) -> str:
    return " ".join(
        str(lead.get(k) or "")
        for k in (
            "company_name",
            "notes",
            "address",
            "freight_type",
            "discovery_query",
            "website",
        )
    ).lower()


def rule_vet_lead(lead: dict) -> dict:
    """Deterministic logistics filter — always available."""
    text = _blob(lead)
    name = (lead.get("company_name") or "").lower()

    for bad in NEGATIVE:
        if bad in text or bad in name:
            return {
                **lead,
                "vet_score": 1,
                "vet_status": "reject",
                "vet_reason": f"Looks like non-shipper / broker noise ({bad})",
                "vet_method": "rules",
            }

    score = 4
    hits = []
    for good in POSITIVE:
        if good in text:
            score += 1
            hits.append(good)
    score = min(score, 10)

    if score >= 7:
        status = "qualified"
    elif score >= 5:
        status = "maybe"
    else:
        status = "weak"

    reason = (
        f"Matched shipper signals: {', '.join(hits[:5])}"
        if hits
        else "Weak shipper signals — review manually"
    )
    return {
        **lead,
        "vet_score": score,
        "vet_status": status,
        "vet_reason": reason,
        "vet_method": "rules",
    }


def _gemini_key(company: Optional[dict] = None) -> str:
    key = ""
    if company:
        key = (company.get("gemini_api_key") or "").strip()
    if not key:
        key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        try:
            import streamlit as st

            key = str(st.secrets.get("gemini_api_key", "") or "").strip()
        except Exception:
            key = ""
    return key


def llm_vet_batch(leads: list[dict], company: Optional[dict] = None) -> list[dict]:
    """
    Ask Gemini to score each candidate as a direct shipper prospect.
    On failure, falls back to rules per lead.
    """
    if not leads:
        return []

    key = _gemini_key(company)
    if not key:
        return [rule_vet_lead(l) for l in leads]

    # Cap payload size
    slim = []
    for i, l in enumerate(leads[:40]):
        slim.append(
            {
                "i": i,
                "company_name": l.get("company_name"),
                "address": l.get("address"),
                "phone": l.get("phone"),
                "website": l.get("website"),
                "query": l.get("discovery_query"),
                "freight_type": l.get("freight_type"),
            }
        )

    prompt = f"""You are a US trucking logistics specialist helping an owner-operator carrier
find DIRECT SHIPPERS (companies that own freight and hire carriers), NOT brokers and NOT other carriers.

Score each business 1-10 for "likely direct shipper / freight owner we should cold-email":
- 8-10: produce packer, cold storage, food/dairy/meat distributor, manufacturer shipping goods
- 5-7: possible wholesale / warehouse — maybe
- 1-4: restaurant, retail storefront only, broker, trucking company, unrelated

Return ONLY valid JSON array:
[{{"i":0,"score":8,"status":"qualified","reason":"short reason"}}]
status must be one of: qualified | maybe | reject | weak

Candidates:
{json.dumps(slim, ensure_ascii=False)}
"""

    try:
        import requests

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.0-flash:generateContent"
        )
        resp = requests.post(
            url,
            params={"key": key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=60,
        )
        if resp.status_code != 200:
            return [rule_vet_lead(l) for l in leads]

        data = resp.json()
        text = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        # Extract JSON array
        m = re.search(r"\[[\s\S]*\]", text)
        if not m:
            return [rule_vet_lead(l) for l in leads]
        arr = json.loads(m.group(0))
        by_i = {int(x["i"]): x for x in arr if "i" in x}

        out = []
        for i, lead in enumerate(leads):
            if i in by_i:
                x = by_i[i]
                score = int(x.get("score") or 5)
                status = str(x.get("status") or "maybe").lower()
                if status not in ("qualified", "maybe", "reject", "weak"):
                    status = "maybe" if score >= 5 else "weak"
                out.append(
                    {
                        **lead,
                        "vet_score": score,
                        "vet_status": status,
                        "vet_reason": str(x.get("reason") or "")[:240],
                        "vet_method": "gemini",
                    }
                )
            else:
                out.append(rule_vet_lead(lead))
        return out
    except Exception:
        return [rule_vet_lead(l) for l in leads]


def filter_vetted(
    leads: list[dict],
    min_score: int = 6,
    include_maybe: bool = True,
) -> list[dict]:
    out = []
    for l in leads:
        status = (l.get("vet_status") or "").lower()
        score = int(l.get("vet_score") or 0)
        if status == "reject":
            continue
        if score < min_score and not (include_maybe and status == "maybe" and score >= 5):
            if score < min_score:
                continue
        out.append(l)
    out.sort(key=lambda x: int(x.get("vet_score") or 0), reverse=True)
    return out
