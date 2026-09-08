"""
Role-based access control (RBAC) — scalable by module.

Super Admin (owner): full access to every module and every lead; only person
who can create/edit team members and assign leads.

Standard roles (Nurturer / Rep): CRUD only on modules granted + only leads
assigned to them. Unassigned leads stay owner-only.

Add a future module by registering it in MODULES — pages + permission checks
pick it up automatically.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Optional

from .paths import DATA_DIR

TEAM_JSON = DATA_DIR / "team_rbac.json"

# ---------------------------------------------------------------------------
# Module registry — extend here when you add the next product surface
# ---------------------------------------------------------------------------

ACTIONS = ("create", "read", "update", "delete")

MODULES: dict[str, dict[str, Any]] = {
    "dashboard": {
        "label": "Dashboard",
        "page": "Dashboard",
        "super_only": False,
        "default_actions": ["read"],
    },
    "leads": {
        "label": "Leads List",
        "page": "Leads List",
        "super_only": False,
        "default_actions": ["create", "read", "update", "delete"],
    },
    "find_leads": {
        "label": "Find Leads",
        "page": "Find Leads",
        "super_only": False,
        "default_actions": ["create", "read", "update"],
    },
    "pipeline": {
        "label": "Pipeline & Outreach",
        "page": "Pipeline & Outreach",
        "super_only": False,
        "default_actions": ["create", "read", "update"],
    },
    "inbox": {
        "label": "Inbox Bot",
        "page": "Inbox Bot",
        "super_only": False,
        "default_actions": ["create", "read", "update"],
    },
    "carrier_leads": {
        "label": "Carrier Leads",
        "page": "Carrier Leads",
        "super_only": False,
        "default_actions": ["create", "read", "update", "delete"],
    },
    "find_carriers": {
        "label": "Find Carriers",
        "page": "Find Carriers",
        "super_only": False,
        "default_actions": ["create", "read", "update"],
    },
    "carrier_pipeline": {
        "label": "Carrier Pipeline",
        "page": "Carrier Pipeline",
        "super_only": False,
        "default_actions": ["create", "read", "update"],
    },
    "carrier_inbox": {
        "label": "Carrier Inbox",
        "page": "Carrier Inbox",
        "super_only": False,
        "default_actions": ["create", "read", "update"],
    },
    "org_setup": {
        "label": "Org Setup",
        "page": "Org Setup",
        "super_only": True,
        "default_actions": ["create", "read", "update", "delete"],
    },
    "cloud": {
        "label": "Cloud Hosting",
        "page": "Cloud Hosting",
        "super_only": True,
        "default_actions": ["create", "read", "update", "delete"],
    },
    "help": {
        "label": "Help",
        "page": "Help",
        "super_only": False,
        "default_actions": ["read"],
    },
    "team_admin": {
        "label": "Team & Access",
        "page": None,  # lives inside Org Setup
        "super_only": True,
        "default_actions": ["create", "read", "update", "delete"],
    },
}

ROLE_PRESETS: dict[str, dict[str, Any]] = {
    "super_admin": {
        "label": "Super Admin",
        "see_all_leads": True,
        "manage_team": True,
    },
    "manager": {
        "label": "Manager",
        "see_all_leads": False,
        "manage_team": False,
        "modules": {
            "dashboard": ["read"],
            "leads": ["create", "read", "update", "delete"],
            "find_leads": ["create", "read", "update"],
            "pipeline": ["create", "read", "update"],
            "inbox": ["create", "read", "update"],
            "carrier_leads": ["create", "read", "update", "delete"],
            "find_carriers": ["create", "read", "update"],
            "carrier_pipeline": ["create", "read", "update"],
            "carrier_inbox": ["create", "read", "update"],
            "help": ["read"],
        },
    },
    "nurturer": {
        "label": "Shipper Nurturer",
        "see_all_leads": False,
        "manage_team": False,
        "modules": {
            "dashboard": ["read"],
            "leads": ["create", "read", "update"],
            "pipeline": ["read", "update"],
            "inbox": ["read", "update"],
            "help": ["read"],
        },
    },
    "carrier_recruiter": {
        "label": "Carrier Recruiter",
        "see_all_leads": False,
        "manage_team": False,
        "modules": {
            "dashboard": ["read"],
            "carrier_leads": ["create", "read", "update"],
            "find_carriers": ["create", "read", "update"],
            "carrier_pipeline": ["read", "update"],
            "carrier_inbox": ["read", "update"],
            "help": ["read"],
        },
    },
    "rep": {
        "label": "Rep",
        "see_all_leads": False,
        "manage_team": False,
        "modules": {
            "dashboard": ["read"],
            "leads": ["read", "update"],
            "pipeline": ["read", "update"],
            "inbox": ["read", "update"],
            "help": ["read"],
        },
    },
}

SUPER_ADMIN_ID = "super_admin"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def hash_pin(pin: str, salt: Optional[str] = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(8)
    digest = hashlib.sha256(f"{salt}:{pin}".encode("utf-8")).hexdigest()
    return digest, salt


def verify_pin(pin: str, pin_hash: str, salt: str) -> bool:
    if not pin or not pin_hash or not salt:
        return False
    digest, _ = hash_pin(pin, salt)
    return secrets.compare_digest(digest, pin_hash)


def _blank_state() -> dict[str, Any]:
    return {
        "version": 1,
        "super_admin": {
            "id": SUPER_ADMIN_ID,
            "name": "Super Admin",
            "email": "accounts@logixtrek.com",
            "role": "super_admin",
            "active": True,
            "pin_hash": "",
            "pin_salt": "",
            "module_access": {},  # ignored — full access
        },
        "users": [],
        "updated_at": _utc_now(),
    }


def _open_rbac_worksheet(*, create_if_missing: bool = False):
    """Optional Google Sheet tab for team RBAC (same workbook as leads)."""
    from . import storage

    if not storage.using_cloud():
        return None
    import gspread

    info = storage._get_gcp_info()
    sheet_id = storage._get_sheet_id()
    if not info or not sheet_id:
        return None
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    client = gspread.authorize(creds)
    sh = client.open_by_key(sheet_id)
    try:
        return sh.worksheet("rbac")
    except gspread.WorksheetNotFound:
        if not create_if_missing:
            return None
        ws = sh.add_worksheet(title="rbac", rows=20, cols=2)
        ws.update(
            "A1:B2",
            [["key", "value"], ["state_json", json.dumps(_blank_state())]],
            value_input_option="USER_ENTERED",
        )
        return ws


def load_rbac_state() -> dict[str, Any]:
    state = None
    try:
        from . import storage

        if storage.using_cloud():
            ws = _open_rbac_worksheet(create_if_missing=False)
            if ws is not None:
                rows = ws.get_all_records()
                for row in rows:
                    if str(row.get("key", "")).strip() == "state_json":
                        raw = row.get("value") or ""
                        if raw:
                            state = json.loads(raw)
                        break
    except Exception:
        state = None

    if state is None and TEAM_JSON.exists():
        try:
            with open(TEAM_JSON, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            state = None

    if not isinstance(state, dict):
        state = _blank_state()
    # ensure shape
    base = _blank_state()
    base.update({k: state.get(k, base[k]) for k in base})
    if not isinstance(base.get("users"), list):
        base["users"] = []
    if not isinstance(base.get("super_admin"), dict):
        base["super_admin"] = _blank_state()["super_admin"]
    base["super_admin"]["id"] = SUPER_ADMIN_ID
    base["super_admin"]["role"] = "super_admin"
    base["super_admin"]["active"] = True
    return base


def save_rbac_state(state: dict[str, Any]) -> None:
    state = deepcopy(state)
    state["updated_at"] = _utc_now()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(TEAM_JSON, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

    try:
        from . import storage

        if storage.using_cloud():
            ws = _open_rbac_worksheet(create_if_missing=True)
            if ws is not None:
                payload = json.dumps(state, ensure_ascii=False)
                ws.clear()
                ws.update("A1:B2", [["key", "value"], ["state_json", payload]])
    except Exception:
        # Local file remains source of truth for session if Sheets write fails
        pass


def ensure_super_admin_pin(state: dict[str, Any], pin: str) -> dict[str, Any]:
    """Set / rotate Super Admin PIN (owner only)."""
    digest, salt = hash_pin(pin)
    state = deepcopy(state)
    state["super_admin"]["pin_hash"] = digest
    state["super_admin"]["pin_salt"] = salt
    save_rbac_state(state)
    return state


def sync_super_admin_profile(
    state: dict[str, Any], *, name: str, email: str
) -> dict[str, Any]:
    state = deepcopy(state)
    state["super_admin"]["name"] = name or state["super_admin"].get("name") or "Super Admin"
    state["super_admin"]["email"] = (email or state["super_admin"].get("email") or "").lower().strip()
    save_rbac_state(state)
    return state


def list_users(state: Optional[dict] = None, *, include_super: bool = True) -> list[dict]:
    state = state or load_rbac_state()
    users = []
    if include_super:
        users.append(deepcopy(state["super_admin"]))
    for u in state.get("users") or []:
        users.append(deepcopy(u))
    return users


def get_user_by_id(user_id: str, state: Optional[dict] = None) -> Optional[dict]:
    for u in list_users(state, include_super=True):
        if u.get("id") == user_id:
            return u
    return None


def get_user_by_email(email: str, state: Optional[dict] = None) -> Optional[dict]:
    needle = (email or "").lower().strip()
    if not needle:
        return None
    for u in list_users(state, include_super=True):
        if (u.get("email") or "").lower().strip() == needle:
            return u
    return None


def _default_module_access(role: str) -> dict[str, list[str]]:
    preset = ROLE_PRESETS.get(role) or ROLE_PRESETS["nurturer"]
    return deepcopy(preset.get("modules") or {})


def create_user(
    state: dict[str, Any],
    *,
    name: str,
    email: str,
    pin: str,
    role: str = "nurturer",
    module_access: Optional[dict[str, list[str]]] = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Super Admin creates a teammate. Returns (user, new_state)."""
    if role == "super_admin":
        raise ValueError("Only one Super Admin is allowed.")
    if role not in ROLE_PRESETS:
        raise ValueError(f"Unknown role: {role}")
    email_n = (email or "").lower().strip()
    if not email_n or not name.strip() or not pin:
        raise ValueError("Name, email, and PIN are required.")
    if get_user_by_email(email_n, state):
        raise ValueError("That email is already on the team.")

    digest, salt = hash_pin(pin)
    user = {
        "id": f"u_{uuid.uuid4().hex[:10]}",
        "name": name.strip(),
        "email": email_n,
        "role": role,
        "active": True,
        "pin_hash": digest,
        "pin_salt": salt,
        "module_access": module_access or _default_module_access(role),
        "created_at": _utc_now(),
    }
    state = deepcopy(state)
    state.setdefault("users", []).append(user)
    save_rbac_state(state)
    return user, state


