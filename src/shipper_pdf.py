"""
Parse National Shipper Contact List PDFs (NAME / NUMBER / EMAIL / PHONE / FAX layout).

Extracts a US state code from the trailing City, ST pattern in the NAME field
so users can filter before bulk-saving into the outreach pipeline.
"""
from __future__ import annotations

import io
import re
from typing import Any, Optional

EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(
    r"(?:\+?1[\s\-.]?)?(?:\(?\d{3}\)?[\s\-.]?)\d{3}[\s\-.]?\d{4}"
)
# PACA-ish license token between name and email
LICENSE_RE = re.compile(r"\b(21200[A-Z0-9]{3,5}|N/?A)\b", re.I)

# Full / alternate state names → USPS code
STATE_ALIASES = {
    "ALABAMA": "AL",
    "ALASKA": "AK",
    "ARIZONA": "AZ",
    "ARKANSAS": "AR",
    "CALIFORNIA": "CA",
    "COLORADO": "CO",
    "CONNECTICUT": "CT",
    "DELAWARE": "DE",
    "FLORIDA": "FL",
    "FLA": "FL",
    "GEORGIA": "GA",
    "HAWAII": "HI",
    "IDAHO": "ID",
    "ILLINOIS": "IL",
    "INDIANA": "IN",
    "IOWA": "IA",
    "KANSAS": "KS",
    "KENTUCKY": "KY",
    "LOUISIANA": "LA",
    "MAINE": "ME",
    "MARYLAND": "MD",
    "MASSACHUSETTS": "MA",
    "MICHIGAN": "MI",
    "MINNESOTA": "MN",
    "MISSISSIPPI": "MS",
    "MISSOURI": "MO",
    "MONTANA": "MT",
    "NEBRASKA": "NE",
    "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH",
    "NEW JERSEY": "NJ",
    "NEW MEXICO": "NM",
    "NEW YORK": "NY",
    "N.Y": "NY",
    "NY": "NY",
    "NORTH CAROLINA": "NC",
    "NORTH DAKOTA": "ND",
    "OHIO": "OH",
    "OKLAHOMA": "OK",
    "OREGON": "OR",
    "PENNSYLVANIA": "PA",
    "RHODE ISLAND": "RI",
    "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD",
    "TENNESSEE": "TN",
    "TEXAS": "TX",
    "UTAH": "UT",
    "VERMONT": "VT",
    "VIRGINIA": "VA",
    "WASHINGTON": "WA",
    "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI",
    "WYOMING": "WY",
    "DISTRICT OF COLUMBIA": "DC",
    "D.C": "DC",
    # Non-US markers we keep distinct (not US filter)
    "ONTARIO": "ON",
    "QUEBEC": "QC",
    "BRITISH COLUMBIA": "BC",
    "CD": "ON",  # common "ONTARIO, CD." shorthand in this PDF
    "CN": "ON",  # "ONTARIO, CN." variant
    "PE": "XX",  # Peru etc. — skip US filter
}

US_STATES = {
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
    "DC",
}

SKIP_LINE = re.compile(
    r"^(?:\d{1,2}/\d{1,2}/\d{2,4}|SHIPPER CONTACT LIST|NAME\s+NUMBER|"
    r"Page\s+\d+\s+of\s+\d+|E-MAIL\s+PHONE\s+FAX)$",
    re.I,
)


def _norm_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return (raw or "").strip()


def _fix_email(raw: str) -> str:
    e = (raw or "").strip()
    if not e or e.upper() in {"N/A", "NA", "NONE"}:
        return ""
    # Common OCR / PDF typo: comma instead of dot before TLD
    e = re.sub(r",([a-z]{2,})$", r".\1", e, flags=re.I)
    e = e.replace(" ", "")
    m = EMAIL_RE.search(e)
    return m.group(0).lower() if m else ""


