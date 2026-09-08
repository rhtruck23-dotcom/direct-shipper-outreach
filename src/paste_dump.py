"""
Paste-dump parser — turn messy LinkedIn / ThomasNet / email / Notes copy-paste
into lead dicts. No website scraping — user pastes what they already copied.
"""
from __future__ import annotations

import re
from typing import Any, Optional

EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(
    r"(?:\+?1[\s\-.]?)?(?:\(?\d{3}\)?[\s\-.]?)\d{3}[\s\-.]?\d{4}"
)
URL_RE = re.compile(r"https?://[^\s<>\"']+|www\.[^\s<>\"']+", re.I)
LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/[^\s<>\"']+", re.I)
AT_COMPANY_RE = re.compile(
    r"(?:^|\n)\s*(.+?)\s*\n\s*(.+?)\s+at\s+(.+?)(?:\n|$)",
    re.I,
)
TITLE_AT_RE = re.compile(
    r"^(.+?)\s+at\s+(.+)$",
    re.I,
)

SKIP_LINES = re.compile(
    r"^(page\s+\d+|message|connect|follow|pending|mutual|"
    r"1st|2nd|3rd|degree|linkedin|see all|show more|"
    r"people also viewed|contact info)$",
    re.I,
)


def _clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", (line or "").strip())


def _norm_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return (raw or "").strip()


def _is_person_name(text: str) -> bool:
    t = _clean_line(text)
    if not t or len(t) > 60 or EMAIL_RE.search(t) or PHONE_RE.search(t):
        return False
    if SKIP_LINES.match(t):
        return False
    words = t.split()
    if not (2 <= len(words) <= 5):
        return False
    return all(w[:1].isalpha() for w in words if w)


def _is_companyish(text: str) -> bool:
    t = _clean_line(text)
    if not t or len(t) < 2 or len(t) > 120:
        return False
    if EMAIL_RE.search(t) or PHONE_RE.search(t) or SKIP_LINES.match(t):
        return False
    if _is_person_name(t) and " " in t and len(t.split()) <= 3:
        # Could still be a company (e.g. "Blue Ocean") — allow if has LLC/Inc/etc
        pass
    markers = (
        "llc",
        "inc",
        "corp",
        "co.",
        "company",
        "foods",
        "produce",
        "logistics",
        "warehouse",
        "distributor",
        "packing",
        "farms",
        "group",
        "industries",
    )
    low = t.lower()
    if any(m in low for m in markers):
        return True
    # Title Case multi-word without job words
    job = ("manager", "director", "buyer", "coordinator", "vp", "president", "owner")
    if any(j in low for j in job):
        return False
    return len(t.split()) >= 2 and t[0].isupper()


def parse_tabular_paste(text: str) -> list[dict[str, Any]]:
    """CSV / TSV / Excel-copied table with a header row."""
    from .leads import parse_import_csv

    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    if len(lines) < 2:
        return []
    header = lines[0].lower()
    if "\t" in lines[0] and ("email" in header or "company" in header or "name" in header):
        # convert TSV → CSV
        csv_text = "\n".join(
            ",".join('"' + c.replace('"', '""') + '"' for c in ln.split("\t"))
            for ln in lines
        )
        return parse_import_csv(csv_text.encode("utf-8"))
    if "," in lines[0] and ("email" in header or "company" in header):
        return parse_import_csv(text.encode("utf-8"))
    return []


def _chunk_blocks(text: str) -> list[str]:
    # Prefer blank-line cards; else sliding windows around each email
    raw = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = [b.strip() for b in re.split(r"\n\s*\n+", raw) if b.strip()]
    if len(blocks) >= 2:
        return blocks
    # Single blob with many emails — split around emails
    emails = list(EMAIL_RE.finditer(raw))
    if len(emails) <= 1:
        return [raw.strip()] if raw.strip() else []
    out = []
    for i, m in enumerate(emails):
        start = emails[i - 1].end() if i else 0
        end = emails[i + 1].start() if i + 1 < len(emails) else len(raw)
        # include some context before this email
        chunk_start = max(start, m.start() - 400)
        out.append(raw[chunk_start:end].strip())
    return out


