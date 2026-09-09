"""Tests for public-web email enrichment agent."""
from __future__ import annotations

from unittest.mock import patch

from src.email_agent import (
    _host_ok,
    _pick_email,
    _slug_candidates,
    enrich_lead_email,
    enrich_leads_missing_email,
)


def test_host_ok_blocks_search_engines():
    assert _host_ok("https://www.lifewayfoods.com/contact") is True
    assert _host_ok("https://duckduckgo.com/?q=test") is False
    assert _host_ok("https://www.linkedin.com/company/x") is False


def test_slug_candidates():
    slugs = _slug_candidates("LifeWay Foods, Inc.")
    assert any(s.endswith(".com") for s in slugs)
    assert any("lifeway" in s for s in slugs)


def test_pick_email_prefers_matching_domain():
    emails = ["sales@other.com", "info@lifewayfoods.com"]
    assert _pick_email(emails, "https://www.lifewayfoods.com") == "info@lifewayfoods.com"


def test_enrich_lead_email_already_has_email():
    lead = {"company_name": "X", "email": "a@b.com"}
    out = enrich_lead_email(lead, {})
    assert out["email"] == "a@b.com"
    assert out["email_enrich_status"] == "already_had_email"


def test_enrich_lead_email_fills_from_site(monkeypatch):
    lead = {"company_name": "LifeWay Foods", "state": "IL", "email": ""}

    monkeypatch.setattr(
        "src.email_agent.resolve_website",
        lambda *_a, **_k: "https://www.lifewayfoods.com",
    )
    monkeypatch.setattr(
        "src.email_agent.fetch_public_emails",
        lambda *_a, **_k: ["info@lifewayfoods.com", "sales@lifewayfoods.com"],
    )
    out = enrich_lead_email(lead, {})
    assert out["email"] == "info@lifewayfoods.com"
    assert out["email_enrich_status"] == "filled"
    assert "lifewayfoods.com" in (out.get("website") or "")


def test_batch_enrich_respects_max_and_state():
    leads = [
        {"company_name": "A Co", "state": "IL", "email": ""},
        {"company_name": "B Co", "state": "IL", "email": ""},
        {"company_name": "C Co", "state": "TX", "email": ""},
        {"company_name": "D Co", "state": "IL", "email": "d@d.com"},
    ]

    def fake_enrich(lead, company_cfg=None):
        out = dict(lead)
        if not out.get("email"):
            out["email"] = f"info@{out['company_name'][0].lower()}.com"
            out["email_enrich_status"] = "filled"
            out["website"] = "https://example.org"
        return out

    with patch("src.email_agent.enrich_lead_email", side_effect=fake_enrich):
        result = enrich_leads_missing_email(
            leads, {}, state="IL", max_leads=1, sleep_s=0
        )
    assert result["scanned"] == 1
    assert result["filled"] == 1
    assert result["missing_total"] == 2  # two IL blanks
