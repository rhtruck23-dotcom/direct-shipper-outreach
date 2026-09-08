"""QA for logistics vetting rules."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.vetting import filter_vetted, rule_vet_lead


def test_reject_broker():
    lead = rule_vet_lead({"company_name": "ABC Freight Broker LLC", "notes": "truck broker"})
    assert lead["vet_status"] == "reject"
    assert lead["vet_score"] <= 2


def test_qualify_produce():
    lead = rule_vet_lead(
        {
            "company_name": "Midwest Fresh Produce Packers",
            "notes": "cold storage produce distributor",
            "discovery_query": "produce packer in IL",
        }
    )
    assert lead["vet_score"] >= 7
    assert lead["vet_status"] == "qualified"


def test_filter_keeps_qualified():
    leads = [
        rule_vet_lead({"company_name": "Cold Storage Foods", "notes": "refrigerated distributor"}),
        rule_vet_lead({"company_name": "Bob's Trucking Company", "notes": "motor carrier"}),
    ]
    kept = filter_vetted(leads, min_score=6)
    names = [k["company_name"] for k in kept]
    assert "Cold Storage Foods" in names
    assert "Bob's Trucking Company" not in names
