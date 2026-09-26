"""Streamlit pages — Lead for X multi-project funnel."""
from __future__ import annotations

import csv
import io
from typing import Optional

import pandas as pd
import streamlit as st

from src.project_x.agent import generate_templates_from_scope, preview_templates
from src.project_x.bot import process_inbox_reply
from src.project_x.campaign import run_due_x_emails
from src.project_x.leads import (
    activate_x_sequence,
    filter_x_leads,
    lead_key,
    load_x_leads,
    mark_x_converted,
    mark_x_response,
    upsert_x_leads,
)
from src.project_x.store import (
    PROJECT_TYPES,
    create_project,
    get_active_project,
    get_active_project_id,
    list_projects,
    load_all_x_leads,
    set_active_project_id,
    update_project,
    update_x_lead,
)
from src.project_x.templates import ensure_templates, render_x_email
from src.rbac import can, can_access_lead, is_super_admin, scope_leads
from src.schedule import days_until_next, next_action_for_lead
from src.stages import STAGE_STYLE, contact_indicator, stage_label
from src.storage import using_cloud


def _user():
    return st.session_state.get("auth_user")


def _company():
    return st.session_state.get("company") or {}


def _require_active_project() -> Optional[dict]:
    project = get_active_project()
    if not project:
        st.warning("Create or select a project first → **Lead for X → Project Setup**.")
        return None
    return project


def _project_picker(*, key: str = "x_proj_pick") -> Optional[dict]:
    projects = list_projects()
    if not projects:
        return None
    active_id = get_active_project_id()
    labels = {
        f"{p.get('name')} ({p.get('project_type')})": p.get("id") for p in projects
    }
    ids = list(labels.values())
    default_idx = ids.index(active_id) if active_id in ids else 0
    choice = st.selectbox(
        "Active project",
        list(labels.keys()),
        index=default_idx,
        key=key,
    )
    pid = labels[choice]
    if pid != active_id:
        set_active_project_id(pid)
    return next(p for p in projects if p.get("id") == pid)


def _style_status(df: pd.DataFrame):
    def paint(val):
        for status, (label, bg, fg) in STAGE_STYLE.items():
            if val == label:
                return f"background-color: {bg}; color: {fg}; font-weight: 600;"
        return ""

    return df.style.map(paint, subset=["Stage"])


def _refresh_leads(project_id: str) -> list[dict]:
    all_leads = load_x_leads(project_id)
    visible = scope_leads(all_leads, _user())
    st.session_state["x_leads"] = visible
    return visible


# ---------------------------------------------------------------------------
# Project Setup
# ---------------------------------------------------------------------------