def update_user(
    state: dict[str, Any],
    user_id: str,
    *,
    name: Optional[str] = None,
    email: Optional[str] = None,
    role: Optional[str] = None,
    active: Optional[bool] = None,
    module_access: Optional[dict[str, list[str]]] = None,
    pin: Optional[str] = None,
) -> dict[str, Any]:
    if user_id == SUPER_ADMIN_ID:
        raise ValueError("Edit Super Admin via PIN / profile tools, not team CRUD.")
    state = deepcopy(state)
    found = None
    for u in state.get("users") or []:
        if u.get("id") == user_id:
            found = u
            break
    if not found:
        raise ValueError("User not found.")
    if name is not None:
        found["name"] = name.strip()
    if email is not None:
        found["email"] = email.lower().strip()
    if role is not None:
        if role == "super_admin":
            raise ValueError("Cannot promote to Super Admin.")
        if role not in ROLE_PRESETS:
            raise ValueError(f"Unknown role: {role}")
        found["role"] = role
        if module_access is None:
            found["module_access"] = _default_module_access(role)
    if active is not None:
        found["active"] = bool(active)
    if module_access is not None:
        found["module_access"] = module_access
    if pin:
        digest, salt = hash_pin(pin)
        found["pin_hash"] = digest
        found["pin_salt"] = salt
    save_rbac_state(state)
    return state


