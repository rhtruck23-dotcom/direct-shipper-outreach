"""National shipper PDF parser tests."""
from __future__ import annotations

from src.shipper_pdf import (
    extract_state_from_name_blob,
    filter_by_states,
    parse_national_shipper_text,
    parse_shipper_contact_line,
    state_counts,
)


def test_extract_state_fresno_ca():
    company, city, state = extract_state_from_name_blob("1 SOURCE MKTING., FRESNO, CA.")
    assert state == "CA"
    assert "FRESNO" in city.upper() or city.upper() == "FRESNO"
    assert "SOURCE" in company.upper()


def test_parse_line_with_email():
    line = (
        "2 GIRLS PRODUCE CO., VINELAND, NJ. 21200HB0C sharondbax@aol.com "
        "856-692-6054 856-691-4274"
    )
    lead = parse_shipper_contact_line(line)
    assert lead is not None
    assert lead["state"] == "NJ"
    assert lead["email"] == "sharondbax@aol.com"
    assert lead["phone"].startswith("(856)")


def test_parse_text_batch_and_filter():
    text = """
SHIPPER CONTACT LIST
NAME NUMBER E-MAIL PHONE FAX
BLUE RIDGE PRODUCE, RICHMOND, VA. 21200AAAA ops@blueridge.com 804-555-0100 804-555-0101
TEXAS FRESH, MCALLEN, TX. 21200BBBB sales@txfresh.com 956-555-0100 956-555-0101
NO EMAIL FARMS, SALINAS, CA. 21200CCCC N/A 831-555-0100 831-555-0101
Page 1 of 1
"""
    leads = parse_national_shipper_text(text)
    assert len(leads) == 3
    counts = state_counts(leads)
    assert counts["VA"] == 1 and counts["TX"] == 1 and counts["CA"] == 1
    va = filter_by_states(leads, ["VA"], require_email=True)
    assert len(va) == 1
    assert va[0]["company_name"].startswith("BLUE RIDGE")
