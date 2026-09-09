"""Paste-lead validation — format + logistics vet (no LinkedIn scrape)."""
from __future__ import annotations

from src.paste_validate import split_validated, validate_paste_leads


def test_validate_blocks_bad_email_and_broker():
    leads = [
        {
            "company_name": "Blue Ridge Produce LLC",
            "email": "ops@blueridgeproduce.com",
            "freight_type": "Reefer",
            "notes": "cold storage produce packer",
        },
        {
            "company_name": "Fast Freight Broker Inc",
            "email": "desk@fastfreightbroker.com",
            "notes": "freight broker load board",
        },
        {
            "company_name": "Ghost Co",
            "email": "a@mailinator.com",
        },
    ]
    out = validate_paste_leads(leads, company={}, enrich_websites=False, use_llm=False)
    assert len(out) == 3
    by_email = {l["email"]: l for l in out}
    assert by_email["ops@blueridgeproduce.com"]["validation_ready"] is True
    assert by_email["desk@fastfreightbroker.com"]["validation_ready"] is False
    assert by_email["desk@fastfreightbroker.com"]["vet_status"] == "reject"
    assert by_email["a@mailinator.com"]["validation_ready"] is False
    assert by_email["a@mailinator.com"]["validation_status"] == "blocked"

    parts = split_validated(out)
    assert len(parts["blocked"]) >= 2
    assert len(parts["ready"]) >= 1
