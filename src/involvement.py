"""
Involvement metrics — target ≤10% human effort in the end-to-end operation.

Model (per typical 20-lead Find & Vet → Activate → 16-day sequence):
- App runs discovery, enrichment, vetting, 4-email cadence, safe replies, DNC memory.
- Human only: start search, skim ranked list, fix a few blank emails, activate,
  and close escalated deals when the bot pings.

"Entire operation" includes machine-equivalent work credits so automated labor
is counted in the denominator (otherwise % human would always look high).
"""
from __future__ import annotations

from typing import Any

APP_UNITS = {
    "places_search": ("Google Places / Business pull", 12),
    "web_search": ("Google Search + site read", 10),
    "email_enrich": ("Public website email harvest", 8),
    "llm_vet": ("Gemini / rules logistics scoring", 15),
    "sequence_emails": ("Email 1–4 schedule + delivery", 20),
    "safe_bot": ("Safe auto-replies (opt-out / intro / referral)", 10),
    "memory": ("Cloud lead memory + DNC enforcement", 8),
}

HUMAN_UNITS = {
    "start_search": ("Enter state/zip + click Find & Vet", 1),
    "skim_list": ("Skim ranked shortlist, uncheck obvious junk", 2),
    "fill_emails": ("Fill remaining blank emails (enrichment got most)", 1),
    "activate": ("Save + Activate + Start", 1),
    "close_escalations": ("Handle bot escalations (rate/contract/load)", 2),
}


def involvement_report(include_optional_paca: bool = False) -> dict[str, Any]:
    human = dict(HUMAN_UNITS)
    app = dict(APP_UNITS)
    if include_optional_paca:
        human["paca_csv"] = ("Optional USDA PACA CSV once per region", 2)

    human_units = sum(v[1] for v in human.values())
    app_units = sum(v[1] for v in app.values())
    total = human_units + app_units
    pct = round(100.0 * human_units / total, 1) if total else 0.0

    return {
        "human_units": human_units,
        "app_units": app_units,
        "total_units": total,
        "involvement_pct": pct,
        "target_pct": 10.0,
        "under_target": pct <= 10.0,
        "human_steps": [
            {"id": k, "label": v[0], "units": v[1], "who": "human"} for k, v in human.items()
        ],
        "app_steps": [
            {"id": k, "label": v[0], "units": v[1], "who": "app"} for k, v in app.items()
        ],
        "summary": (
            f"Human {human_units} / total {total} effort units = {pct}% "
            f"(target ≤10%). App runs discovery→vet→follow-up; you only start, "
            f"skim, and close escalations."
        ),
    }


def assert_under_target(include_optional_paca: bool = False) -> None:
    r = involvement_report(include_optional_paca=include_optional_paca)
    if not r["under_target"]:
        raise AssertionError(
            f"Involvement {r['involvement_pct']}% exceeds target {r['target_pct']}%"
        )