def delete_user(state: dict[str, Any], user_id: str) -> dict[str, Any]:
    if user_id == SUPER_ADMIN_ID:
        raise ValueError("Cannot delete Super Admin.")
    state = deepcopy(state)
    state["users"] = [u for u in (state.get("users") or []) if u.get("id") != user_id]
    save_rbac_state(state)
    return state


def authenticate(
    email: str,
    pin: str,
    *,
    company_email: str = "",
    secrets_pin: str = "",
    state: Optional[dict] = None,
) -> Optional[dict[str, Any]]:
    """
    Login. Super Admin matches company email (or stored super email) + PIN.
    If Super Admin has no PIN set yet, secrets_pin / default bootstrap PIN works
    and is stored on first success.
    """
    state = state or load_rbac_state()
    email_n = (email or "").lower().strip()
    if not email_n or not pin:
        return None

    super_u = state["super_admin"]
    super_emails = {
        (super_u.get("email") or "").lower().strip(),
        (company_email or "").lower().strip(),
        "accounts@logixtrek.com",
    }
    super_emails.discard("")

    if email_n in super_emails:
        if super_u.get("pin_hash") and super_u.get("pin_salt"):
            if verify_pin(pin, super_u["pin_hash"], super_u["pin_salt"]):
                return _public_user(super_u)
            # also accept Streamlit secrets pin as owner override
            if secrets_pin and secrets.compare_digest(pin, secrets_pin):
                return _public_user(super_u)
            return None
        # Bootstrap: accept secrets pin or first PIN the owner types (min 4)
        boot = secrets_pin or ""
        if boot and secrets.compare_digest(pin, boot):
            ensure_super_admin_pin(state, pin)
            state = load_rbac_state()
            return _public_user(state["super_admin"])
        if len(pin) >= 4 and not boot:
            ensure_super_admin_pin(state, pin)
            if company_email:
                sync_super_admin_profile(state, name="Super Admin", email=company_email)
            state = load_rbac_state()
            return _public_user(state["super_admin"])
        if boot:
            return None
        return None

    user = get_user_by_email(email_n, state)
    if not user or user.get("id") == SUPER_ADMIN_ID:
        return None
    if not user.get("active", True):
        return None
    if not verify_pin(pin, user.get("pin_hash", ""), user.get("pin_salt", "")):
        return None
    return _public_user(user)


