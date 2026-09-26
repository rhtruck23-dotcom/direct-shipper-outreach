"""
Shared Streamlit CRM panel for a selected lead.

Used by Shipper Leads List + Lead for X Leads List (+ Carrier when wired).
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Callable, Optional

import streamlit as st

from .crm_picklists import (
    CRM_STATUSES,
    PRIORITIES,
    SALES_STAGES,
    crm_status_label,
    normalize_crm_status,
    normalize_priority,
    normalize_sales_stage,
    priority_label,
    sales_stage_label,
)
from .lead_crm import (
    append_note,
    create_task,
    ensure_lead_crm_fields,
    lead_stable_id,
    mark_task_done,
    send_one_off_email,
    tasks_for_lead,
)
from .llm import chat, preferred_provider
from .outcome_learning import patterns_for_prompt
from .rag import build_context_pack


PersistFn = Callable[[dict], None]


def render_lead_crm_panel(
    lead: dict,
    company: dict,
    *,
    funnel: str = "shipper",
    persist: PersistFn,
    project: Optional[dict] = None,
    key_prefix: str = "crm",
    show_agent_chat: bool = True,
) -> None:
    """
    CRM detail: picklists, notes timeline, one-off email, tasks, optional agent chat.
    Mutates `lead` in place and calls `persist(lead)` on saves.
    """
    ensure_lead_crm_fields(lead)
    lid = lead_stable_id(lead, funnel=funnel)
    kp = f"{key_prefix}_{lid}"

    st.markdown("#### CRM fields")
    c1, c2, c3, c4 = st.columns(4)
    cur_status = normalize_crm_status(lead.get("crm_status"))
    cur_stage = normalize_sales_stage(lead.get("sales_stage"))
    cur_pri = normalize_priority(lead.get("priority"))
    new_status = c1.selectbox(
        "CRM status",
        list(CRM_STATUSES),
        index=list(CRM_STATUSES).index(cur_status),
        format_func=crm_status_label,
        key=f"{kp}_status",
    )
    new_stage = c2.selectbox(
        "Sales stage",
        list(SALES_STAGES),
        index=list(SALES_STAGES).index(cur_stage),
        format_func=sales_stage_label,
        key=f"{kp}_stage",
    )
    new_pri = c3.selectbox(
        "Priority",
        list(PRIORITIES),
        index=list(PRIORITIES).index(cur_pri),
        format_func=priority_label,
        key=f"{kp}_pri",
    )
    next_raw = (lead.get("next_contact_at") or "")[:16]
    try:
        default_dt = datetime.fromisoformat(next_raw) if next_raw else None
    except Exception:
        default_dt = None
    next_d = c4.date_input(
        "Next contact date",
        value=default_dt.date() if default_dt else None,
        key=f"{kp}_ncd",
    )
    next_t = st.time_input(
        "Next contact time",
        value=default_dt.time() if default_dt else time(9, 0),
        key=f"{kp}_nct",
    )

    if st.button("Save CRM fields", type="primary", key=f"{kp}_save_crm"):
        lead["crm_status"] = new_status
        lead["sales_stage"] = new_stage
        lead["priority"] = new_pri
        if next_d:
            lead["next_contact_at"] = datetime.combine(next_d, next_t).isoformat(timespec="minutes")
        else:
            lead["next_contact_at"] = ""
        persist(lead)
        st.success("CRM fields saved.")
        st.rerun()

    # ---- Notes timeline ----
    st.markdown("#### Notes timeline")
    timeline = lead.get("notes_timeline") or []
    if timeline:
        with st.expander(f"Past notes ({len(timeline)})", expanded=len(timeline) <= 3):
            for n in reversed(timeline[-20:]):
                who = n.get("author") or ""
                st.caption(f"{str(n.get('at') or '')[:19]} {('· ' + who) if who else ''}")
                st.write(n.get("text") or "")
    else:
        st.caption("No timeline notes yet — remarks still work as a free-text field above.")

    note_text = st.text_area("Add note (appends to timeline)", height=70, key=f"{kp}_note")
    if st.button("Append note", key=f"{kp}_add_note"):
        if note_text.strip():
            author = ""
            try:
                u = st.session_state.get("auth_user") or {}
                author = u.get("name") or u.get("email") or ""
            except Exception:
                pass
            append_note(lead, note_text, author=author)
            persist(lead)
            st.success("Note added.")
            st.rerun()
        else:
            st.warning("Write a note first.")

    # ---- One-off email ----
    st.markdown("#### Send one-off email")
    live = bool(company.get("send_live_emails"))
    st.caption(
        f"Uses the same emailer as Pipeline · "
        f"{'🟢 LIVE' if live else '🟡 dry-run (safe)'} — independent of the 4-step sequence."
    )
    e1, e2 = st.columns(2)
    oo_subj = e1.text_input("Subject", key=f"{kp}_oo_subj")
    oo_body = e2.text_area("Body", height=100, key=f"{kp}_oo_body")
    if st.button("Send one-off", key=f"{kp}_oo_send"):
        if not (lead.get("email") or "").strip():
            st.error("Lead has no email.")
        elif not oo_subj.strip() or not oo_body.strip():
            st.warning("Subject and body required.")
        else:
            result = send_one_off_email(
                lead, company, subject=oo_subj.strip(), body=oo_body.strip(), funnel=funnel
            )
            persist(lead)
            if result.get("ok"):
                st.success(f"Email queued ({result.get('mode')}).")
            else:
                st.error(result.get("error") or "Send failed.")
            st.rerun()

    # ---- Tasks ----
    st.markdown("#### Schedule task")
    t1, t2 = st.columns(2)
    task_title = t1.text_input("Task title", key=f"{kp}_tt")
    task_due_d = t2.date_input("Due date", value=date.today(), key=f"{kp}_td")
    task_due_t = st.time_input("Due time", value=time(17, 0), key=f"{kp}_ttm")
    if st.button("Create task", key=f"{kp}_ct"):
        if not task_title.strip():
            st.warning("Title required.")
        else:
            due_at = datetime.combine(task_due_d, task_due_t).isoformat(timespec="minutes")
            create_task(
                lead_id=lid,
                title=task_title.strip(),
                due_at=due_at,
                funnel=funnel,
                company_name=lead.get("company_name") or "",
            )
            # Ensure lead has stable id for future links
            if not (lead.get("id") or "").strip():
                lead["id"] = lid
                persist(lead)
            st.success("Task created.")
            st.rerun()

    open_tasks = tasks_for_lead(lid, include_done=True)
    if open_tasks:
        st.caption(f"{sum(1 for t in open_tasks if t.get('status')!='done')} open · {len(open_tasks)} total")
        for t in open_tasks[:12]:
            cols = st.columns([4, 2, 1])
            status = t.get("status") or "open"
            cols[0].write(f"{'✅' if status=='done' else '⬜'} **{t.get('title')}**")
            cols[1].caption(str(t.get("due_at") or "")[:16])
            if status != "done" and cols[2].button("Done", key=f"{kp}_done_{t['id']}"):
                mark_task_done(t["id"])
                st.rerun()

    # ---- Agent chat ----
    if show_agent_chat:
        st.markdown("#### Agent chat")
        st.caption(
            "Ask about this lead / project. Uses scope + RAG context pack + outcome learning. "
            f"Provider preference: **{preferred_provider(company)}** "
            "(fallback: preferred → gemini → ollama → rules)."
        )
        hist_key = f"{kp}_chat_hist"
        if hist_key not in st.session_state:
            st.session_state[hist_key] = []
        for m in st.session_state[hist_key][-8:]:
            with st.chat_message(m["role"]):
                st.write(m["content"])

        prompt = st.chat_input("Message the agent…", key=f"{kp}_chat_in")
        if prompt:
            st.session_state[hist_key].append({"role": "user", "content": prompt})
            pack = build_context_pack(project=project, lead=lead)
            patterns = patterns_for_prompt(lead=lead, project=project)
            system = (
                "You are a CRM sales assistant for LogixTrek outreach. "
                "Be concise and actionable. Use CONTEXT PACK facts only when claiming specifics.\n\n"
                f"CONTEXT PACK:\n{pack}\n"
            )
            if patterns:
                system += f"\n{patterns}\n"
            result = chat(
                st.session_state[hist_key][-10:],
                company,
                system=system,
            )
            if result.ok:
                reply = result.text.strip()
                via = result.provider
            else:
                # Rules fallback
                reply = (
                    f"(Rules fallback — no LLM responded: {result.error or 'none'})\n\n"
                    f"Lead: {lead.get('company_name')} · stage {lead.get('sales_stage')} · "
                    f"status {lead.get('crm_status')}.\n"
                    f"Next contact: {lead.get('next_contact_at') or 'not set'}.\n"
                    f"Project: {(project or {}).get('name') or 'n/a'}.\n"
                    "Tip: install Ollama + pull llama3.2, or set Gemini/Groq keys in Org Setup."
                )
                via = "rules"
            st.session_state[hist_key].append(
                {"role": "assistant", "content": f"{reply}\n\n_via {via}_"}
            )
            st.rerun()
