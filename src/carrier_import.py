"""Import carriers from CSV / Excel / PDF into lead-shaped dicts."""
from __future__ import annotations

import csv
import io
import re
from typing import Any


EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")
MC_RE = re.compile(r"\bMC[-\s]?(\d{4,8})\b", re.I)
DOT_RE = re.compile(r"\bDOT[-\s]?(\d{4,9})\b", re.I)


ALIASES = {
    "company": "company_name",
    "company name": "company_name",
    "legal name": "company_name",
    "dba": "company_name",
    "carrier": "company_name",
    "carrier name": "company_name",
    "name": "contact_name",
    "contact": "contact_name",
    "contact name": "contact_name",
    "owner": "contact_name",
    "e-mail": "email",
    "email address": "email",
    "telephone": "phone",
    "tel": "phone",
    "mobile": "phone",
    "st": "state",
    "postal": "zip",
    "zipcode": "zip",
    "zip code": "zip",
    "mc": "mc_number",
    "mc#": "mc_number",
    "mc number": "mc_number",
    "docket": "mc_number",
    "dot": "dot_number",
    "dot#": "dot_number",
    "dot number": "dot_number",
    "usdót": "dot_number",
    "equipment": "equipment_type",
    "equipment type": "equipment_type",
    "truck": "equipment_type",
    "cdl": "cdl_class",
    "cdl class": "cdl_class",
    "years": "years_exp",
    "experience": "years_exp",
    "authority date": "authority_date",
    "add date": "authority_date",
    "lane": "lane_or_region",
    "region": "lane_or_region",
    "url": "website",
    "web": "website",
    "remark": "remarks",
    "note": "notes",
}

FIELDS = [
    "company_name",
    "contact_name",
    "email",
    "phone",
    "state",
    "county",
    "zip",
    "mc_number",
    "dot_number",
    "equipment_type",
    "cdl_class",
    "years_exp",
    "authority_date",
    "lane_or_region",
    "notes",
    "remarks",
    "source",
    "website",
]


def _map_header(raw_key: str) -> str | None:
    key = (raw_key or "").strip().lower()
    if key in ALIASES:
        return ALIASES[key]
    canon = key.replace(" ", "_")
    if canon in FIELDS:
        return canon
    return ALIASES.get(key)


def parse_carrier_csv(file_bytes: bytes) -> list[dict]:
    text = file_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []
    out = []
    for row in reader:
        mapped = {h: "" for h in FIELDS}
        for raw_key, val in row.items():
            if raw_key is None:
                continue
            canon = _map_header(raw_key)
            if canon and canon in mapped:
                mapped[canon] = (val or "").strip()
        if mapped.get("company_name") or mapped.get("email") or mapped.get("mc_number"):
            mapped["source"] = mapped.get("source") or "csv_import"
            out.append(mapped)
    return out


def parse_carrier_excel(file_bytes: bytes) -> list[dict]:
    try:
        import pandas as pd
    except ImportError as e:
        raise RuntimeError("pandas required for Excel import") from e
    try:
        df = pd.read_excel(io.BytesIO(file_bytes))
    except Exception as e:
        # openpyxl missing or bad file
        raise RuntimeError(
            f"Could not read Excel ({e}). Install openpyxl or export as CSV."
        ) from e
    # write to csv bytes then reuse mapper
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    rows = parse_carrier_csv(buf.getvalue().encode("utf-8"))
    for r in rows:
        r["source"] = "excel_import"
    return rows


def extract_carriers_from_pdf_text(text: str) -> list[dict]:
    """Best-effort scrape of MC/DOT/email/phone blocks from PDF text."""
    text = text or ""
    emails = EMAIL_RE.findall(text)
    phones = PHONE_RE.findall(text)
    mcs = MC_RE.findall(text)
    dots = DOT_RE.findall(text)

    # Split on blank lines into chunks; attach identifiers found nearby
    chunks = [c.strip() for c in re.split(r"\n\s*\n", text) if c.strip()]
    out: list[dict] = []
    seen = set()

    for chunk in chunks[:80]:
        em = EMAIL_RE.search(chunk)
        ph = PHONE_RE.search(chunk)
        mc = MC_RE.search(chunk)
        dot = DOT_RE.search(chunk)
        if not (em or mc or dot):
            continue
        # first non-empty line as company guess
        lines = [ln.strip() for ln in chunk.splitlines() if ln.strip()]
        company = lines[0][:120] if lines else "Carrier from PDF"
        # avoid header-looking lines
        if company.lower().startswith(("page ", "table ", "fmcsa", "safer")):
            if len(lines) > 1:
                company = lines[1][:120]
        key = (em.group(0).lower() if em else "") or (
            f"mc:{mc.group(1)}" if mc else f"dot:{dot.group(1) if dot else company}"
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "company_name": company,
                "contact_name": "",
                "email": em.group(0) if em else "",
                "phone": ph.group(0) if ph else "",
                "mc_number": f"MC-{mc.group(1)}" if mc else "",
                "dot_number": f"DOT-{dot.group(1)}" if dot else "",
                "state": "",
                "source": "pdf_import",
                "notes": chunk[:400],
            }
        )

    # If chunking found nothing but we have identifiers, build rows from lists
    if not out and (mcs or dots or emails):
        n = max(len(mcs), len(dots), len(emails), 1)
        for i in range(n):
            out.append(
                {
                    "company_name": f"Carrier {i + 1} from PDF",
                    "email": emails[i] if i < len(emails) else "",
                    "phone": phones[i] if i < len(phones) else "",
                    "mc_number": f"MC-{mcs[i]}" if i < len(mcs) else "",
                    "dot_number": f"DOT-{dots[i]}" if i < len(dots) else "",
                    "source": "pdf_import",
                }
            )
    return out


def parse_carrier_pdf(file_bytes: bytes) -> list[dict]:
    text = ""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(file_bytes))
        parts = []
        for page in reader.pages[:30]:
            parts.append(page.extract_text() or "")
        text = "\n".join(parts)
    except Exception as e:
        # Fallback: latin-1 decode may still catch emails in simple PDFs
        try:
            text = file_bytes.decode("latin-1", errors="ignore")
        except Exception:
            raise RuntimeError(f"Could not read PDF ({e}). Install pypdf or use CSV/Excel.") from e
    return extract_carriers_from_pdf_text(text)


def parse_carrier_upload(filename: str, file_bytes: bytes) -> list[dict]:
    name = (filename or "").lower()
    if name.endswith(".csv"):
        return parse_carrier_csv(file_bytes)
    if name.endswith((".xlsx", ".xls")):
        return parse_carrier_excel(file_bytes)
    if name.endswith(".pdf"):
        return parse_carrier_pdf(file_bytes)
    # try csv then excel
    try:
        return parse_carrier_csv(file_bytes)
    except Exception:
        return parse_carrier_excel(file_bytes)