def extract_state_from_name_blob(name_blob: str) -> tuple[str, str, str]:
    """
    Split 'COMPANY, CITY, ST.' into company, city, state.
    Returns (company_name, city, state_code).
    """
    blob = re.sub(r"\s+", " ", (name_blob or "").strip())
    blob = blob.rstrip(".,; ")
    if not blob:
        return "", "", ""

    # Try ", XX" or ", XX." at end (2-letter)
    m = re.search(r",\s*([A-Za-z.]{2,20})\.?$", blob)
    state = ""
    city = ""
    company = blob
    if m:
        raw_st = m.group(1).strip().upper().replace(".", "")
        # Could be FLA, NY, CA, MONTANA, ONTARIO, CD
        if raw_st in STATE_ALIASES:
            state = STATE_ALIASES[raw_st]
        elif len(raw_st) == 2 and raw_st.isalpha():
            state = raw_st
        else:
            # maybe full state with no alias hit
            state = STATE_ALIASES.get(raw_st, raw_st if len(raw_st) == 2 else "")

        before = blob[: m.start()].rstrip(" ,.")
        # Split city from company: last comma segment is city
        if "," in before:
            company, city = before.rsplit(",", 1)
            company = company.strip(" ,.")
            city = city.strip(" ,.")
            # "..., LEAMINGTON, ONTARIO" when state was CN/CD already mapped — city may be province
            if city.upper().replace(".", "") in STATE_ALIASES and STATE_ALIASES[
                city.upper().replace(".", "")
            ] == state:
                # city was actually the province name; pull real city from company
                if "," in company:
                    company, city = company.rsplit(",", 1)
                    company = company.strip(" ,.")
                    city = city.strip(" ,.")
        else:
            company = before
            city = ""
    else:
        # "KALISPELL, MONTANA" without trailing abbrev pattern already handled;
        # try last token full state name
        parts = [p.strip() for p in blob.split(",") if p.strip()]
        if len(parts) >= 2:
            last = parts[-1].upper().replace(".", "")
            if last in STATE_ALIASES or (len(last) == 2 and last.isalpha()):
                state = STATE_ALIASES.get(last, last)
                if len(parts) >= 3:
                    company = ", ".join(parts[:-2]).strip()
                    city = parts[-2].strip()
                else:
                    company = parts[0]
                    city = ""

    state = (state or "").upper().strip()
    if state == "XX":
        state = ""
    return company.strip(), city.strip(), state


def parse_shipper_contact_line(line: str) -> Optional[dict[str, Any]]:
    line = re.sub(r"\s+", " ", (line or "").strip())
    if not line or SKIP_LINE.match(line):
        return None

    # Prefer email anchor
    email_m = EMAIL_RE.search(line)
    email = ""
    left = line
    right = ""
    if email_m:
        email = _fix_email(email_m.group(0))
        left = line[: email_m.start()].strip()
        right = line[email_m.end() :].strip()
    else:
        # N/A email
        na = re.search(r"\bN/?A\b", line, re.I)
        if not na:
            return None
        left = line[: na.start()].strip()
        right = line[na.end() :].strip()
        email = ""

    # License token at end of left
    lic = ""
    lic_m = LICENSE_RE.search(left)
    if lic_m:
        lic = lic_m.group(1).upper()
        if lic in {"N/A", "NA"}:
            lic = ""
        name_blob = left[: lic_m.start()].strip(" ,.-")
    else:
        # last token might be license without match — drop trailing code-like token
        toks = left.rsplit(" ", 1)
        if len(toks) == 2 and re.match(r"^[A-Z0-9]{5,12}$", toks[1], re.I):
            name_blob, lic = toks[0].strip(" ,.-"), toks[1].upper()
        else:
            name_blob = left.strip(" ,.-")

    company, city, state = extract_state_from_name_blob(name_blob)
    if not company:
        return None
    # Clean "INC KALISPELL" style city leftovers
    if city.upper().startswith("INC "):
        city = city[4:].strip()
        if not company.upper().endswith("INC") and not company.upper().endswith("INC."):
            company = f"{company}, INC"

    phones = PHONE_RE.findall(right)
    phone = _norm_phone(phones[0]) if phones else ""
    fax = _norm_phone(phones[1]) if len(phones) > 1 else ""

    return {
        "company_name": company,
        "contact_name": "",
        "email": email,
        "phone": phone,
        "state": state,
        "county": "",
        "zip": "",
        "city": city,
        "freight_type": "Reefer",
        "lane_or_region": state,
        "notes": f"city={city}" if city else "",
        "remarks": f"PACA# {lic}" if lic else "",
        "source": "national_shipper_pdf",
        "website": "",
        "paca_number": lic,
        "fax": fax,
    }


def extract_pdf_text(file_bytes: bytes) -> str:
    try:
        import pypdf
    except ImportError as e:
        raise RuntimeError("pypdf is required to read shipper PDFs") from e
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def parse_national_shipper_pdf(file_bytes: bytes) -> list[dict[str, Any]]:
    text = extract_pdf_text(file_bytes)
    return parse_national_shipper_text(text)


def parse_national_shipper_text(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in (text or "").splitlines():
        lead = parse_shipper_contact_line(raw)
        if not lead:
            continue
        key = (lead.get("email") or "").lower() or f"co:{(lead.get('company_name') or '').lower()}"
        if key in seen:
            continue
        seen.add(key)
        out.append(lead)
    return out


def filter_by_states(
    leads: list[dict],
    states: list[str],
    *,
    us_only: bool = False,
    require_email: bool = False,
) -> list[dict]:
    wanted = {s.strip().upper() for s in (states or []) if s and s.strip()}
    out = []
    for l in leads:
        st = (l.get("state") or "").upper().strip()
        if us_only and st not in US_STATES:
            continue
        if wanted and st not in wanted:
            continue
        if require_email and not (l.get("email") or "").strip():
            continue
        out.append(l)
    return out


def state_counts(leads: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for l in leads:
        st = (l.get("state") or "").upper().strip() or "(blank)"
        counts[st] = counts.get(st, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
