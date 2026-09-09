"""
Email enrichment agent — fill missing emails from public web sources only.

Strategy (in order):
1) If lead already has website → scrape public pages for emails
2) Google Programmable Search (when CSE keys set) → pick company site → scrape
3) Domain guess (companyname.com / .net / .org) → scrape
4) DuckDuckGo HTML search → first real company site (never search-engine pages) → scrape

Does NOT scrape LinkedIn / ThomasNet / Yellow Pages directories or bypass CAPTCHAs.
"""
from __future__ import annotations

import html
import re
import time
import urllib.parse
from typing import Any, Callable, Optional
from urllib.parse import urlparse

import requests

from .enrich import enrich_lead, fetch_public_emails

UA = "LogixTrekLeadBot/1.0 (+https://www.logixtrek.com; shipper email enrichment)"
EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)

SKIP_HOSTS = (
    "duckduckgo.com",
    "google.com",
    "bing.com",
    "yahoo.com",
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "yelp.com",
    "yellowpages.com",
    "mapquest.com",
    "wikipedia.org",
    "zoominfo.com",
    "dnb.com",
    "bloomberg.com",
    "crunchbase.com",
    "bbb.org",
    "gov",
    "fda.gov",
    "usda.gov",
)

LEGAL_WORDS = re.compile(
    r"\b(inc|llc|ltd|corp|corporation|company|co|the|plc|lp|llp|btu|rs|plt)\b",
    re.I,
)