def page_x_projects():
    st.title("Lead for X — Project Setup")
    user = _user()
    if not can(user, "x_projects", "read"):
        st.error("No access to Project Setup.")
        return

    st.caption(
        "Create a project (buyer or seller), paste **Project Scope**, then import leads "
        "and run the 4-email pipeline. The LLM molds every email to your scope."
    )

    projects = list_projects(include_archived=True)
    active = get_active_project()

    col_a, col_b = st.columns([1, 1])
    with col_a:
        st.subheader("Projects")
        if not projects:
            st.info("No projects yet — create one below.")
        else:
            for p in projects:
                badge = "🟢" if (p.get("status") or "") == "active" else "⚪"
                mark = " ← active" if active and p.get("id") == active.get("id") else ""
                st.write(
                    f"{badge} **{p.get('name')}** · {p.get('project_type')}{mark}"
                )
                if st.button("Select", key=f"xsel_{p.get('id')}"):
                    set_active_project_id(p["id"])
                    st.rerun()

    with col_b:
        st.subheader("Create project")
        if can(user, "x_projects", "create") or is_super_admin(user):
            with st.form("x_create_project"):
                name = st.text_input("Name", placeholder="e.g. Shrimp buyers — Gulf")
                ptype = st.selectbox(
                    "Type",
                    list(PROJECT_TYPES),
                    format_func=lambda t: {
                        "buyer": "Buyer — we want to buy / source",
                        "seller": "Seller — we want to sell",
                        "other": "Other / partnership",
                    }.get(t, t),
                )
                scope = st.text_area(
                    "Project Scope (LLM uses this)",
                    height=160,
                    placeholder=(
                        "Example: We buy frozen shrimp (16/20, 21/25) from Gulf / import "
                        "suppliers for East Coast distributors. Need HACCP, consistent "
                        "weekly volume, FOB or delivered pricing. Tone: direct, seafood-trade."
                    ),
                )
                tone = st.text_input("Tone notes (optional)", placeholder="Direct, trade-floor, no fluff")
                if st.form_submit_button("Create project", type="primary"):
                    try:
                        p = create_project(
                            name=name,
                            project_type=ptype,
                            scope=scope,
                            tone_notes=tone,
                        )
                        st.success(f"Created **{p['name']}** and set as active.")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
        else:
            st.warning("No create permission.")

    st.divider()
    st.subheader("Edit active project")
    project = _project_picker(key="x_edit_pick")
    if not project:
        return

    if not (can(user, "x_projects", "update") or is_super_admin(user)):
        st.info("Read-only — ask Super Admin to edit scope.")
        st.markdown(f"**Scope**\n\n{project.get('scope') or '_(empty)_'}")
        return

    e1, e2 = st.columns(2)
    new_name = e1.text_input("Name", value=project.get("name") or "", key="x_en")
    new_type = e2.selectbox(
        "Type",
        list(PROJECT_TYPES),
        index=list(PROJECT_TYPES).index(project.get("project_type") or "buyer"),
        key="x_et",
    )
    new_scope = st.text_area(
        "Project Scope",
        value=project.get("scope") or "",
        height=200,
        key="x_es",
        help="This is the domain brain — templates, pipeline emails, and inbox replies mold to this text.",
    )
    new_tone = st.text_input(
        "Tone notes",
        value=project.get("tone_notes") or "",
        key="x_eto",
    )
    new_status = st.selectbox(
        "Status",
        ["active", "archived"],
        index=0 if (project.get("status") or "active") == "active" else 1,
        key="x_est",
    )

    b1, b2 = st.columns(2)
    if b1.button("Save project", type="primary", key="x_save_proj"):
        update_project(
            project["id"],
            name=new_name,
            project_type=new_type,
            scope=new_scope,
            tone_notes=new_tone,
            status=new_status,
        )
        st.success("Saved.")
        st.rerun()
    if b2.button("Regenerate templates from scope", key="x_regen_hint"):
        st.info("Open **Lead for X → Templates** and click **Generate from Project Scope (LLM)**.")


# ---------------------------------------------------------------------------
# Find Leads
# ---------------------------------------------------------------------------