def _public_user(user: dict) -> dict[str, Any]:
    return {
        "id": user["id"],
        "name": user.get("name") or "",
        "email": user.get("email") or "",
        "role": user.get("role") or "nurturer",
        "module_access": deepcopy(user.get("module_access") or {}),
    }


def is_super_admin(user: Optional[dict]) -> bool:
    return bool(user) and (
        user.get("id") == SUPER_ADMIN_ID or user.get("role") == "super_admin"
    )


def module_for_page(page_label: str) -> Optional[str]:
    for mid, meta in MODULES.items():
        if meta.get("page") == page_label:
            return mid
    return None


def can(user: Optional[dict], module_id: str, action: str = "read") -> bool:
    if not user:
        return False
    if module_id not in MODULES:
        return False
    if is_super_admin(user):
        return True
    meta = MODULES[module_id]
    if meta.get("super_only"):
        return False
    actions = (user.get("module_access") or {}).get(module_id) or []
    return action in actions


def allowed_pages(user: Optional[dict]) -> list[str]:
    pages: list[str] = []
    for mid, meta in MODULES.items():
        page = meta.get("page")
        if not page:
            continue
        if can(user, mid, "read"):
            pages.append(page)
    # stable order matching MODULES definition
    return pages


def can_see_all_leads(user: Optional[dict]) -> bool:
    if not user:
        return False
    if is_super_admin(user):
        return True
    preset = ROLE_PRESETS.get(user.get("role") or "", {})
    return bool(preset.get("see_all_leads"))


def can_access_lead(user: Optional[dict], lead: dict) -> bool:
    if not user:
        return False
    if can_see_all_leads(user):
        return True
    return (lead.get("assigned_to") or "") == user.get("id")


def scope_leads(leads: list[dict], user: Optional[dict]) -> list[dict]:
    if can_see_all_leads(user):
        return list(leads)
    uid = (user or {}).get("id")
    return [l for l in leads if (l.get("assigned_to") or "") == uid]


def assign_leads(
    leads: list[dict], lead_keys: list[str], assignee_id: str
) -> tuple[list[dict], int]:
    """Set assigned_to on matching leads. assignee_id '' = unassign (owner pool)."""
    from .storage import lead_key

    keyset = {k.lower().strip() for k in lead_keys}
    count = 0
    for lead in leads:
        if lead_key(lead).lower() in keyset:
            lead["assigned_to"] = assignee_id or ""
            count += 1
    return leads, count


def assign_carriers(
    leads: list[dict], lead_keys: list[str], assignee_id: str
) -> tuple[list[dict], int]:
    from .carrier_storage import carrier_key

    keyset = {k.lower().strip() for k in lead_keys}
    count = 0
    for lead in leads:
        if carrier_key(lead).lower() in keyset:
            lead["assigned_to"] = assignee_id or ""
            count += 1
    return leads, count


def role_choices() -> list[str]:
    return [r for r in ROLE_PRESETS if r != "super_admin"]


def module_choices_for_team() -> list[str]:
    return [m for m, meta in MODULES.items() if not meta.get("super_only")]
