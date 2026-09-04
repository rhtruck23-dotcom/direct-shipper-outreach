"""Smoke-import all modules (no Streamlit runtime needed)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_imports():
    import src.bot
    import src.campaign
    import src.company
    import src.emailer
    import src.leads
    import src.notify
    import src.places
    import src.schedule
    import src.templates

    assert src.templates.TEMPLATES[1]["subject"]
    assert src.company.load_company()["my_mc"] == "MC-1590829"
