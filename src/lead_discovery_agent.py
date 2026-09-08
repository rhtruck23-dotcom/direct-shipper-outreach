"""
Lead discovery agent (adapted from Claude handoff).

Sources (legal):
1. Google Places (New) — via our existing discovery module
2. Google Programmable Search + read company public websites
3. USDA PACA — MANUAL only (robots.txt blocks bots)
   https://apps.mrp.usda.gov/public_search

Does NOT scrape LinkedIn / ThomasNet / PACA live search.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

import requests

from .discovery import discover_candidates
from .enrich import enrich_lead, extract_emails_from_html

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

PACA_SEARCH_URL = "https://apps.mrp.usda.gov/public_search"
PACA_OVERVIEW_URL = "https://www.ams.usda.gov/rules-regulations/paca/epacaportal"


@dataclass
class Candidate:
    company_name: str
    address: str = ""
    phone: str = ""
    website: str = ""
    state: str = ""
    zip: str = ""
    county: str = ""
    source: str = ""
    raw_snippet: str = ""
    email_guess: str = ""
    fit_score: Optional[int] = None  # 0-100
    fit_reason: str = ""
    freight_type: str = ""
    id: str = ""


BUSINESS_TYPE_MAP = {
    "reefer": "cold storage warehouse OR produce distributor OR frozen food distributor OR dairy distributor",
    "dry van": "distribution center OR manufacturer OR wholesale distributor OR beverage distributor",
    "box truck": "local distributor OR warehouse OR fulfillment center OR wholesale grocery",
}


def paca_manual_search_instructions(state_or_zip: str) -> str:
    return (
        f"Open {PACA_SEARCH_URL} and search for '{state_or_zip}' "
        f"(State/Territory or zip / zip range). "
        f"Copy company name + city/state into a CSV, then Import in this app. "
        f"Overview: {PACA_OVERVIEW_URL}. "
        f"We do NOT auto-scrape this tool — its robots.txt blocks bots."
    )


def google_search_enrich(
    query: str,
    api_key: str,
    cse_id: str,
    max_results: int = 10,
) -> list[Candidate]:
    """Google Programmable Search (100 free queries/day)."""
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "q": query,
        "key": api_key,
        "cx": cse_id,
        "num": min(max_results, 10),
    }
    resp = requests.get(url, params=params, timeout=20)
    data = resp.json()
    if data.get("error"):
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    out: list[Candidate] = []
    for item in data.get("items", []):
        out.append(
            Candidate(
                company_name=(item.get("title") or "").split(" - ")[0].split(" | ")[0][:120],
                website=item.get("link", ""),
                raw_snippet=item.get("snippet", ""),
                source="google_search",
            )
        )
    return out


def fetch_site_contact_info(url: str, timeout: int = 12) -> tuple[str, str]:
    """Read company public page → email + text snippet for LLM."""
    if not url or "example.com" in url:
        return "", ""
    if not url.startswith("http"):
        url = "https://" + url
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": "LogixTrekLeadBot/1.0 (+https://www.logixtrek.com)"
            },
            allow_redirects=True,
        )
        if resp.status_code >= 400:
            return "", ""
        html = resp.text or ""
    except requests.RequestException:
        return "", ""

    emails = extract_emails_from_html(html, url)
    email = emails[0] if emails else ""
    # crude visible text
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()[:2000]
    return email, text


QUALIFY_PROMPT = """You are a freight logistics analyst helping a carrier find DIRECT \
shipper customers (no brokers). The carrier operates: {equipment}.

Decide how likely this company needs to hire a truck like this directly \
(produce packers, food distributors, cold storage, manufacturers, DCs = good; \
retail stores, restaurants, brokers, trucking companies = poor).

Company: {company_name}
Address: {address}
Public info found: {snippet}

