"""Company / org configuration for LogixTrek outreach."""
from __future__ import annotations

import json
import os
import shutil
from typing import Any

from .paths import COMPANY_DEFAULT, COMPANY_FILE

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def ensure_company_file() -> None:
    if not COMPANY_FILE.exists():
        shutil.copy(COMPANY_DEFAULT, COMPANY_FILE)


def load_company() -> dict[str, Any]:
    ensure_company_file()
    with open(COMPANY_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # Env overrides (never store secrets in committed defaults)
    if os.getenv("SMTP_PASSWORD"):
        cfg["smtp_password"] = os.getenv("SMTP_PASSWORD", "")
    if os.getenv("GOOGLE_PLACES_API_KEY"):
        cfg["google_places_api_key"] = os.getenv("GOOGLE_PLACES_API_KEY", "")
    return cfg


def save_company(cfg: dict[str, Any]) -> None:
    ensure_company_file()
    # Don't write env-only secrets back if blank and env has them
    to_save = dict(cfg)
    with open(COMPANY_FILE, "w", encoding="utf-8") as f:
        json.dump(to_save, f, indent=2)