def _norm_company(name: str) -> str:
    s = (name or "").lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = LEGAL_WORDS.sub(" ", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _slug_candidates(company: str) -> list[str]:
    base = _norm_company(company).replace(" ", "")
    if not base or len(base) < 3:
        return []
    alts = [base]
    # shorter slug without dairy/food noise words kept if leftover is long enough
    short = re.sub(
        r"(dairy|foods?|farms?|cheese|creamery|products?|international|usa|group)$",
        "",
        base,
    )
    if short and short != base and len(short) >= 4:
        alts.append(short)
    out = []
    for a in alts:
        for tld in (".com", ".net", ".org"):
            out.append(a + tld)
    return out


def _host_ok(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower().split("@")[-1].split(":")[0]
    except Exception:
        return False
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return False
    return not any(b in host for b in SKIP_HOSTS)


def _root_host(url: str) -> str:
    host = urlparse(url).netloc.lower().split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def _email_matches_site(email: str, site: str) -> bool:
    if not email or "@" not in email or not site:
        return False
    dom = email.split("@")[-1].lower()
    root = _root_host(site)
    return dom == root or dom.endswith("." + root)


def _pick_email(emails: list[str], site: str = "") -> str:
    if not emails:
        return ""
    if site:
        matched = [e for e in emails if _email_matches_site(e, site)]
        if matched:
            return matched[0]
        # accept role inboxes even if off-domain (rare)
        for e in emails:
            local = e.split("@")[0]
            if local in {"info", "sales", "contact", "orders", "shipping", "logistics"}:
                return e
        return ""
    return emails[0]


def _get(url: str, timeout: int = 12) -> str:
    resp = requests.get(
        url,
        headers={"User-Agent": UA},
        timeout=timeout,
        allow_redirects=True,
    )
    if resp.status_code >= 400:
        return ""
    return resp.text or ""


def find_website_via_cse(
    company: str,
    state: str,
    cse_key: str,
    cse_id: str,
) -> str:
    q = f'"{company}" {state} official website'.strip()
    url = "https://www.googleapis.com/customsearch/v1"
    params = {"q": q, "key": cse_key, "cx": cse_id, "num": 5}
    try:
        data = requests.get(url, params=params, timeout=20).json()
    except Exception:
        return ""
    if data.get("error"):
        return ""
    for item in data.get("items") or []:
        link = item.get("link") or ""
        if link and _host_ok(link):
            return link
    return ""


def find_website_via_ddg(company: str, state: str) -> str:
    q = urllib.parse.quote_plus(f"{company} {state} official website")
    url = f"https://html.duckduckgo.com/html/?q={q}"
    try:
        page = _get(url)
    except Exception:
        return ""
    # prefer uddg redirect targets
    for m in re.finditer(r'uddg=([^&"]+)', page):
        link = urllib.parse.unquote(html.unescape(m.group(1)))
        if link.startswith("http") and _host_ok(link):
            return link
    for m in re.finditer(r'href="(https?://[^"]+)"', page):
        link = html.unescape(m.group(1))
        if _host_ok(link):
            return link
    return ""


def find_website_by_domain_guess(company: str) -> str:
    for host in _slug_candidates(company):
        for scheme in ("https://", "http://"):
            url = scheme + host
            try:
                emails = fetch_public_emails(url, timeout=8)
                # even if no email, if site responds with content it's usable
                html_txt = _get(url, timeout=8)
                if html_txt and len(html_txt) > 400:
                    return url
                if emails:
                    return url
            except Exception:
                continue
    return ""


def resolve_website(lead: dict, company_cfg: Optional[dict] = None) -> str:
    existing = (lead.get("website") or "").strip()
    if existing and _host_ok(existing):
        return existing if existing.startswith("http") else "https://" + existing

    name = (lead.get("company_name") or "").strip()
    state = (lead.get("state") or "").strip()
    if not name:
        return ""

    cfg = company_cfg or {}
    cse_key = (cfg.get("google_cse_api_key") or "").strip()
    cse_id = (cfg.get("google_cse_id") or "").strip()
    if cse_key and cse_id:
        site = find_website_via_cse(name, state, cse_key, cse_id)
        if site:
            return site

    site = find_website_by_domain_guess(name)
    if site:
        return site

    return find_website_via_ddg(name, state)


def enrich_lead_email(
    lead: dict,
    company_cfg: Optional[dict] = None,
) -> dict:
    """
    Return a copy of lead with email/website filled when publicly found.
    Sets email_source / email_enrich_status for UI.
    """
    out = dict(lead)
    if (out.get("email") or "").strip():
        out["email_enrich_status"] = "already_had_email"
        return out

    site = resolve_website(out, company_cfg)
    if site:
        out["website"] = site
        emails = fetch_public_emails(site)
        picked = _pick_email(emails, site)
        if picked:
            out["email"] = picked
            out["email_source"] = "public_web_agent"
            out["email_enrich_status"] = "filled"
            rem = out.get("remarks") or ""
            tag = "email:public_web_agent"
            if tag not in rem:
                out["remarks"] = (rem + " | " + tag).strip(" |")
            return out

        # also run generic enrich_lead path
        enriched = enrich_lead(out)
        if (enriched.get("email") or "").strip():
            enriched["email_source"] = enriched.get("email_source") or "website"
            enriched["email_enrich_status"] = "filled"
            return enriched

    out["email_enrich_status"] = "not_found"
    return out


def enrich_leads_missing_email(
    leads: list[dict],
    company_cfg: Optional[dict] = None,
    *,
    state: str = "",
    max_leads: int = 40,
    sleep_s: float = 0.35,
    progress_cb: Optional[Callable[[str, float], None]] = None,
) -> dict[str, Any]:
    """
    Enrich in-place copies for leads missing email.
    Returns stats + updated lead dicts (not yet persisted).
    """
    st = (state or "").upper().strip()
    missing = [
        l
        for l in leads
        if not (l.get("email") or "").strip()
        and (l.get("company_name") or "").strip()
        and ((l.get("state") or "").upper() == st if st else True)
        and (l.get("status") or "") != "do_not_contact"
    ]
    batch = missing[: max(0, int(max_leads))]
    updated: list[dict] = []
    filled = 0
    not_found = 0

    for i, lead in enumerate(batch):
        if progress_cb:
            progress_cb(
                f"{i + 1}/{len(batch)} · {lead.get('company_name')}",
                (i + 1) / max(len(batch), 1),
            )
        result = enrich_lead_email(lead, company_cfg)
        if (result.get("email") or "").strip() and not (lead.get("email") or "").strip():
            filled += 1
            updated.append(result)
        else:
            not_found += 1
            if result.get("website") and not lead.get("website"):
                updated.append(result)
        if sleep_s:
            time.sleep(sleep_s)

    return {
        "scanned": len(batch),
        "missing_total": len(missing),
        "filled": filled,
        "not_found": not_found,
        "updated": updated,
        "has_cse": bool(
            (company_cfg or {}).get("google_cse_api_key")
            and (company_cfg or {}).get("google_cse_id")
        ),
    }
