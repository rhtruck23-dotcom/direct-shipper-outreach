from src.lead_discovery_agent import candidate_to_lead_dict, Candidate, paca_manual_search_instructions


def test_paca_instructions_mention_manual():
    text = paca_manual_search_instructions("61455")
    assert "apps.mrp.usda.gov" in text
    assert "robots" in text.lower() or "NOT" in text or "manual" in text.lower() or "Copy" in text


def test_candidate_maps_fit_score():
    c = Candidate(
        company_name="Fresh Packers LLC",
        fit_score=82,
        fit_reason="Produce packer with outbound reefer lanes",
        email_guess="shipping@fresh.example",
        source="google_places",
    )
    d = candidate_to_lead_dict(c, "Reefer", "IL", "61455")
    assert d["vet_status"] == "qualified"
    assert d["fit_score"] == 82
    assert d["email"] == "shipping@fresh.example"
    assert d["needs_email"] is False