def page_x_find_leads():
    st.title("Lead for X — Find Leads")
    user = _user()
    if not can(user, "x_find_leads", "read"):
        st.error("No access.")
        return
    project = _require_active_project()
    if not project:
        return
    st.caption(f"Importing into **{project.get('name')}** ({project.get('project_type')})")
    _project_picker(key="x_find_proj")

    tab_paste, tab_csv, tab_manual = st.tabs(["Paste dump", "CSV import", "Add one"])

    with tab_paste:
        from src.paste_dump import parse_paste_dump

        st.markdown("#### Paste emails / contacts → this project")
        state = st.text_input("Default state", "", key="xpaste_st")
        blob = st.text_area("Paste dump", height=200, key="xpaste_blob")
        if st.button("Parse paste", type="primary", key="xpaste_parse"):
            parsed = parse_paste_dump(
                blob,
                state=state,
                freight_type=project.get("name") or "Lead",
                source="x_paste_dump",
            )
            for p in parsed:
                p["project_id"] = project["id"]
                p["source"] = "x_paste_dump"
                if p.get("freight_type"):
                    p["role_or_title"] = p.get("freight_type")
            st.session_state["x_paste"] = parsed
            st.success(f"Extracted {len(parsed)} row(s).") if parsed else st.warning("Nothing found.")

        parsed = st.session_state.get("x_paste") or []
        if parsed:
            st.dataframe(pd.DataFrame(parsed), use_container_width=True, hide_index=True)
            if can(user, "x_find_leads", "create") or is_super_admin(user):
                c1, c2 = st.columns(2)
                if c1.button("Save to project", type="primary", key="xpaste_save"):
                    a, u = upsert_x_leads(project["id"], parsed)
                    st.success(f"Saved — added {a}, updated {u}.")
                    st.session_state.pop("x_paste", None)
                if c2.button("Save + Activate", key="xpaste_act"):
                    a, u = upsert_x_leads(project["id"], parsed)
                    leads = load_all_x_leads()
                    keys = [
                        lead_key(l)
                        for l in leads
                        if l.get("project_id") == project["id"]
                        and any(
                            (l.get("email") or "").lower() == (p.get("email") or "").lower()
                            for p in parsed
                            if p.get("email")
                        )
                    ]
                    n, skipped = activate_x_sequence(leads, keys)
                    st.success(f"Saved ({a}/{u}), activated {n}. Next: **Pipeline → Start**.")
                    for s in skipped:
                        st.warning(s)
                    st.session_state.pop("x_paste", None)

    with tab_csv:
        st.caption("CSV with columns like company_name, contact_name, email, phone, state")
        up = st.file_uploader("CSV file", type=["csv"], key="x_csv")
        if up is not None:
            raw = up.read()
            try:
                text = raw.decode("utf-8-sig")
            except Exception:
                text = raw.decode("latin-1")
            reader = csv.DictReader(io.StringIO(text))
            rows = []
            for row in reader:
                rows.append(
                    {
                        "company_name": (row.get("company_name") or row.get("company") or "").strip(),
                        "contact_name": (row.get("contact_name") or row.get("name") or "").strip(),
                        "email": (row.get("email") or "").strip(),
                        "phone": (row.get("phone") or "").strip(),
                        "state": (row.get("state") or "").strip(),
                        "notes": (row.get("notes") or "").strip(),
                        "role_or_title": (row.get("title") or row.get("role") or "").strip(),
                        "source": "x_csv",
                        "project_id": project["id"],
                    }
                )
            st.write(f"{len(rows)} row(s)")
            if rows:
                st.dataframe(pd.DataFrame(rows[:50]), use_container_width=True, hide_index=True)
            if rows and (can(user, "x_find_leads", "create") or is_super_admin(user)):
                if st.button("Import CSV into project", type="primary", key="x_csv_go"):
                    a, u = upsert_x_leads(project["id"], rows)
                    st.success(f"Imported — added {a}, updated {u}.")

    with tab_manual:
        with st.form("x_manual"):
            co = st.text_input("Company")
            cn = st.text_input("Contact")
            em = st.text_input("Email")
            ph = st.text_input("Phone")
            stt = st.text_input("State")
            if st.form_submit_button("Add lead"):
                if not (can(user, "x_find_leads", "create") or is_super_admin(user)):
                    st.error("No create permission.")
                elif not em and not co:
                    st.error("Need company or email.")
                else:
                    upsert_x_leads(
                        project["id"],
                        [
                            {
                                "company_name": co,
                                "contact_name": cn,
                                "email": em,
                                "phone": ph,
                                "state": stt,
                                "source": "x_manual",
                            }
                        ],
                    )
                    st.success("Added.")


# ---------------------------------------------------------------------------
# Leads List
# ---------------------------------------------------------------------------


