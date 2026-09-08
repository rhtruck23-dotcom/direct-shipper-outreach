"""RBAC unit tests — roles, scoping, CRUD, scalable modules."""
from __future__ import annotations

import src.rbac as rbac


def test_hash_pin_roundtrip():
    digest, salt = rbac.hash_pin("secret123")
    assert rbac.verify_pin("secret123", digest, salt)
    assert not rbac.verify_pin("wrong", digest, salt)


def test_super_admin_sees_all_and_all_pages(tmp_path, monkeypatch):
    monkeypatch.setattr(rbac, "TEAM_JSON", tmp_path / "team_rbac.json")
    state = rbac._blank_state()
    rbac.save_rbac_state(state)
    rbac.ensure_super_admin_pin(state, "owner-pin")
    user = rbac.authenticate(
        "accounts@logixtrek.com",
        "owner-pin",
        company_email="accounts@logixtrek.com",
    )
    assert user is not None
    assert rbac.is_super_admin(user)
    assert "Org Setup" in rbac.allowed_pages(user)
    assert "Cloud Hosting" in rbac.allowed_pages(user)
    leads = [
        {"email": "a@a.com", "assigned_to": ""},
        {"email": "b@b.com", "assigned_to": "u_other"},
    ]
    assert len(rbac.scope_leads(leads, user)) == 2


def test_nurturer_scoped_leads_and_no_org(tmp_path, monkeypatch):
    monkeypatch.setattr(rbac, "TEAM_JSON", tmp_path / "team_rbac.json")
    state = rbac._blank_state()
    rbac.save_rbac_state(state)
    user, state = rbac.create_user(
        state,
        name="Nurse",
        email="nurse@logixtrek.com",
        pin="nurse1",
        role="nurturer",
    )
    pub = rbac.authenticate("nurse@logixtrek.com", "nurse1")
    assert pub is not None
    assert not rbac.is_super_admin(pub)
    assert "Org Setup" not in rbac.allowed_pages(pub)
    assert "Cloud Hosting" not in rbac.allowed_pages(pub)
    assert rbac.can(pub, "leads", "read")
    assert rbac.can(pub, "leads", "update")
    assert not rbac.can(pub, "org_setup", "read")

    leads = [
        {"email": "a@a.com", "assigned_to": user["id"]},
        {"email": "b@b.com", "assigned_to": ""},
        {"email": "c@c.com", "assigned_to": "someone_else"},
    ]
    scoped = rbac.scope_leads(leads, pub)
    assert len(scoped) == 1
    assert scoped[0]["email"] == "a@a.com"


def test_assign_leads():
    leads = [
        {"email": "a@a.com", "assigned_to": ""},
        {"email": "b@b.com", "assigned_to": ""},
    ]
    out, n = rbac.assign_leads(leads, ["a@a.com"], "u_1")
    assert n == 1
    assert out[0]["assigned_to"] == "u_1"
    assert out[1]["assigned_to"] == ""


def test_module_registry_has_pages():
    pages = {m["page"] for m in rbac.MODULES.values() if m.get("page")}
    assert "Dashboard" in pages
    assert "Find Leads" in pages
    assert "team_admin" in rbac.MODULES
    assert rbac.MODULES["team_admin"]["super_only"] is True


def test_update_and_delete_user(tmp_path, monkeypatch):
    monkeypatch.setattr(rbac, "TEAM_JSON", tmp_path / "team_rbac.json")
    state = rbac._blank_state()
    rbac.save_rbac_state(state)
    user, state = rbac.create_user(
        state, name="Rep", email="rep@x.com", pin="rep99", role="rep"
    )
    state = rbac.update_user(
        state,
        user["id"],
        role="manager",
        module_access={"leads": ["read", "update"], "dashboard": ["read"]},
    )
    again = rbac.get_user_by_id(user["id"], state)
    assert again["role"] == "manager"
    assert again["module_access"]["leads"] == ["read", "update"]
    state = rbac.delete_user(state, user["id"])
    assert rbac.get_user_by_id(user["id"], state) is None
