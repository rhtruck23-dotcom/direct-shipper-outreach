"""Public-website enrichment — extract contact emails from company sites only."""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests

EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.I,
)

# Prefer logistics-ish inboxes when multiple found
PRIORITY_PREFIXES = (
    "shipping",
    "logistics",
    "transport",
    "traffic",
    "freight",
    "dispatch",
    "warehouse",
    "orders",
    "sales",
    "info",
    "contact",
)

SKIP_DOMAINS = (
    "example.com",
    "sentry.io",
    "wixpress.com",
    "cloudflare",
    "schema.org",
    "google.com",
    "gstatic.com",
    "facebook.com",
    "linkedin.com",
)


def _clean_emails(emails: list[str], site_host: str = "") -> list[str]:
    out = []
    for e in emails:
        e = e.strip().lower().rstrip(".")
        if any(bad in e for bad in SKIP_DOMAINS):
            continue
        if e.endswith((".png", ".jpg", ".gif", ".webp", ".css", ".js")):
            continue
        if site_host and site_host not in e.split("@")[-1] and not any(
            e.startswith(p + "@") for p in PRIORITY_PREFIXES
        ):
            # keep off-domain only if looks like a role inbox; still allow
            pass
        if e not in out:
            out.append(e)
    # rank
    def score(addr: str) -> int:
        local = addr.split("@")[0]
        for i, p in enumerate(PRIORITY_PREFIXES):
            if local.startswith(p):
                return 100 - i
        return 0

    return sorted(out, key=score, reverse=True)


def extract_emails_from_html(html: str, website: str = "") -> list[str]:
    host = urlparse(website).netloc.replace("www.", "") if website else ""
    found = EMAIL_RE.findall(html or "")
    # also mailto:
    found += re.findall(r"mailto:([^\"'?&\s>]+)", html or "", flags=re.I)
    return _clean_emails(found, host)


def fetch_public_emails(website: str, timeout: int = 12) -> list[str]:
    """Fetch homepage (+ /contact if linked) and return emails. Fail soft."""
    if not website or "example.com" in website:
        return []
    url = website.strip()
    if not url.startswith("http"):
        url = "https://" + url

    headers = {
        "User-Agent": "LogixTrekLeadBot/1.0 (+https://www.logixtrek.com; direct shipper outreach)"
    }
    emails: list[str] = []
    try:
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        if resp.status_code >= 400:
            return []
        html = resp.text or ""
        emails = extract_emails_from_html(html, url)

        # try a couple contact paths if none yet
        if not emails:
            for path in ("/contact", "/contact-us", "/about", "/about-us"):
                try:
                    c = requests.get(
                        urljoin(resp.url, path),
                        headers=headers,
                        timeout=timeout,
                        allow_redirects=True,
                    )
                    if c.status_code < 400:
                        emails = extract_emails_from_html(c.text or "", url)
                        if emails:
                            break
                except Exception:
                    continue
    except Exception:
        return []
    return emails[:5]


def enrich_lead(lead: dict) -> dict:
    """Add email from public website when missing."""
    out = dict(lead)
    if (out.get("email") or "").strip():
        return out
    emails = fetch_public_emails(out.get("website") or "")
    if emails:
        out["email"] = emails[0]
        extra = ", ".join(emails[1:3])
        note = out.get("notes") or ""
        out["notes"] = (note + f" | Web emails: {emails[0]}" + (f"; {extra}" if extra else "")).strip(" |")
        out["email_source"] = "website"
    else:
        out["email_source"] = "none"
    return out