def page_x_leads_list():
    st.title("Lead for X — Leads List")
    user = _user()
    if not can(user, "x_leads", "read"):
        st.error("No access.")
        return
    project = _require_active_project()
    if not project:
        return
    _project_picker(key="x_list_proj")
    if using_cloud():
        st.success("☁️ Cloud: Google Sheet `x_leads`")
    else:
        st.warning("💾 Local `data/x_leads.json`")

    leads = _refresh_leads(project["id"])
    f1, f2, f3, f4 = st.columns(4)
    f_state = f1.text_input("State", "", key="xl_st")
    f_status = f2.selectbox(
        "Stage",
        [""] + list(STAGE_STYLE.keys()),
        format_func=lambda s: stage_label(s) if s else "All stages",
        key="xl_status",
    )
    f_q = f3.text_input("Search", "", key="xl_q")
    hide_dnc = f4.checkbox("Hide DNC", value=False, key="xl_dnc")

    filtered = filter_x_leads(
        leads,
        project_id=project["id"],
        state=f_state or None,
        status=f_status or None,
        hide_dnc=hide_dnc,
        q=f_q or None,
    )
    if not filtered:
        st.warning("No leads yet. Use Find Leads to import.")
        return

    rows = []
    for l in filtered:
        rows.append(
            {
                "Stage": stage_label(l.get("status") or "not_started"),
                "Indicator": contact_indicator(l),
                "Company": l.get("company_name") or "",
                "Contact": l.get("contact_name") or "",
                "Email": l.get("email") or "",
                "Phone": l.get("phone") or "",
                "State": l.get("state") or "",
                "Emails sent": int(l.get("contact_count") or 0),
                "Remarks": l.get("remarks") or "",
                "Reasoning": (l.get("reasoning") or "")[:80],
                "_key": lead_key(l),
            }
        )
    df = pd.DataFrame(rows)
    st.dataframe(
        _style_status(df.drop(columns=["_key"])),
        use_container_width=True,
        hide_index=True,
        height=420,
    )

    if not can(user, "x_leads", "update"):
        return

    labels = {
        f"{r['Company']} <{r['Email']}> — {r['Stage']}": r["_key"] for r in rows
    }
    pick = st.selectbox("Select lead", list(labels.keys()), key="xl_pick")
    key = labels[pick]
    lead = next(l for l in leads if lead_key(l) == key)

    if not can_access_lead(user, lead) and not is_super_admin(user):
        st.error("No access to that lead.")
        return

    r1, r2 = st.columns(2)
    with r1:
        new_remarks = st.text_area("Remarks", value=lead.get("remarks") or "", height=90)
        new_email = st.text_input("Email", value=lead.get("email") or "")
        new_phone = st.text_input("Phone", value=lead.get("phone") or "")
    with r2:
        st.write(f"**{contact_indicator(lead)}**")
        st.write(f"**Reasoning:** {lead.get('reasoning') or '—'}")

    b1, b2, b3, b4 = st.columns(4)
    if b1.button("Save", type="primary", key="xl_save"):
        lead["remarks"] = new_remarks
        lead["email"] = new_email
        lead["phone"] = new_phone
        update_x_lead(lead)
        st.success("Saved.")
        st.rerun()
    if b2.button("Mark Converted ★", key="xl_conv"):
        mark_x_converted(lead)
        update_x_lead(lead)
        st.success("Converted.")
        st.rerun()
    if b3.button("Do Not Contact 🚫", key="xl_dncbtn"):
        mark_x_response(lead, positive=False)
        update_x_lead(lead)
        st.success("Locked DNC.")
        st.rerun()
    if b4.button("Mark Responded 📞", key="xl_resp"):
        mark_x_response(lead, positive=True)
        update_x_lead(lead)
        st.success("Sequence stopped.")
        st.rerun()


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def page_x_pipeline():
    st.title("Lead for X — Pipeline")
    user = _user()
    if not can(user, "x_pipeline", "read"):
        st.error("No access.")
        return
    company = _company()
    project = _require_active_project()
    if not project:
        return
    _project_picker(key="x_pipe_proj")
    st.caption(
        f"**{project.get('name')}** · 4-email sequence · days 0 / 4 / 9 / 16 · "
        f"{'LIVE' if company.get('send_live_emails') else 'dry-run'}"
    )

    leads = _refresh_leads(project["id"])
    filtered = filter_x_leads(leads, project_id=project["id"], hide_dnc=True)
    if not filtered:
        st.warning("No outreach-eligible leads.")
        return

    if "xpipe_sel_nonce" not in st.session_state:
        st.session_state["xpipe_sel_nonce"] = 0
    if "xpipe_select_default" not in st.session_state:
        st.session_state["xpipe_select_default"] = False

    s_all, s_clear, s_hint = st.columns([1, 1, 2])
    if s_all.button("Select all", key="xpipe_sel_all"):
        st.session_state["xpipe_select_default"] = True
        st.session_state["xpipe_sel_nonce"] = int(st.session_state["xpipe_sel_nonce"]) + 1
        st.rerun()
    if s_clear.button("Clear selection", key="xpipe_sel_clear"):
        st.session_state["xpipe_select_default"] = False
        st.session_state["xpipe_sel_nonce"] = int(st.session_state["xpipe_sel_nonce"]) + 1
        st.rerun()
    s_hint.caption(f"{len(filtered)} leads shown")

    default_sel = bool(st.session_state.get("xpipe_select_default"))
    key_by_idx = []
    rows = []
    for l in filtered:
        step = next_action_for_lead(l)
        key_by_idx.append(lead_key(l))
        rows.append(
            {
                "Select": default_sel,
                "Stage": stage_label(l.get("status") or "not_started"),
                "Indicator": contact_indicator(l),
                "Company": l.get("company_name"),
                "Email": l.get("email"),
                "State": l.get("state"),
                "Active": bool(l.get("active_sequence")),
                "Next": step if step else "—",
                "Days": days_until_next(l) if l.get("active_sequence") else "—",
            }
        )

    edited = st.data_editor(
        pd.DataFrame(rows),
        hide_index=True,
        use_container_width=True,
        disabled=[c for c in rows[0].keys() if c != "Select"],
        key=f"xpipe_editor_{st.session_state['xpipe_sel_nonce']}",
    )
    selected_keys = [
        key_by_idx[i] for i, sel in enumerate(edited["Select"].tolist()) if sel
    ]
    force = st.checkbox("Force restart sequence", value=False, key="xpipe_force")

    a1, a2, a3 = st.columns(3)
    if a1.button("Activate selected", type="primary", key="xpipe_act"):
        if not can(user, "x_pipeline", "update"):
            st.error("No update permission.")
        elif not selected_keys:
            st.warning("Select leads first.")
        else:
            n, skipped = activate_x_sequence(load_all_x_leads(), selected_keys, force=force)
            st.success(f"Activated {n}.")
            for s in skipped:
                st.warning(s)
            _refresh_leads(project["id"])

    if a2.button("Start — send due emails", key="xpipe_start"):
        if not can(user, "x_pipeline", "update"):
            st.error("No update permission.")
        else:
            keys = selected_keys or [
                lead_key(l)
                for l in leads
                if l.get("active_sequence") and next_action_for_lead(l)
            ]
            if not keys:
                st.warning("Nothing due.")
            else:
                results = run_due_x_emails(
                    load_all_x_leads(), company, project, only_keys=keys
                )
                mode = "LIVE" if company.get("send_live_emails") else "DRY RUN"
                st.success(f"Processed {len(results)} ({mode}).")
                for r in results:
                    if r.get("ok"):
                        st.write(f"✓ {r.get('lead')} → Email {r.get('step')}")
                        if not company.get("send_live_emails") and r.get("body"):
                            with st.expander(f"Preview {r.get('lead')}"):
                                st.code(r.get("body", ""))
                    else:
                        st.error(f"✗ {r.get('lead')}: {r.get('error')}")
                _refresh_leads(project["id"])

    if a3.button("Mark selected Converted", key="xpipe_conv"):
        if not selected_keys:
            st.warning("Select first.")
        else:
            for l in load_all_x_leads():
                if lead_key(l) in selected_keys and can_access_lead(user, l):
                    mark_x_converted(l)
                    update_x_lead(l)
            st.success("Marked Converted.")
            st.rerun()

    with st.expander("Email 1–4 preview (this project)"):
        for step, subj, body in preview_templates(project, company):
            st.markdown(f"**Email {step} — {subj}**")
            st.code(body)


# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------


def page_x_inbox():
    st.title("Lead for X — Inbox")
    user = _user()
    if not can(user, "x_inbox", "read"):
        st.error("No access.")
        return
    company = _company()
    project = _require_active_project()
    if not project:
        return
    _project_picker(key="x_inbox_proj")
    st.caption(
        f"Paste a reply. Bot uses **Project Scope** for {project.get('name')} "
        f"({project.get('project_type')})."
    )

    leads = _refresh_leads(project["id"])
    with_email = [l for l in leads if l.get("email")]
    if not with_email:
        st.warning("Add leads with email first.")
        return

    labels = {
        f"{l.get('company_name')} <{l.get('email')}> [{stage_label(l.get('status'))}]": l
        for l in with_email
    }
    choice = st.selectbox("Which lead replied?", list(labels.keys()), key="xib_pick")
    lead = labels[choice]
    inbound = st.text_area("Paste their reply", height=160, key="xib_in")

    if st.button("Process with Lead-for-X Bot", type="primary", key="xib_go") and inbound.strip():
        if not can(user, "x_inbox", "update"):
            st.error("No update permission.")
            return
        summary = process_inbox_reply(lead, inbound, company, project)
        decision = summary["decision"]
        st.markdown(f"**Intent:** `{decision.intent}`")
        st.caption(summary.get("reasoning") or "")
        if decision.stop_sequence:
            st.info("Sequence stopped.")
        if summary.get("sent"):
            st.success(
                f"Bot reply {'sent' if summary.get('mode') == 'live' else 'drafted (dry run)'}."
            )
            with st.expander("Bot reply"):
                st.code(decision.reply_body)
        elif decision.intent == "escalate":
            st.warning("Escalated — you close this deal yourself.")
        if decision.escalate_to_owner:
            st.info("Owner alert logged.")
        _refresh_leads(project["id"])


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


