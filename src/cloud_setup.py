"""Cloud secrets helpers — no Google/Sheets imports (safe on Cloud Hosting page)."""
from __future__ import annotations

import base64
import json
from typing import Any, Optional


def json_to_b64_secret(json_text: str) -> str:
    data = json.loads(json_text.strip())
    if data.get("type") != "service_account":
        raise ValueError("This does not look like a Google service account JSON file.")
    if "private_key" not in data or "client_email" not in data:
        raise ValueError("JSON is missing private_key or client_email.")
    compact = json.dumps(data, separators=(",", ":"))
    return base64.b64encode(compact.encode("utf-8")).decode("ascii")


def build_simple_secrets_toml(sheet_id: str, json_text: str) -> str:
    b64 = json_to_b64_secret(json_text)
    return (
        f'google_sheet_id = "{sheet_id.strip()}"\n'
        f"send_live_emails = false\n"
        f'gcp_sa_b64 = "{b64}"\n'
        "\n"
        "[company]\n"
        'my_company = "LogixTrek LLC"\n'
        'my_name = "LogixTrek Dispatch"\n'
        'my_phone = "(443) 891-8543"\n'
        'my_email = "accounts@logixtrek.com"\n'
        'my_mc = "MC-1590829"\n'
        'my_dot = "DOT-4146389"\n'
        'website = "https://www.logixtrek.com"\n'
        'physical_address = "1030 Derry Ln Apt 36, Macomb, IL 61455"\n'
        'equipment = "53\' Reefer (also Dry Van / Box capacity)"\n'
        'origin_area = "Macomb, IL / Midwest"\n'
        'owner_notify_email = "accounts@logixtrek.com"\n'
        'smtp_host = "smtp.gmail.com"\n'
        "smtp_port = 587\n"
        'smtp_user = "accounts@logixtrek.com"\n'
        'unsubscribe_note = "LogixTrek LLC | 1030 Derry Ln Apt 36, Macomb, IL 61455 | www.logixtrek.com | Reply STOP to opt out of future emails."\n'
    )


def secret_status() -> dict[str, Any]:
    keys: list[str] = []
    sheet_id = ""
    info: Optional[dict] = None
    err = ""
    try:
        import streamlit as st

        keys = list(st.secrets.keys())
        sheet_id = str(st.secrets.get("google_sheet_id", "") or "").strip()
        info = _gcp_from_secrets()
    except Exception as e:
        err = str(e)

    return {
        "keys": keys,
        "sheet_id_present": bool(sheet_id),
        "sheet_id_preview": (sheet_id[:8] + "...") if sheet_id else "",
        "gcp_loaded": bool(info),
        "gcp_client_email": (info or {}).get("client_email", ""),
        "cloud_ready": bool(sheet_id) and bool(info),
        "error": err,
    }


def _gcp_from_secrets() -> Optional[dict]:
    import streamlit as st

    b64 = st.secrets.get("gcp_sa_b64", None)
    if b64:
        raw = base64.b64decode(str(b64).strip()).decode("utf-8")
        return json.loads(raw)

    raw = st.secrets.get("gcp_service_account_json", None)
    if raw:
        if isinstance(raw, dict):
            return dict(raw)
        text = str(raw).strip()
        if text and text != "REPLACE_ME":
            return json.loads(text)

    if "gcp_service_account" in st.secrets:
        info = dict(st.secrets["gcp_service_account"])
        pk = info.get("private_key")
        if isinstance(pk, str) and "\\n" in pk:
            info["private_key"] = pk.replace("\\n", "\n")
        return info
    return None
