"""Streamlit pages — Carrier (owner-operator) onboarding funnel."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.bot import handle_reply
from src.carrier_campaign import run_due_carrier_emails
from src.carrier_fmcsa import search_new_carriers
from src.carrier_import import parse_carrier_upload
from src.carrier_leads import (
    activate_carrier_sequence,
    carrier_key,
    filter_carriers,
    load_carriers,
    mark_carrier_hired,
    mark_carrier_response,
    upsert_carriers,
)
from src.carrier_storage import update_carrier
from src.carrier_templates import render_carrier_email
from src.notify import notify_owner
from src.rbac import (
    can,
    can_access_lead,
    is_super_admin,
    list_users,
    scope_leads,
)
from src.schedule import days_until_next, next_action_for_lead
from src.stages import STAGE_STYLE, contact_indicator, stage_label
from src.storage import using_cloud


def _user():
    return st.session_state.get("auth_user")


def _company():
    return st.session_state.get("company") or {}


def _assignee_name(user_id: str) -> str:
    if not user_id:
        return "Unassigned (owner pool)"
    for u in list_users(include_super=True):
        if u.get("id") == user_id:
            return f"{u.get('name')} ({u.get('role')})"
    return user_id


def _all_carriers() -> list[dict]:
    try:
        leads = load_carriers()
        st.session_state.pop("_carrier_storage_error", None)
        return leads
    except Exception as e:
        st.session_state["_carrier_storage_error"] = str(e)
        return list(st.session_state.get("carriers_all") or [])


def _refresh_carriers() -> list[dict]:
    all_leads = _all_carriers()
    st.session_state.carriers_all = all_leads
    if st.session_state.get("_carrier_storage_error"):
        st.error(
            "Carrier Cloud DB read failed. "
            f"{st.session_state['_carrier_storage_error'][:280]}"
        )
    visible = scope_leads(all_leads, _user())
    st.session_state.carriers = visible
    return visible


def _persist_one(lead: dict) -> None:
    user = _user()
    if not can_access_lead(user, lead) and not is_super_admin(user):
        st.error("No access to that carrier.")
        return
    if not can(user, "carrier_leads", "update") and not is_super_admin(user):
        st.error("No update permission.")
        return
    update_carrier(lead)


def _carrier_indicator(lead: dict) -> str:
    status = lead.get("status") or "not_started"
    if status == "converted":
        return "✅ Hired under MC"
    return contact_indicator(lead)


def _style_status(df: pd.DataFrame):
    def paint(val):
        for status, (label, bg, fg) in STAGE_STYLE.items():
            if val == label:
                return f"background-color: {bg}; color: {fg}; font-weight: 600;"
        return ""

    return df.style.map(paint, subset=["Stage"])


def page_find_carriers():
    st.title("Find Carriers (Owner-Operators)")
    user = _user()
    if not can(user, "find_carriers", "read"):
        st.error("No access to Find Carriers.")
        return
    st.caption(
        "Build a lease-on recruiting list under LogixTrek MC. "
        "Import PDF/Excel/CSV, pull FMCSA demo/live lookups, then activate the 4-email sequence."
    )
    company = _company()

    tab_paste, tab_fmcsa, tab_import, tab_manual = st.tabs(
        [
            "Paste dump (easiest)",
            "FMCSA / new authority",
            "Import PDF / Excel / CSV",
            "Add one carrier",
        ]
    )

    with tab_paste:
        st.markdown("#### Paste carrier list → lease-on pipeline")
        st.caption(
            "Copy from LinkedIn, email, Excel, Notes — paste here. App pulls company / contact / email / phone / MC if present."
        )
        from src.paste_dump import parse_paste_dump

        cstate = st.text_input("Default state", "VA", key="cpaste_st")
        blob = st.text_area("Paste dump", height=200, key="cpaste_blob")
        if st.button("Parse paste", type="primary", key="cpaste_parse"):
            parsed = parse_paste_dump(
                blob, state=cstate, freight_type="Reefer", source="carrier_paste_dump"
            )
            # map freight field unused for carriers — keep company/email/phone
            for p in parsed:
                p["equipment_type"] = p.get("freight_type") or ""
                p["source"] = "carrier_paste_dump"
            st.session_state["carrier_paste"] = parsed
            st.success(f"Extracted {len(parsed)} row(s).") if parsed else st.warning("Nothing found.")
        parsed = st.session_state.get("carrier_paste") or []
        if parsed:
            st.dataframe(pd.DataFrame(parsed), use_container_width=True, hide_index=True)
            if can(user, "find_carriers", "create") or is_super_admin(user):
                if st.button("Save paste to Carrier Leads", type="primary", key="cpaste_save"):
                    # only rows with email or mc/company
                    a, u = upsert_carriers(parsed)
                    st.success(f"Saved — added {a}, updated {u}.")
                    _refresh_carriers()

    with tab_fmcsa:
        st.markdown("#### Pull carriers by state (official FMCSA Census)")
        st.caption(
            "Enter **VA** (or any 2-letter state) → pulls **up to thousands** of active carriers "
            "with MC# from data.transportation.gov. Emails are usually blank — add before outreach. "
            "Filter to small fleets for owner-operator lease-on targets."
        )
        c1, c2, c3, c4 = st.columns(4)
        state = c1.text_input("State (2-letter)", "VA", key="fc_st")
        limit = c2.number_input("Max carriers", min_value=50, max_value=5000, value=1000, step=50)
        max_pu = c3.number_input("Max power units (O/O filter)", min_value=0, max_value=500, value=10)
        active = c4.checkbox("Active only", value=True)
        use_demo = st.checkbox("Fallback to tiny demo if Census fails", value=True)
        mc_raw = st.text_area(
            "Optional MC# list (QCMobile — needs fmcsa_web_key)",
            placeholder="MC-123456\nMC-654321",
            height=70,
        )
        mc_list = [x.strip() for x in mc_raw.splitlines() if x.strip()] if mc_raw else None
        if st.button("Pull carriers from FMCSA Census", type="primary", key="fc_pull"):
            with st.spinner("Querying FMCSA Company Census…"):
                rows, mode = search_new_carriers(
                    state=state,
                    use_demo_if_needed=use_demo,
                    mc_list=mc_list,
                    limit=int(limit),
                    max_power_units=int(max_pu) if max_pu > 0 else None,
                    use_census=True,
                )
            st.session_state["carrier_pull"] = rows
            st.info(f"{mode}")
            st.success(f"Pulled {len(rows)} carrier(s).")
        rows = st.session_state.get("carrier_pull") or []
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=320)
            if can(user, "find_carriers", "create") or is_super_admin(user):
                if st.button("Save pull to Carrier Leads", type="primary"):
                    a, u = upsert_carriers(rows)
                    st.success(f"Saved — added {a}, updated {u}.")
                    _refresh_carriers()

    with tab_import:
        up = st.file_uploader(
            "Upload carrier list",
            type=["csv", "xlsx", "xls", "pdf"],
            key="fc_up",
        )
        if up is not None:
            try:
                parsed = parse_carrier_upload(up.name, up.getvalue())
            except Exception as e:
                st.error(str(e))
                parsed = []
            st.write(f"Parsed {len(parsed)} carrier(s) from `{up.name}`")
            if parsed:
                st.dataframe(pd.DataFrame(parsed), use_container_width=True, hide_index=True)
                if can(user, "find_carriers", "create") or is_super_admin(user):
                    if st.button("Import into Carrier Leads", type="primary"):
                        a, u = upsert_carriers(parsed)
                        st.success(f"Imported — added {a}, updated {u}.")
                        _refresh_carriers()

    with tab_manual:
        with st.form("fc_manual"):
            company_name = st.text_input("Company / DBA")
            contact_name = st.text_input("Contact")
            email = st.text_input("Email")
            phone = st.text_input("Phone")
            mc_number = st.text_input("MC#")
            dot_number = st.text_input("DOT#")
            st_state = st.text_input("State", company.get("origin_area", "IL")[:2])
            equipment_type = st.selectbox(
                "Equipment", ["Reefer", "Dry Van", "Box Truck", "Flatbed", "Other"]
            )
            notes = st.text_area("Notes")
            if st.form_submit_button("Add carrier", type="primary"):
                if not (company_name or email or mc_number):
                    st.error("Need company, email, or MC#.")
                else:
                    upsert_carriers(
                        [
                            {
                                "company_name": company_name,
                                "contact_name": contact_name,
                                "email": email,
                                "phone": phone,
                                "mc_number": mc_number,
                                "dot_number": dot_number,
                                "state": st_state,
                                "equipment_type": equipment_type,
                                "notes": notes,
                                "source": "manual",
                                "lane_or_region": company.get("origin_area", ""),
                            }
                        ]
                    )
                    st.success("Added.")
                    _refresh_carriers()


def page_carrier_leads():
    st.title("Carrier Leads")
    user = _user()
    if not can(user, "carrier_leads", "read"):
        st.error("No access to Carrier Leads.")
        return
    st.caption(
        "Owner-operator recruiting memory. Color = stage. Converted = Hired under LogixTrek MC."
    )
    if not is_super_admin(user):
        st.info("You only see carriers assigned to you.")
    if using_cloud():
        st.success("☁️ Carrier tab: Google Sheet `carrier_leads`")
    else:
        st.warning("💾 Local carrier DB")

    leads = _refresh_carriers()
    f1, f2, f3, f4 = st.columns(4)
    f_state = f1.text_input("State", "", key="cl_state")
    f_equip = f2.text_input("Equipment contains", "", key="cl_eq")
    f_status = f3.selectbox(
        "Stage",
        [""] + list(STAGE_STYLE.keys()),
        format_func=lambda s: stage_label(s) if s else "All stages",
        key="cl_status",
    )
    hide_dnc = f4.checkbox("Hide DNC", value=False, key="cl_dnc")

    filtered = filter_carriers(
        leads,
        state=f_state or None,
        equipment_type=f_equip or None,
        status=f_status or None,
        hide_dnc=hide_dnc,
    )
    if not filtered:
        st.warning("No carriers yet. Use Find Carriers to import or pull.")
        return

    rows = []
    for l in filtered:
        row = {
            "Stage": stage_label(l.get("status") or "not_started"),
            "Indicator": _carrier_indicator(l),
            "Company": l.get("company_name") or "",
            "Contact": l.get("contact_name") or "",
            "Email": l.get("email") or "",
            "Phone": l.get("phone") or "",
            "MC": l.get("mc_number") or "",
            "DOT": l.get("dot_number") or "",
            "State": l.get("state") or "",
            "Equipment": l.get("equipment_type") or "",
            "Emails sent": int(l.get("contact_count") or 0),
            "Remarks": l.get("remarks") or "",
            "_key": carrier_key(l),
        }
        if is_super_admin(user):
            row["Assigned"] = _assignee_name(l.get("assigned_to") or "")
        rows.append(row)

    df = pd.DataFrame(rows)
    st.dataframe(
        _style_status(df.drop(columns=["_key"])),
        use_container_width=True,
        hide_index=True,
        height=420,
    )

    if not can(user, "carrier_leads", "update"):
        return

    labels = {
        f"{r['Company']} <{r['Email'] or r['MC']}> — {r['Stage']}": r["_key"] for r in rows
    }
    pick = st.selectbox("Select carrier", list(labels.keys()), key="cl_pick")
    key = labels[pick]
    lead = next(l for l in leads if carrier_key(l) == key)

    r1, r2 = st.columns(2)
    with r1:
        new_remarks = st.text_area("Remarks", value=lead.get("remarks") or "", height=90)
        new_email = st.text_input("Email", value=lead.get("email") or "")
        new_phone = st.text_input("Phone", value=lead.get("phone") or "")
    with r2:
        st.write(f"**{_carrier_indicator(lead)}**")
        st.write(f"**MC:** {lead.get('mc_number') or '—'} · **DOT:** {lead.get('dot_number') or '—'}")
        st.write(f"**Assigned:** {_assignee_name(lead.get('assigned_to') or '')}")

    b1, b2, b3, b4 = st.columns(4)
    if b1.button("Save", type="primary", key="cl_save"):
        lead["remarks"] = new_remarks
        lead["email"] = new_email
        lead["phone"] = new_phone
        _persist_one(lead)
        st.success("Saved.")
        st.rerun()
    if b2.button("Mark Hired ✅", key="cl_hire"):
        mark_carrier_hired(lead)
        _persist_one(lead)
        st.success("Hired under MC.")
        st.rerun()
    if b3.button("Do Not Contact 🚫", key="cl_dncbtn"):
        mark_carrier_response(lead, positive=False)
        _persist_one(lead)
        st.success("Locked.")
        st.rerun()
    if b4.button("Mark Responded 📞", key="cl_resp"):
        mark_carrier_response(lead, positive=True)
        _persist_one(lead)
        st.success("Sequence stopped.")
        st.rerun()


def page_carrier_pipeline():
    st.title("Carrier Pipeline")
    user = _user()
    if not can(user, "carrier_pipeline", "read"):
        st.error("No access to Carrier Pipeline.")
        return
    company = _company()
    leads = _refresh_carriers()
    st.caption("4-email lease-on sequence · days 0 / 4 / 9 / 16 · dry-run until live SMTP.")

    filtered = filter_carriers(leads, hide_dnc=True)
    if not filtered:
        st.warning("No outreach-eligible carriers.")
        return

    key_by_idx = []
    rows = []
    for l in filtered:
        step = next_action_for_lead(l)
        key_by_idx.append(carrier_key(l))
        rows.append(
            {
                "Select": False,
                "Stage": stage_label(l.get("status") or "not_started"),
                "Indicator": _carrier_indicator(l),
                "Company": l.get("company_name"),
                "Email": l.get("email"),
                "MC": l.get("mc_number"),
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
        key="cpipe_editor",
    )
    selected_keys = [
        key_by_idx[i] for i, sel in enumerate(edited["Select"].tolist()) if sel
    ]
    force = st.checkbox("Force restart sequence", value=False, key="cpipe_force")

    a1, a2, a3 = st.columns(3)
    if a1.button("Activate selected", type="primary", key="cpipe_act"):
        if not can(user, "carrier_pipeline", "update"):
            st.error("No update permission.")
        elif not selected_keys:
            st.warning("Select carriers first.")
        else:
            n, skipped = activate_carrier_sequence(_all_carriers(), selected_keys, force=force)
            st.success(f"Activated {n}.")
            for s in skipped:
                st.warning(s)
            _refresh_carriers()

    if a2.button("Start — send due emails", key="cpipe_start"):
        if not can(user, "carrier_pipeline", "update"):
            st.error("No update permission.")
        else:
            keys = selected_keys or [
                carrier_key(l)
                for l in leads
                if l.get("active_sequence") and next_action_for_lead(l)
            ]
            if not keys:
                st.warning("Nothing due.")
            else:
                results = run_due_carrier_emails(_all_carriers(), company, only_keys=keys)
                mode = "LIVE" if company.get("send_live_emails") else "DRY RUN"
                st.success(f"Processed {len(results)} ({mode}).")
                for r in results:
                    if r.get("ok"):
                        st.write(f"✓ {r.get('lead')} → Email {r.get('step')}")
                        if not company.get("send_live_emails"):
                            with st.expander(f"Preview {r.get('lead')}"):
                                st.code(r.get("body", ""))
                    else:
                        st.error(f"✗ {r.get('lead')}: {r.get('error')}")
                _refresh_carriers()

    if a3.button("Mark selected Hired", key="cpipe_hire"):
        if not selected_keys:
            st.warning("Select first.")
        else:
            for l in _all_carriers():
                if carrier_key(l) in selected_keys and can_access_lead(user, l):
                    mark_carrier_hired(l)
                    update_carrier(l)
            st.success("Marked Hired.")
            st.rerun()

    with st.expander("Email 1–4 preview (carrier)"):
        sample = {
            "contact_name": "Alex",
            "company_name": "Sample Carrier LLC",
            "mc_number": "MC-999999",
            "state": "IL",
            "lane_or_region": "IL / Midwest",
        }
        for step in range(1, 5):
            subj, body = render_carrier_email(step, sample, company)
            st.markdown(f"**Email {step} — {subj}**")
            st.code(body)


def page_carrier_inbox():
    st.title("Carrier Inbox Bot")
    user = _user()
    if not can(user, "carrier_inbox", "read"):
        st.error("No access to Carrier Inbox.")
        return
    st.caption("Paste a carrier reply. Bot handles opt-out / interest; escalates pay / lease terms to you.")
    company = _company()
    leads = _refresh_carriers()
    with_email = [l for l in leads if l.get("email")]
    if not with_email:
        st.warning("Add carriers with email first.")
        return

    labels = {
        f"{l.get('company_name')} <{l.get('email')}> [{stage_label(l.get('status'))}]": l
        for l in with_email
    }
    choice = st.selectbox("Which carrier replied?", list(labels.keys()), key="cib_pick")
    lead = labels[choice]
    inbound = st.text_area("Paste their reply", height=160, key="cib_in")

    if st.button("Process with Carrier Bot", type="primary", key="cib_go") and inbound.strip():
        decision = handle_reply(lead, inbound, company)
        st.markdown(f"**Intent:** `{decision.intent}`")
        if decision.stop_sequence:
            mark_carrier_response(lead, positive=decision.mark_positive)
            st.info("Sequence stopped.")

        conv = lead.get("conversation") or []
        conv.append(
            {
                "at": __import__("datetime").datetime.now().isoformat(),
                "direction": "inbound",
                "body": inbound,
                "intent": decision.intent,
                "funnel": "carrier",
            }
        )

        if decision.auto_send and company.get("bot_auto_reply", True) and decision.reply_body:
            from src.emailer import send_email

            result = send_email(
                lead["email"],
                decision.reply_subject,
                decision.reply_body,
                company,
                meta={"type": "carrier_bot_reply", "intent": decision.intent},
            )
            conv.append(
                {
                    "at": result["at"],
                    "direction": "outbound_bot",
                    "subject": decision.reply_subject,
                    "body": decision.reply_body,
                    "mode": result.get("mode"),
                }
            )
            st.success(f"Bot reply {'sent' if result.get('live') else 'drafted (dry run)'}.")
            with st.expander("Bot reply"):
                st.code(decision.reply_body)
        elif decision.intent == "escalate":
            st.warning("Escalated — you close lease-on / pay terms yourself.")

        if decision.escalate_to_owner and decision.owner_alert:
            notify_owner(
                company,
                f"CARRIER {decision.intent.upper()}: {lead.get('company_name')}",
                decision.owner_alert,
            )
            st.info("Owner alert logged.")

        rem = lead.get("remarks") or ""
        tag = f"CarrierReply:{decision.intent}"
        if tag not in rem:
            lead["remarks"] = (rem + f" | {tag}").strip(" |")
        lead["conversation"] = conv
        _persist_one(lead)
        _refresh_carriers()