def page_x_templates():
    st.title("Lead for X — Templates")
    user = _user()
    if not can(user, "x_templates", "read"):
        st.error("No access.")
        return
    company = _company()
    project = _require_active_project()
    if not project:
        return
    project = _project_picker(key="x_tmpl_proj") or project

    st.caption(
        f"**{project.get('name')}** · type `{project.get('project_type')}` · "
        "Generate from Project Scope (Gemini if key set, else rule-based)."
    )
    with st.expander("Current Project Scope", expanded=False):
        st.write(project.get("scope") or "_(empty — add scope in Project Setup)_")

    has_gemini = bool((company.get("gemini_api_key") or "").strip())
    st.write(f"Gemini: {'ready' if has_gemini else 'not set → rule-based templates'}")

    if can(user, "x_templates", "update") or is_super_admin(user):
        if st.button("Generate from Project Scope (LLM)", type="primary", key="x_gen_tmpl"):
            tmpl, method = generate_templates_from_scope(project, company)
            update_project(project["id"], templates=tmpl)
            st.success(f"Templates updated via **{method}**.")
            st.rerun()

    templates = ensure_templates(project)
    for step in range(1, 5):
        t = templates[step]
        st.markdown(f"#### Email {step}")
        if can(user, "x_templates", "update") or is_super_admin(user):
            subj = st.text_input(
                f"Subject {step}",
                value=t.get("subject") or "",
                key=f"x_ts_{step}",
            )
            body = st.text_area(
                f"Body {step}",
                value=t.get("body") or "",
                height=180,
                key=f"x_tb_{step}",
            )
            templates[step] = {"subject": subj, "body": body}
        else:
            st.write(f"**{t.get('subject')}**")
            st.code(t.get("body") or "")

    if can(user, "x_templates", "update") or is_super_admin(user):
        if st.button("Save template edits", key="x_tmpl_save"):
            update_project(project["id"], templates=templates)
            st.success("Saved.")
            st.rerun()

    st.divider()
    st.subheader("Merged preview")
    sample = {
        "contact_name": "Alex",
        "company_name": "Sample Co",
        "state": "FL",
        "lane_or_region": "Southeast",
    }
    # Use in-memory edits
    preview_proj = {**project, "templates": templates}
    for step in range(1, 5):
        subj, body = render_x_email(step, sample, company, preview_proj)
        st.markdown(f"**Email {step} — {subj}**")
        st.code(body)
