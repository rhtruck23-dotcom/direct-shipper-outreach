"""Paste-dump parser tests — LinkedIn-ish blobs, tables, dedupe."""
from __future__ import annotations

from src.paste_dump import parse_paste_dump


def test_linkedin_style_block():
    text = """
Jordan Lee
Procurement Manager at Blue Ridge Produce LLC
jordan@blueridgeproduce.com
(540) 555-0199
Richmond, Virginia

Sam Ortiz
Logistics Director at Chesapeake Cold Storage
sam.ortiz@chesapeakecold.com
804-555-0100
"""
    leads = parse_paste_dump(text, state="VA", freight_type="Reefer")
    assert len(leads) >= 2
    emails = {l["email"] for l in leads}
    assert "jordan@blueridgeproduce.com" in emails
    assert any("Blue Ridge" in (l.get("company_name") or "") for l in leads)


def test_tsv_table_paste():
    text = "company_name\tcontact_name\temail\tstate\nAcme Foods\tPat\tpat@acme.com\tVA\n"
    leads = parse_paste_dump(text, state="VA")
    assert len(leads) == 1
    assert leads[0]["email"] == "pat@acme.com"
    assert leads[0]["company_name"] == "Acme Foods"


def test_email_only_infers_company():
    text = "Reach out to ops@heartlanddairy.com about reefer lanes"
    leads = parse_paste_dump(text, state="IL")
    assert len(leads) == 1
    assert leads[0]["email"] == "ops@heartlanddairy.com"
    assert "Heartlanddairy" in leads[0]["company_name"] or "heartland" in leads[0]["company_name"].lower()


def test_filter_and_csv():
    from src.paste_dump import filter_paste_leads, leads_to_csv_bytes

    leads = [
        {"company_name": "A", "email": "a@a.com", "phone": ""},
        {"company_name": "B Produce", "email": "", "phone": "555"},
        {"company_name": "C", "email": "c@c.com", "phone": "555"},
    ]
    assert len(filter_paste_leads(leads, require_email=True)) == 2
    assert len(filter_paste_leads(leads, keyword="produce")) == 1
    raw = leads_to_csv_bytes(leads)
    assert b"company_name" in raw and b"a@a.com" in raw