def parse_block(block: str, defaults: Optional[dict] = None) -> Optional[dict[str, Any]]:
    defaults = defaults or {}
    lines = [_clean_line(ln) for ln in block.splitlines() if _clean_line(ln)]
    lines = [ln for ln in lines if not SKIP_LINES.match(ln)]
    if not lines:
        return None

    emails = EMAIL_RE.findall(block)
    phones = [_norm_phone(p) for p in PHONE_RE.findall(block)]
    urls = URL_RE.findall(block)
    linkedin = LINKEDIN_RE.findall(block)

    email = (emails[0] if emails else "").lower()
    phone = phones[0] if phones else ""
    website = ""
    for u in urls:
        if "linkedin.com" in u.lower():
            continue
        website = u if u.startswith("http") else f"https://{u}"
        break

    contact = ""
    company = ""

    # LinkedIn-style: Name \n Title at Company
    m = AT_COMPANY_RE.search(block)
    if m:
        contact = _clean_line(m.group(1))
        company = _clean_line(m.group(3))
    else:
        for ln in lines:
            tm = TITLE_AT_RE.match(ln)
            if tm and not EMAIL_RE.search(ln):
                left, right = _clean_line(tm.group(1)), _clean_line(tm.group(2))
                if _is_person_name(left) or any(
                    j in left.lower()
                    for j in ("manager", "director", "buyer", "procurement", "logistics")
                ):
                    if not contact and _is_person_name(left):
                        contact = left
                    company = company or right
                else:
                    company = company or right
                    if not contact and _is_person_name(left):
                        contact = left

    if not contact:
        for ln in lines[:4]:
            if _is_person_name(ln):
                contact = ln
                break

    if not company:
        for ln in lines:
            if contact and ln == contact:
                continue
            if _is_companyish(ln):
                company = ln
                break

    if not company and email:
        # domain → Company guess
        domain = email.split("@")[-1].split(".")[0]
        if domain and domain not in ("gmail", "yahoo", "hotmail", "outlook", "icloud", "aol"):
            company = domain.replace("-", " ").title()

    if not company and not email and not phone:
        return None

    if not company:
        company = contact or email or phone or "Unknown from paste"

    lead = {
        "company_name": company[:160],
        "contact_name": contact[:80],
        "email": email,
        "phone": phone,
        "state": (defaults.get("state") or "").upper()[:2],
        "zip": defaults.get("zip") or "",
        "freight_type": defaults.get("freight_type") or "Reefer",
        "lane_or_region": defaults.get("lane_or_region") or defaults.get("state") or "",
        "website": website,
        "notes": (defaults.get("notes") or "")[:200],
        "source": defaults.get("source") or "paste_dump",
        "remarks": "",
    }
    if linkedin:
        li = linkedin[0]
        if not li.startswith("http"):
            li = "https://" + li
        lead["notes"] = (lead["notes"] + f" | LinkedIn: {li}").strip(" |")

    mc = re.search(r"\bMC[-\s]?(\d{4,8})\b", block, re.I)
    dot = re.search(r"\bDOT[-\s]?(\d{4,9})\b", block, re.I)
    if mc:
        lead["mc_number"] = f"MC-{mc.group(1)}"
    if dot:
        lead["dot_number"] = f"DOT-{dot.group(1)}"

    # keep raw snippet short for audit
    snippet = " | ".join(lines[:6])[:300]
    if snippet:
        lead["remarks"] = f"Paste: {snippet}"
    return lead


def parse_paste_dump(
    text: str,
    *,
    state: str = "",
    zip_code: str = "",
    freight_type: str = "Reefer",
    source: str = "paste_dump",
) -> list[dict[str, Any]]:
    """
    Parse user-pasted mess into lead-shaped dicts (deduped by email, else company).
    """
    text = (text or "").strip()
    if not text:
        return []

    defaults = {
        "state": state,
        "zip": zip_code,
        "freight_type": freight_type,
        "source": source,
        "lane_or_region": state,
    }

    # 1) Structured table first
    tabular = parse_tabular_paste(text)
    if tabular:
        out = []
        for row in tabular:
            row = dict(row)
            row["state"] = row.get("state") or state
            row["zip"] = row.get("zip") or zip_code
            row["freight_type"] = row.get("freight_type") or freight_type
            row["source"] = row.get("source") or source
            if row.get("company_name") or row.get("email"):
                out.append(row)
        return _dedupe(out)

    # 2) Free-form / LinkedIn cards
    leads = []
    for block in _chunk_blocks(text):
        lead = parse_block(block, defaults)
        if lead:
            leads.append(lead)
    return _dedupe(leads)


def _dedupe(leads: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for lead in leads:
        email = (lead.get("email") or "").lower().strip()
        key = email or f"co:{(lead.get('company_name') or '').lower().strip()}"
        if not key or key == "co:":
            continue
        if key not in seen:
            seen[key] = lead
        else:
            old = seen[key]
            for f in ("contact_name", "phone", "website", "notes", "remarks"):
                if not old.get(f) and lead.get(f):
                    old[f] = lead[f]
    return list(seen.values())