Respond ONLY JSON:
{{"fit_score": <0-100 integer>, "reason": "<one sentence>"}}
"""


def qualify_candidate_gemini(
    candidate: Candidate,
    equipment: str,
    gemini_api_key: str,
    model: str = "gemini-2.0-flash",
) -> Candidate:
    prompt = QUALIFY_PROMPT.format(
        equipment=equipment,
        company_name=candidate.company_name,
        address=candidate.address,
        snippet=(candidate.raw_snippet[:1500] or "(no additional info found)"),
    )
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={gemini_api_key}"
    )
    try:
        resp = requests.post(
            url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=25
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        text = text.strip().strip("`").replace("json\n", "").replace("JSON\n", "").strip()
        m = re.search(r"\{[\s\S]*\}", text)
        parsed = json.loads(m.group(0) if m else text)
        candidate.fit_score = int(parsed.get("fit_score", 50))
        candidate.fit_reason = str(parsed.get("reason", ""))[:240]
    except Exception as e:
        candidate.fit_score = 50
        candidate.fit_reason = f"(could not auto-qualify: {type(e).__name__})"
    return candidate


def _places_to_candidates(rows: list[dict], freight_type: str) -> list[Candidate]:
    out = []
    for r in rows:
        out.append(
            Candidate(
                company_name=r.get("company_name") or "",
                address=r.get("address") or "",
                phone=r.get("phone") or "",
                website=r.get("website") or "",
                state=r.get("state") or "",
                zip=r.get("zip") or "",
                county=r.get("county") or "",
                source=r.get("source") or "google_places",
                raw_snippet=r.get("notes") or r.get("discovery_query") or "",
                email_guess=r.get("email") or "",
                freight_type=freight_type,
                id=r.get("id") or "",
            )
        )
    return out


def _dedupe(cands: list[Candidate]) -> list[Candidate]:
    seen: dict[str, Candidate] = {}
    for c in cands:
        key = (c.company_name or "").lower().strip()
        if not key:
            key = (c.website or c.phone or "").lower()
        if not key:
            continue
        if key not in seen:
            seen[key] = c
        else:
            # merge richer fields
            old = seen[key]
            if not old.email_guess and c.email_guess:
                old.email_guess = c.email_guess
            if not old.phone and c.phone:
                old.phone = c.phone
            if not old.website and c.website:
                old.website = c.website
            if c.raw_snippet and c.raw_snippet not in old.raw_snippet:
                old.raw_snippet = (old.raw_snippet + " " + c.raw_snippet).strip()
            if c.source and c.source not in old.source:
                old.source = f"{old.source}+{c.source}"
    return list(seen.values())


def candidate_to_lead_dict(c: Candidate, freight_type: str, state: str, zip_code: str) -> dict:
    score100 = int(c.fit_score or 0)
    vet_score = max(1, min(10, round(score100 / 10))) if c.fit_score is not None else 5
    if score100 >= 70:
        status = "qualified"
    elif score100 >= 50:
        status = "maybe"
    elif score100 > 0:
        status = "weak"
    else:
        status = "weak"
    return {
        "id": c.id or "",
        "company_name": c.company_name,
        "contact_name": "",
        "email": c.email_guess or "",
        "phone": c.phone or "",
        "state": c.state or state,
        "county": c.county or "",
        "zip": c.zip or zip_code,
        "freight_type": freight_type,
        "lane_or_region": c.address or f"{state} {zip_code}".strip(),
        "notes": f"Source: {c.source}",
        "remarks": f"Fit {score100}/100 — {c.fit_reason}"[:500],
        "source": c.source,
        "website": c.website or "",
        "address": c.address or "",
        "vet_score": vet_score,
        "vet_status": status,
        "vet_reason": c.fit_reason or "",
        "vet_method": "gemini" if c.fit_reason and "could not auto-qualify" not in c.fit_reason else "mixed",
        "fit_score": score100,
        "needs_email": not bool((c.email_guess or "").strip()),
    }


def discover_leads(
    state: str,
    zip_code: str,
    freight_type: str,
    equipment: str,
    config: dict,
    max_per_source: int = 15,
    progress_cb=None,
) -> list[dict]:
    """
    config keys:
      google_places_api_key, google_cse_api_key, google_cse_id,
      gemini_api_key, use_demo (bool)
    """

    def prog(msg: str):
        if progress_cb:
            progress_cb(msg)

    all_c: list[Candidate] = []
    location_str = zip_code or state
    ft = freight_type.lower()
    business_query_term = BUSINESS_TYPE_MAP.get(ft, "distribution center")
    use_demo = bool(config.get("use_demo"))

    # Source 1: Places (New) via our discovery module
    prog("Searching Google Places / Business…")
    places_key = (config.get("google_places_api_key") or "").strip()
    max_candidates = int(config.get("max_candidates") or max_per_source or 200)
    try:
        rows = discover_candidates(
            places_key,
            freight_type=freight_type,
            state=state,
            zip_code=zip_code,
            use_demo=use_demo or not places_key,
            max_per_query=20,
            max_total=max_candidates,
        )
        all_c += _places_to_candidates(rows, freight_type)
        prog(f"Places: {len(rows)} candidates")
    except Exception as e:
        prog(f"Places warning: {e}")

    # Source 2: Programmable Search + site read
    cse_key = (config.get("google_cse_api_key") or "").strip()
    cse_id = (config.get("google_cse_id") or "").strip()
    if cse_key and cse_id and not use_demo:
        prog("Running Google Search enrichment…")
        try:
            hits = google_search_enrich(
                f"{business_query_term} {location_str} contact",
                cse_key,
                cse_id,
                max_results=max_per_source,
            )
            for c in hits:
                if c.website:
                    email, snippet = fetch_site_contact_info(c.website)
                    c.email_guess = email
                    c.raw_snippet = (c.raw_snippet + " " + snippet).strip()
                    c.state = state
                    c.zip = zip_code
                    c.freight_type = freight_type
            all_c += hits
            prog(f"Search: {len(hits)} candidates")
        except Exception as e:
            prog(f"Search warning: {e}")

    all_c = _dedupe(all_c)

    # Website enrich for Places hits missing email
    prog("Reading public websites for emails…")
    enriched_c: list[Candidate] = []
    for i, c in enumerate(all_c):
        if use_demo:
            enriched_c.append(c)
            continue
        if c.email_guess or not c.website:
            enriched_c.append(c)
            continue
        prog(f"Site {i+1}/{len(all_c)}: {c.company_name[:40]}")
        as_lead = {
            "company_name": c.company_name,
            "email": c.email_guess,
            "website": c.website,
            "notes": c.raw_snippet,
        }
        as_lead = enrich_lead(as_lead)
        c.email_guess = as_lead.get("email") or c.email_guess
        if as_lead.get("notes"):
            c.raw_snippet = (c.raw_snippet + " " + as_lead["notes"]).strip()
        enriched_c.append(c)
    all_c = enriched_c

    # LLM qualify
    gem_key = (config.get("gemini_api_key") or "").strip()
    if gem_key and not use_demo:
        prog("Gemini logistics scoring…")
        for c in all_c:
            qualify_candidate_gemini(c, equipment, gem_key)
    else:
        # light heuristic score if no Gemini
        from .vetting import rule_vet_lead

        for c in all_c:
            tmp = rule_vet_lead(
                {
                    "company_name": c.company_name,
                    "notes": c.raw_snippet,
                    "address": c.address,
                    "discovery_query": business_query_term,
                    "website": c.website,
                }
            )
            c.fit_score = int(tmp.get("vet_score", 5)) * 10
            c.fit_reason = tmp.get("vet_reason") or ""

    all_c.sort(key=lambda x: x.fit_score or 0, reverse=True)
    return [
        candidate_to_lead_dict(c, freight_type, state, zip_code) for c in all_c
    ]
