"""
LogixTrek Direct Shipper Outreach — free web app
Host on Streamlit Community Cloud. Leads persist in Google Sheets.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.bot import handle_reply
from src.campaign import run_due_emails
from src.company import load_company, save_company
from src.leads import (
    activate_sequence,
    filter_leads,
    lead_key,
    load_leads,
    mark_converted,
    mark_response,
    parse_import_csv,
    persist_lead_tracking,
    upsert_leads,
)
from src.notify import notify_owner
from src.places import demo_places_results, search_places
from src.find_vet import find_and_vet_shippers
from src.carrier_pages import (
    page_carrier_inbox,
    page_carrier_leads,
    page_carrier_pipeline,
    page_find_carriers,
)
from src.carrier_leads import load_carriers, persist_carriers
from src.rbac import (
    ACTIONS,
    MODULES,
    ROLE_PRESETS,
    allowed_pages,
    assign_carriers,
    assign_leads,
    authenticate,
    can,
    can_access_lead,
    create_user,
    delete_user,
    ensure_super_admin_pin,
    is_super_admin,
    list_users,
    load_rbac_state,
    module_choices_for_team,
    role_choices,
    scope_leads,
    sync_super_admin_profile,
    update_user,
)
from src.schedule import days_until_next, next_action_for_lead
from src.stages import STAGE_STYLE, contact_indicator, stage_label
from src.storage import update_lead, using_cloud
from src.cloud_setup import build_simple_secrets_toml, secret_status
from src.templates import render_email

st.set_page_config(
    page_title="LogixTrek Direct Shipper Outreach",
    page_icon="🚛",
    layout="wide",
)

st.markdown(
    """
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&display=swap');

  :root {
    --lg-blue: #0EA5E9;
    --lg-teal: #14B8A6;
    --lg-green: #10B981;
    --lg-deep: #0B3D4A;
    --lg-glass: rgba(255, 255, 255, 0.45);
    --lg-glass-border: rgba(255, 255, 255, 0.65);
    --lg-shadow: 0 8px 32px rgba(14, 165, 233, 0.12);
  }

  html, body, [class*="css"] {
    font-family: "DM Sans", system-ui, sans-serif !important;
  }

  .stApp {
    background:
      radial-gradient(1200px 600px at 10% -10%, rgba(14, 165, 233, 0.35), transparent 55%),
      radial-gradient(900px 500px at 90% 0%, rgba(16, 185, 129, 0.28), transparent 50%),
      radial-gradient(800px 400px at 50% 100%, rgba(20, 184, 166, 0.22), transparent 45%),
      linear-gradient(165deg, #E0F2FE 0%, #ECFDF5 45%, #CCFBF1 100%) !important;
    color: var(--lg-deep);
  }

  .block-container {
    padding-top: 1.25rem;
    max-width: 1280px;
  }

  /* Sidebar glass */
  section[data-testid="stSidebar"] {
    background: rgba(255, 255, 255, 0.38) !important;
    backdrop-filter: blur(18px) saturate(1.35);
    -webkit-backdrop-filter: blur(18px) saturate(1.35);
    border-right: 1px solid var(--lg-glass-border) !important;
    box-shadow: 4px 0 24px rgba(11, 61, 74, 0.06);
  }
  section[data-testid="stSidebar"] .stMarkdown h3 {
    background: linear-gradient(90deg, var(--lg-blue), var(--lg-teal));
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent !important;
    font-weight: 700;
  }

  /* Headers */
  h1, h2, h3 {
    color: var(--lg-deep) !important;
    letter-spacing: -0.02em;
  }

  /* Metrics as glass cards */
  div[data-testid="stMetric"] {
    background: var(--lg-glass);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border: 1px solid var(--lg-glass-border);
    border-radius: 16px;
    padding: 0.85rem 1rem;
    box-shadow: var(--lg-shadow);
  }
  div[data-testid="stMetricValue"] {
    font-size: 1.4rem;
    color: var(--lg-deep) !important;
  }

  /* Primary buttons — liquid glass */
  div.stButton > button[kind="primary"],
  div.stButton > button[data-testid="baseButton-primary"],
  button[kind="primary"] {
    background: linear-gradient(135deg, rgba(14, 165, 233, 0.92), rgba(20, 184, 166, 0.92)) !important;
    color: #fff !important;
    border: 1px solid rgba(255, 255, 255, 0.45) !important;
    border-radius: 14px !important;
    box-shadow: 0 6px 20px rgba(14, 165, 233, 0.28), inset 0 1px 0 rgba(255,255,255,0.35) !important;
    backdrop-filter: blur(8px);
    font-weight: 600 !important;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
  }
  div.stButton > button[kind="primary"]:hover,
  button[kind="primary"]:hover {
    transform: translateY(-1px);
    box-shadow: 0 10px 28px rgba(16, 185, 129, 0.35), inset 0 1px 0 rgba(255,255,255,0.4) !important;
  }

  /* Secondary / default buttons */
  div.stButton > button,
  div.stDownloadButton > button {
    background: rgba(255, 255, 255, 0.5) !important;
    border: 1px solid rgba(14, 165, 233, 0.35) !important;
    border-radius: 14px !important;
    color: var(--lg-deep) !important;
    backdrop-filter: blur(10px);
    box-shadow: 0 4px 14px rgba(14, 165, 233, 0.1);
    font-weight: 550 !important;
  }
  div.stButton > button:hover {
    border-color: var(--lg-teal) !important;
    background: rgba(255, 255, 255, 0.72) !important;
  }

  /* Tabs — pill glass */
  div[data-testid="stTabs"] {
    background: rgba(255, 255, 255, 0.35);
    backdrop-filter: blur(12px);
    border: 1px solid var(--lg-glass-border);
    border-radius: 18px;
    padding: 0.4rem 0.5rem 0.75rem;
    box-shadow: var(--lg-shadow);
  }
  button[data-baseweb="tab"] {
    border-radius: 999px !important;
    color: var(--lg-deep) !important;
    font-weight: 500 !important;
  }
  button[data-baseweb="tab"][aria-selected="true"] {
    background: linear-gradient(135deg, rgba(14, 165, 233, 0.25), rgba(16, 185, 129, 0.3)) !important;
    box-shadow: inset 0 0 0 1px rgba(14, 165, 233, 0.35);
  }
  div[data-baseweb="tab-highlight"] {
    background: transparent !important;
  }
  div[data-baseweb="tab-border"] {
    display: none !important;
  }

  /* Inputs / select / text area glass */
  div[data-testid="stTextInput"] input,
  div[data-testid="stTextArea"] textarea,
  div[data-testid="stNumberInput"] input,
  div[data-baseweb="select"] > div,
  div[data-testid="stFileUploader"] section {
    background: rgba(255, 255, 255, 0.55) !important;
    border-radius: 12px !important;
    border: 1px solid rgba(14, 165, 233, 0.25) !important;
    backdrop-filter: blur(8px);
  }

  /* Alerts / banners */
  div[data-testid="stAlert"] {
    background: rgba(255, 255, 255, 0.55) !important;
    backdrop-filter: blur(12px);
    border-radius: 14px !important;
    border: 1px solid var(--lg-glass-border) !important;
    box-shadow: var(--lg-shadow);
  }

  /* Dataframe / editor */
  div[data-testid="stDataFrame"],
  div[data-testid="stDataEditor"] {
    background: rgba(255, 255, 255, 0.5);
    backdrop-filter: blur(10px);
    border-radius: 16px;
    border: 1px solid var(--lg-glass-border);
    overflow: hidden;
    box-shadow: var(--lg-shadow);
  }

  /* Expander */
  div[data-testid="stExpander"] {
    background: rgba(255, 255, 255, 0.4);
    border-radius: 14px;
    border: 1px solid var(--lg-glass-border);
    backdrop-filter: blur(10px);
  }

  /* Forms */
  div[data-testid="stForm"] {
    background: rgba(255, 255, 255, 0.4);
    backdrop-filter: blur(14px);
    border: 1px solid var(--lg-glass-border);
    border-radius: 18px;
    padding: 1rem 1.1rem 0.5rem;
    box-shadow: var(--lg-shadow);
  }

  /* Sidebar chevron nav (buttons, not radios) */
  section[data-testid="stSidebar"] div.stButton > button {
    width: 100% !important;
    justify-content: flex-start !important;
    text-align: left !important;
    border-radius: 12px !important;
    padding: 0.4rem 0.75rem !important;
    margin: 0.06rem 0 !important;
    font-size: 0.95rem !important;
    font-weight: 500 !important;
    border: 1px solid rgba(14, 165, 233, 0.18) !important;
    background: rgba(255, 255, 255, 0.35) !important;
    box-shadow: none !important;
    transform: none !important;
    min-height: 2.1rem !important;
  }
  section[data-testid="stSidebar"] div.stButton > button[kind="primary"],
  section[data-testid="stSidebar"] div.stButton > button[data-testid="baseButton-primary"] {
    font-size: 1.08rem !important;
    font-weight: 700 !important;
    padding: 0.5rem 0.85rem !important;
    min-height: 2.45rem !important;    background: linear-gradient(
      135deg,
      rgba(14, 165, 233, 0.92),
      rgba(20, 184, 166, 0.9),
      rgba(16, 185, 129, 0.88)
    ) !important;
    color: #fff !important;
    border: 1px solid rgba(255, 255, 255, 0.55) !important;
    box-shadow:
      0 0 0 1px rgba(14, 165, 233, 0.25),
      0 0 20px rgba(14, 165, 233, 0.45),
      0 0 36px rgba(16, 185, 129, 0.28),
      inset 0 1px 0 rgba(255, 255, 255, 0.4) !important;
  }
  section[data-testid="stSidebar"] div.stButton > button:hover {
    border-color: rgba(20, 184, 166, 0.55) !important;
    background: rgba(255, 255, 255, 0.55) !important;
  }
  section[data-testid="stSidebar"] div.stButton > button[kind="primary"]:hover {
    background: linear-gradient(
      135deg,
      rgba(14, 165, 233, 1),
      rgba(16, 185, 129, 0.95)
    ) !important;
    color: #fff !important;
  }
  /* Nested funnel pages (● / ○) sit slightly indented via label spacing */
  section[data-testid="stSidebar"] div.stButton > button p {
    text-align: left !important;
  }

  /* Slider */
  div[data-testid="stSlider"] [role="slider"] {
    background: linear-gradient(135deg, var(--lg-blue), var(--lg-green)) !important;
  }

  .stage-legend span {
    display: inline-block;
    padding: 4px 12px;
    margin: 3px 6px 3px 0;
    border-radius: 999px;
    font-size: 0.82rem;
    border: 1px solid rgba(255,255,255,0.55);
    backdrop-filter: blur(6px);
    box-shadow: 0 2px 8px rgba(11, 61, 74, 0.06);
  }

  /* Code blocks softer glass */
  code, pre {
    border-radius: 10px !important;
  }
</style>
""",
    unsafe_allow_html=True,
)


def _company() -> dict:
    if "company" not in st.session_state:
        # Prefer Streamlit secrets overrides for cloud
        cfg = load_company()
        try:
            if "company" in st.secrets:
                cfg.update(dict(st.secrets["company"]))
            for k in (
                "smtp_password",
                "google_places_api_key",
                "gemini_api_key",
                "google_cse_api_key",
                "google_cse_id",
                "smtp_host",
                "smtp_user",
                "my_email",
            ):
                if k in st.secrets:
                    cfg[k] = st.secrets[k]
            if st.secrets.get("send_live_emails") is not None:
                cfg["send_live_emails"] = bool(st.secrets["send_live_emails"])
        except Exception:
            pass
        st.session_state.company = cfg
    return st.session_state.company


def _current_user() -> dict | None:
    return st.session_state.get("auth_user")


def _secrets_super_pin() -> str:
    try:
        return str(st.secrets.get("super_admin_pin", "") or "").strip()
    except Exception:
        return ""


def _require_auth() -> dict | None:
    """Show login until authenticated. Returns current user or None."""
    user = _current_user()
    if user:
        return user

    st.markdown("### LogixTrek Outreach")
    st.caption("Sign in — Super Admin sees everything; team only sees assigned leads.")
    company = _company()
    with st.form("login_form"):
        email = st.text_input(
            "Work email",
            value=company.get("my_email", "accounts@logixtrek.com"),
        )
        pin = st.text_input("PIN", type="password", help="Owner: set super_admin_pin in Secrets, or create PIN on first login (4+ digits).")
        submitted = st.form_submit_button("Sign in", type="primary")
    if submitted:
        authed = authenticate(
            email,
            pin,
            company_email=company.get("my_email", ""),
            secrets_pin=_secrets_super_pin(),
        )
        if authed:
            st.session_state.auth_user = authed
            if is_super_admin(authed):
                sync_super_admin_profile(
                    load_rbac_state(),
                    name=company.get("my_name") or "Super Admin",
                    email=company.get("my_email") or email,
                )
            st.rerun()
        st.error("Wrong email or PIN.")
    st.info(
        "You are **Super Admin** at your owner email. Add teammates under **Org Setup → Team & Access** after you sign in."
    )
    return None


def _all_leads() -> list[dict]:
    """Full database — never save a scoped list back with persist_lead_tracking."""
    try:
        leads = load_leads()
        st.session_state.pop("_storage_error", None)
        return leads
    except Exception as e:
        st.session_state["_storage_error"] = str(e)
        return list(st.session_state.get("leads_all") or [])


def _refresh_leads() -> list[dict]:
    """Leads visible to the signed-in user (assignment scoped)."""
    all_leads = _all_leads()
    st.session_state.leads_all = all_leads
    if st.session_state.get("_storage_error"):
        st.error(
            "Cloud DB could not load leads. Reboot the app after Secrets changes, "
            "and confirm the service account is an Editor on your Google Sheet. "
            f"Detail: {st.session_state['_storage_error'][:300]}"
        )
    visible = scope_leads(all_leads, _current_user())
    st.session_state.leads = visible
    return visible


def _persist_one(lead: dict) -> None:
    """Safe single-lead save — does not wipe other teammates' leads."""
    user = _current_user()
    if not can_access_lead(user, lead) and not is_super_admin(user):
        st.error("No access to that lead.")
        return
    if not can(user, "leads", "update") and not is_super_admin(user):
        st.error("No update permission.")
        return
    update_lead(lead)


def _storage_banner():
    if using_cloud():
        st.success("☁️ Cloud mode — all contacted leads are saved permanently in your Google Sheet.")
    else:
        st.warning(
            "💾 Local mode — fine for testing. For the free internet app, connect a Google Sheet "
            "in **Cloud Hosting** so records survive and you never re-bother the same people."
        )


def _assignee_name(user_id: str, users: list[dict] | None = None) -> str:
    if not user_id:
        return "Unassigned (owner pool)"
    users = users or list_users(include_super=True)
    for u in users:
        if u.get("id") == user_id:
            return f"{u.get('name')} ({u.get('role')})"
    return user_id


def _legend_html() -> str:
    bits = []
    for status, (label, bg, fg) in STAGE_STYLE.items():
        bits.append(
            f'<span style="background:{bg};color:{fg};">{label}</span>'
        )
    return '<div class="stage-legend">' + "".join(bits) + "</div>"


def _style_status_column(df: pd.DataFrame):
    def paint(val):
        # val is stage label text — map back
        for status, (label, bg, fg) in STAGE_STYLE.items():
            if val == label:
                return f"background-color: {bg}; color: {fg}; font-weight: 600;"
        return ""

    return df.style.map(paint, subset=["Stage"])


def page_dashboard():
    company = _company()
    user = _current_user()
    leads = _refresh_leads() if can(user, "leads", "read") or is_super_admin(user) else []
    _storage_banner()

    from src.involvement import involvement_report

    inv = involvement_report(include_optional_paca=False)
    st.metric(
        "Your involvement (target ≤10%)",
        f"{inv['involvement_pct']}%",
        delta="under target" if inv["under_target"] else "over target",
    )
    st.caption(inv["summary"])

    active = [l for l in leads if l.get("active_sequence")]
    due = [l for l in active if next_action_for_lead(l) is not None]
    responded = [l for l in leads if l.get("status") == "responded"]
    converted = [l for l in leads if l.get("status") == "converted"]
    dnc = [l for l in leads if l.get("status") == "do_not_contact"]
    contacted = [
        l
        for l in leads
        if (l.get("status") or "not_started") != "not_started"
        or int(l.get("contact_count") or 0) > 0
    ]

    st.title("Direct Shipper Outreach")
    st.caption(
        f"{company.get('my_company')} · {company.get('my_mc')} · "
        f"{'🟢 LIVE EMAIL' if company.get('send_live_emails') else '🟡 DRY RUN (safe)'}"
    )

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Shipper leads", len(leads))
    c2.metric("Contacted", len(contacted))
    c3.metric("Active", len(active))
    c4.metric("Due today", len(due))
    c5.metric("Responded", len(responded))
    c6.metric("Converted", len(converted))

    if can(user, "carrier_leads", "read") or is_super_admin(user):
        try:
            carriers = scope_leads(load_carriers(), user)
        except Exception:
            carriers = []
        ca = [l for l in carriers if l.get("active_sequence")]
        ch = [l for l in carriers if l.get("status") == "converted"]
        st.subheader("Carrier onboarding (lease-on under our MC)")
        x1, x2, x3, x4 = st.columns(4)
        x1.metric("Carrier leads", len(carriers))
        x2.metric("Carrier active", len(ca))
        x3.metric("Hired under MC", len(ch))
        x4.metric(
            "Carrier due",
            len([l for l in ca if next_action_for_lead(l) is not None]),
        )

    st.markdown(_legend_html(), unsafe_allow_html=True)
    st.caption(f"🚫 Do Not Contact locked: {len(dnc)} — these people will never be emailed again.")

    st.subheader("What to do next")
    if due:
        st.success(f"{len(due)} shipper lead(s) due — open **Pipeline** and click Start.")
    elif can(user, "carrier_pipeline", "read"):
        st.info("Check **Find Carriers** / **Carrier Pipeline**, or shipper **Find Leads**.")
    elif not leads:
        st.info("Open **Find Leads**, search by state/zip, add emails, then activate.")
    else:
        st.info("Check **Leads List** for color-coded status, or find more leads.")


def page_leads_list():
    st.title("Leads List")
    user = _current_user()
    if not can(user, "leads", "read"):
        st.error("No access to Leads.")
        return
    st.caption(
        "Your permanent contact record. Color = stage. "
        "Do Not Contact and finished sequences are blocked from repeat spam."
    )
    if not is_super_admin(user):
        st.info("You only see leads assigned to you by Super Admin.")
    _storage_banner()
    st.markdown(_legend_html(), unsafe_allow_html=True)

    leads = _refresh_leads()
    team = list_users(include_super=True)
    f1, f2, f3, f4, f5 = st.columns(5)
    with f1:
        f_state = st.text_input("State", "", key="list_state")
    with f2:
        f_zip = st.text_input("Zip prefix", "", key="list_zip")
    with f3:
        f_freight = st.selectbox(
            "Freight", ["", "Reefer", "Dry Van", "Box Truck"], key="list_freight"
        )
    with f4:
        f_status = st.selectbox(
            "Stage",
            [""] + list(STAGE_STYLE.keys()),
            format_func=lambda s: stage_label(s) if s else "All stages",
            key="list_status",
        )
    with f5:
        hide_dnc = st.checkbox("Hide Do Not Contact", value=False)

    filtered = filter_leads(
        leads,
        state=f_state or None,
        zip_prefix=f_zip or None,
        freight_type=f_freight or None,
        status=f_status or None,
        hide_dnc=hide_dnc,
    )

    if not filtered:
        st.warning("No leads yet. Use Find Leads to search or import.")
        return

    rows = []
    for l in filtered:
        row = {
            "Stage": stage_label(l.get("status") or "not_started"),
            "Indicator": contact_indicator(l),
            "Company": l.get("company_name") or "",
            "Contact": l.get("contact_name") or "",
            "Email": l.get("email") or "",
            "Phone": l.get("phone") or "",
            "State": l.get("state") or "",
            "Zip": l.get("zip") or "",
            "Freight": l.get("freight_type") or "",
            "Emails sent": int(l.get("contact_count") or 0),
            "Last emailed": (l.get("last_emailed") or "")[:10],
            "Remarks": l.get("remarks") or "",
            "Notes": l.get("notes") or "",
            "_key": lead_key(l),
        }
        if is_super_admin(user):
            row["Assigned"] = _assignee_name(l.get("assigned_to") or "", team)
        rows.append(row)

    df = pd.DataFrame(rows)
    display = df.drop(columns=["_key"])
    st.dataframe(
        _style_status_column(display),
        use_container_width=True,
        hide_index=True,
        height=420,
    )

    if not can(user, "leads", "update"):
        st.caption("Read-only access.")
        return

    st.subheader("Edit remarks / mark status")
    labels = {
        f"{r['Company']} <{r['Email']}> — {r['Stage']}": r["_key"] for r in rows
    }
    pick = st.selectbox("Select lead", list(labels.keys()))
    key = labels[pick]
    lead = next(l for l in leads if lead_key(l) == key)

    r1, r2 = st.columns(2)
    with r1:
        new_remarks = st.text_area("Remarks", value=lead.get("remarks") or "", height=100)
        new_notes = st.text_area("Notes", value=lead.get("notes") or "", height=80)
    with r2:
        st.write(f"**Indicator:** {contact_indicator(lead)}")
        st.write(f"**Stage:** {stage_label(lead.get('status') or 'not_started')}")
        st.write(f"**Assigned:** {_assignee_name(lead.get('assigned_to') or '', team)}")
        st.write(f"**Conversation messages:** {len(lead.get('conversation') or [])}")
        if lead.get("conversation"):
            with st.expander("History"):
                for msg in lead["conversation"][-8:]:
                    st.caption(
                        f"{msg.get('direction')} · {str(msg.get('at', ''))[:19]}"
                    )
                    st.text((msg.get("body") or "")[:500])

    b1, b2, b3, b4 = st.columns(4)
    if b1.button("Save remarks", type="primary"):
        lead["remarks"] = new_remarks
        lead["notes"] = new_notes
        _persist_one(lead)
        st.success("Saved.")
        st.rerun()
    if b2.button("Mark Converted ✅"):
        mark_converted(lead)
        _persist_one(lead)
        st.success("Converted.")
        st.rerun()
    if b3.button("Do Not Contact 🚫"):
        if can(user, "leads", "delete") or is_super_admin(user):
            mark_response(lead, positive=False)
            _persist_one(lead)
            st.success("Locked — will never email again.")
            st.rerun()
        else:
            st.error("No delete / DNC permission.")
    if b4.button("Mark Responded 📞"):
        mark_response(lead, positive=True)
        _persist_one(lead)
        st.success("Sequence stopped — they replied.")
        st.rerun()


def _page_team_access():
    """Super Admin only — team CRUD + lead assignment."""
    if not is_super_admin(_current_user()):
        st.error("Only Super Admin can manage team access.")
        return

    state = load_rbac_state()
    company = _company()
    st.subheader("Your Super Admin account")
    st.write(f"**{company.get('my_email') or state['super_admin'].get('email')}** — full access to every module and every lead.")

    with st.expander("Change Super Admin PIN"):
        with st.form("sa_pin_form"):
            new_pin = st.text_input("New PIN (4+ characters)", type="password")
            confirm = st.text_input("Confirm PIN", type="password")
            if st.form_submit_button("Update PIN", type="primary"):
                if len(new_pin) < 4 or new_pin != confirm:
                    st.error("PINs must match and be at least 4 characters.")
                else:
                    ensure_super_admin_pin(state, new_pin)
                    sync_super_admin_profile(
                        load_rbac_state(),
                        name=company.get("my_name") or "Super Admin",
                        email=company.get("my_email") or "",
                    )
                    st.success("Super Admin PIN updated. Also set `super_admin_pin` in Streamlit Secrets as a backup.")

    st.divider()
    st.subheader("Team members")
    st.caption(
        "Nurturers / Reps only see leads you assign. Managers get broader CRUD on their assigned pool. "
        "Org Setup & Cloud Hosting stay Super Admin only."
    )

    team = [u for u in list_users(state, include_super=False)]
    if team:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Name": u.get("name"),
                        "Email": u.get("email"),
                        "Role": ROLE_PRESETS.get(u.get("role"), {}).get("label", u.get("role")),
                        "Active": u.get("active", True),
                        "Modules": ", ".join(
                            f"{m}:{'/'.join(a)}"
                            for m, a in (u.get("module_access") or {}).items()
                        ),
                    }
                    for u in team
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No teammates yet — add one below.")

    with st.form("add_user_form"):
        st.markdown("#### Add teammate")
        c1, c2 = st.columns(2)
        name = c1.text_input("Name")
        email = c2.text_input("Email")
        role = st.selectbox(
            "Role",
            role_choices(),
            format_func=lambda r: ROLE_PRESETS[r]["label"],
        )
        pin = st.text_input("Temporary PIN", type="password")
        st.caption(f"Preset modules for {ROLE_PRESETS[role]['label']}: {ROLE_PRESETS[role].get('modules')}")
        if st.form_submit_button("Create user", type="primary"):
            try:
                create_user(state, name=name, email=email, pin=pin, role=role)
                st.success(f"Created {name}. Share their email + PIN privately.")
                st.rerun()
            except Exception as e:
                st.error(str(e))

    if team:
        st.markdown("#### Edit / remove teammate")
        pick_labels = {f"{u['name']} <{u['email']}>": u["id"] for u in team}
        pick = st.selectbox("Select user", list(pick_labels.keys()), key="edit_user_pick")
        uid = pick_labels[pick]
        user = next(u for u in team if u["id"] == uid)

        with st.form("edit_user_form"):
            ename = st.text_input("Name", value=user.get("name") or "")
            eemail = st.text_input("Email", value=user.get("email") or "")
            erole = st.selectbox(
                "Role",
                role_choices(),
                index=max(
                    0,
                    role_choices().index(user.get("role"))
                    if user.get("role") in role_choices()
                    else 0,
                ),
                format_func=lambda r: ROLE_PRESETS[r]["label"],
            )
            eactive = st.toggle("Active", value=bool(user.get("active", True)))
            epin = st.text_input("Reset PIN (leave blank to keep)", type="password")

            st.markdown("**Module CRUD** (scalable — new modules appear here when registered)")
            access = dict(user.get("module_access") or {})
            new_access: dict[str, list[str]] = {}
            for mid in module_choices_for_team():
                label = MODULES[mid]["label"]
                cols = st.columns(len(ACTIONS) + 1)
                cols[0].markdown(f"**{label}**")
                chosen = []
                current = set(access.get(mid) or [])
                for i, act in enumerate(ACTIONS):
                    if cols[i + 1].checkbox(
                        act,
                        value=act in current,
                        key=f"perm_{uid}_{mid}_{act}",
                    ):
                        chosen.append(act)
                if chosen:
                    new_access[mid] = chosen

            save_btn = st.form_submit_button("Save user", type="primary")
            del_btn = st.form_submit_button("Remove user")
            if save_btn:
                try:
                    update_user(
                        load_rbac_state(),
                        uid,
                        name=ename,
                        email=eemail,
                        role=erole,
                        active=eactive,
                        module_access=new_access,
                        pin=epin or None,
                    )
                    st.success("User updated.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
            if del_btn:
                delete_user(load_rbac_state(), uid)
                st.success("User removed.")
                st.rerun()

    st.divider()
    st.subheader("Assign leads to team")
    st.caption("Unassigned leads stay in your owner pool — teammates cannot see them.")
    assignees = list_users(include_super=False)
    if not assignees:
        st.warning("Add a teammate before assigning.")
        return

    assign_options = {f"{u['name']} <{u['email']}>": u["id"] for u in assignees}
    assign_options["— Unassign (owner pool) —"] = ""
    who = st.selectbox("Assign to", list(assign_options.keys()), key="assign_who")
    assignee_id = assign_options[who]

    tab_ship, tab_car = st.tabs(["Shipper leads", "Carrier leads"])
    with tab_ship:
        all_leads = _all_leads()
        if not all_leads:
            st.warning("No shipper leads to assign yet.")
        else:
            rows = []
            key_by_idx = []
            for l in all_leads:
                key_by_idx.append(lead_key(l))
                rows.append(
                    {
                        "Select": False,
                        "Company": l.get("company_name") or "",
                        "Email": l.get("email") or "",
                        "State": l.get("state") or "",
                        "Stage": stage_label(l.get("status") or "not_started"),
                        "Currently": _assignee_name(l.get("assigned_to") or ""),
                    }
                )
            edited = st.data_editor(
                pd.DataFrame(rows),
                hide_index=True,
                use_container_width=True,
                disabled=[c for c in rows[0].keys() if c != "Select"],
                key="assign_editor",
                height=280,
            )
            selected = [
                key_by_idx[i] for i, sel in enumerate(edited["Select"].tolist()) if sel
            ]
            if st.button("Apply shipper assignment", type="primary", key="assign_ship_btn"):
                if not selected:
                    st.warning("Select at least one lead.")
                else:
                    updated, n = assign_leads(all_leads, selected, assignee_id)
                    persist_lead_tracking(updated)
                    st.success(f"Updated assignment on {n} shipper lead(s).")
                    st.rerun()

    with tab_car:
        try:
            all_carriers = load_carriers()
        except Exception as e:
            st.error(f"Could not load carriers: {e}")
            all_carriers = []
        if not all_carriers:
            st.warning("No carrier leads to assign yet.")
        else:
            from src.carrier_leads import carrier_key as _ck

            rows = []
            key_by_idx = []
            for l in all_carriers:
                key_by_idx.append(_ck(l))
                rows.append(
                    {
                        "Select": False,
                        "Company": l.get("company_name") or "",
                        "Email": l.get("email") or "",
                        "MC": l.get("mc_number") or "",
                        "State": l.get("state") or "",
                        "Stage": stage_label(l.get("status") or "not_started"),
                        "Currently": _assignee_name(l.get("assigned_to") or ""),
                    }
                )
            edited = st.data_editor(
                pd.DataFrame(rows),
                hide_index=True,
                use_container_width=True,
                disabled=[c for c in rows[0].keys() if c != "Select"],
                key="assign_carrier_editor",
                height=280,
            )
            selected = [
                key_by_idx[i] for i, sel in enumerate(edited["Select"].tolist()) if sel
            ]
            if st.button("Apply carrier assignment", type="primary", key="assign_car_btn"):
                if not selected:
                    st.warning("Select at least one carrier.")
                else:
                    updated, n = assign_carriers(all_carriers, selected, assignee_id)
                    persist_carriers(updated)
                    st.success(f"Updated assignment on {n} carrier lead(s).")
                    st.rerun()


def page_org_setup():
    st.title("Org Setup")
    user = _current_user()
    if not can(user, "org_setup", "read"):
        st.error("Only Super Admin can open Org Setup.")
        return

    tab_co, tab_team, tab_mail = st.tabs(
        ["Company & SMTP", "Team & Access (RBAC)", "Email templates (Shipper + Carrier)"]
    )

    company = _company()
    with tab_co:
        with st.form("org_form"):
            col1, col2 = st.columns(2)
            with col1:
                my_company = st.text_input("Company name", company.get("my_company", ""))
                my_name = st.text_input("Sender name", company.get("my_name", ""))
                my_phone = st.text_input("Phone", company.get("my_phone", ""))
                my_email = st.text_input("Sending email", company.get("my_email", ""))
                owner_notify_email = st.text_input(
                    "Alert me at", company.get("owner_notify_email", "")
                )
            with col2:
                my_mc = st.text_input("MC#", company.get("my_mc", ""))
                my_dot = st.text_input("DOT#", company.get("my_dot", ""))
                website = st.text_input("Website", company.get("website", ""))
                physical_address = st.text_input(
                    "Physical address", company.get("physical_address", "")
                )
                equipment = st.text_input("Equipment", company.get("equipment", ""))
                origin_area = st.text_input("Origin area", company.get("origin_area", ""))

            default_lanes = st.text_area("Lanes", company.get("default_lanes", ""))
            unsubscribe_note = st.text_area(
                "Email footer", company.get("unsubscribe_note", ""), height=70
            )

            st.markdown("#### SMTP")
            sc1, sc2, sc3 = st.columns(3)
            smtp_host = sc1.text_input("Host", company.get("smtp_host", "smtp.gmail.com"))
            smtp_port = sc2.number_input("Port", value=int(company.get("smtp_port", 587)))
            smtp_user = sc3.text_input("User", company.get("smtp_user", ""))
            smtp_password = st.text_input(
                "App password", value=company.get("smtp_password", ""), type="password"
            )
            send_live = st.toggle(
                "Send LIVE emails", value=bool(company.get("send_live_emails"))
            )
            google_key = st.text_input(
                "Google Places API key",
                value=company.get("google_places_api_key", ""),
                type="password",
            )
            gemini_key = st.text_input(
                "Gemini API key (AI Studio)",
                value=company.get("gemini_api_key", ""),
                type="password",
            )
            cse_key = st.text_input(
                "Google Custom Search API key",
                value=company.get("google_cse_api_key", ""),
                type="password",
            )
            cse_id = st.text_input(
                "Google Custom Search Engine ID (cx)",
                value=company.get("google_cse_id", ""),
            )
            bot_auto = st.toggle(
                "Bot auto-send safe replies", value=bool(company.get("bot_auto_reply", True))
            )

            if st.form_submit_button("Save", type="primary"):
                updated = {
                    **company,
                    "my_company": my_company,
                    "my_name": my_name,
                    "my_phone": my_phone,
                    "my_email": my_email,
                    "owner_notify_email": owner_notify_email,
                    "my_mc": my_mc,
                    "my_dot": my_dot,
                    "website": website,
                    "physical_address": physical_address,
                    "equipment": equipment,
                    "origin_area": origin_area,
                    "default_lanes": default_lanes,
                    "unsubscribe_note": unsubscribe_note
                    or f"{my_company} | {physical_address} | Reply STOP to opt out.",
                    "smtp_host": smtp_host,
                    "smtp_port": int(smtp_port),
                    "smtp_user": smtp_user,
                    "smtp_password": smtp_password,
                    "send_live_emails": send_live,
                    "google_places_api_key": google_key,
                    "gemini_api_key": gemini_key,
                    "google_cse_api_key": cse_key,
                    "google_cse_id": cse_id,
                    "bot_auto_reply": bot_auto,
                }
                try:
                    save_company(updated)
                except Exception:
                    pass  # cloud may be read-only for config file — secrets used instead
                st.session_state.company = updated
                sync_super_admin_profile(
                    load_rbac_state(),
                    name=my_name or "Super Admin",
                    email=my_email,
                )
                st.success("Saved for this session. On Streamlit Cloud, also put secrets in the app settings.")

    with tab_team:
        _page_team_access()

    with tab_mail:
        st.markdown("### Email templates — two funnels")
        st.caption(
            "Shipper emails sell **your truck capacity** to shippers. "
            "Carrier emails recruit **owner-operators to lease onto LogixTrek MC** (~$40k gross pitch)."
        )
        t_ship, t_car = st.tabs(["① Shipper templates (1–4)", "② Carrier / lease-on templates (1–4)"])
        company = _company()
        with t_ship:
            st.info("Used by **Shipper → Pipeline**. Cadence: days 0 / 4 / 9 / 16.")
            sample = {
                "contact_name": "Alex",
                "company_name": "Sample Shipper",
                "freight_type": "Reefer",
                "lane_or_region": "VA / Mid-Atlantic",
                "state": "VA",
            }
            for step in range(1, 5):
                subj, body = render_email(step, sample, company)
                st.markdown(f"**Shipper Email {step} — {subj}**")
                st.code(body)
        with t_car:
            from src.carrier_templates import render_carrier_email

            st.info("Used by **Carrier → Pipeline**. Same cadence: days 0 / 4 / 9 / 16.")
            sample_c = {
                "contact_name": "Jordan",
                "company_name": "Sample Owner-Op LLC",
                "mc_number": "MC-999999",
                "state": "VA",
                "lane_or_region": "VA / Mid-Atlantic",
            }
            for step in range(1, 5):
                subj, body = render_carrier_email(step, sample_c, company)
                st.markdown(f"**Carrier Email {step} — {subj}**")
                st.code(body)


def page_find_leads():
    st.title("Find & Vet Direct Shippers")
    user = _current_user()
    if not can(user, "find_leads", "read"):
        st.error("No access to Find Leads.")
        return
    st.caption(
        "Enter **State** (e.g. VA) — leave Zip blank for statewide multi-city Places pull. "
        "Expect **hundreds** of business matches (not 1000s of ready emails). "
        "Website enrichment fills emails when public; you top up blanks before Pipeline."
    )
    if not can(user, "find_leads", "create") and not is_super_admin(user):
        st.warning("Read-only: ask Super Admin for Find Leads create access, or work assigned leads in Pipeline.")
    company = _company()

    tab_vet, tab_paca, tab_import, tab_manual, tab_limits = st.tabs(
        [
            "Find & Vet (main)",
            "USDA PACA (reefer gold)",
            "Import CSV",
            "Add one lead",
            "Sources / limits",
        ]
    )

    with tab_vet:
        c1, c2, c3, c4 = st.columns(4)
        freight = c1.selectbox("Freight type", ["Reefer", "Dry Van", "Box Truck"], key="fv_fr")
        state = c2.text_input("State (2-letter)", "VA", key="fv_st")
        county = c3.text_input("County (optional)", "", key="fv_co")
        zip_code = c4.text_input("Zip (optional — blank = statewide)", "", key="fv_zip")
        min_score = st.slider("Minimum vet score to show", 5, 9, 6)
        max_candidates = st.slider(
            "Max shipper candidates to pull",
            50,
            500,
            200,
            step=50,
            help="Statewide hub search stops around this many unique businesses.",
        )
        enrich = st.checkbox("Check company websites for public emails", value=True)

        has_places = bool((company.get("google_places_api_key") or "").strip())
        has_gemini = bool((company.get("gemini_api_key") or "").strip())
        has_cse = bool(
            (company.get("google_cse_api_key") or "").strip()
            and (company.get("google_cse_id") or "").strip()
        )
        st.write(
            f"Places: {'ready' if has_places else 'missing'} · "
            f"Google Search (CSE): {'ready' if has_cse else 'missing'} · "
            f"Gemini: {'ready' if has_gemini else 'rules only'}"
        )
        if not has_places:
            st.error(
                "Add **google_places_api_key** in Secrets / Org Setup — without it you only get the tiny demo list."
            )

        b1, b2 = st.columns(2)
        run_live = b1.button("Find & Vet shippers", type="primary")
        run_demo = b2.button("Demo Find & Vet (no API keys)")

        if run_live or run_demo:
            status = st.empty()
            try:
                result = find_and_vet_shippers(
                    company,
                    freight_type=freight,
                    state=state,
                    county=county,
                    zip_code=zip_code,
                    min_score=min_score,
                    enrich_websites=enrich and not run_demo,
                    use_demo=bool(run_demo) or not has_places,
                    max_candidates=max_candidates,
                    progress_cb=lambda m: status.info(m),
                )
                st.session_state.vet_result = result
                status.success(
                    f"Done — {len(result['qualified'])} qualified / maybe from "
                    f"{len(result['candidates'])} raw "
                    f"(rejected {result['rejected_count']})."
                )
            except Exception as e:
                st.error(str(e))

        result = st.session_state.get("vet_result")
        if result:
            if result.get("used_demo"):
                st.warning(
                    "Demo / no Places key — sample companies only. "
                    "Add google_places_api_key in Streamlit Secrets for real local shippers."
                )
            qualified = list(result.get("qualified") or [])
            if not qualified:
                st.info("No leads passed the vet filter. Lower the min score or try another zip.")
            else:
                st.subheader("Vetted list — select who to load into pipeline")
                rows = []
                for q in qualified:
                    needs = "NEEDS EMAIL" if not (q.get("email") or "").strip() else "OK"
                    rows.append(
                        {
                            "Select": bool(q.get("email")),
                            "Fit": int(q.get("fit_score") or int(q.get("vet_score") or 0) * 10),
                            "Email?": needs,
                            "Status": q.get("vet_status") or "",
                            "Company": q.get("company_name") or "",
                            "Email": q.get("email") or "",
                            "Phone": q.get("phone") or "",
                            "City/Addr": (q.get("address") or "")[:60],
                            "Why vetted": (q.get("vet_reason") or q.get("remarks") or "")[:120],
                            "Source": q.get("source") or "",
                            "Website": q.get("website") or "",
                            "_id": q.get("id") or q.get("company_name"),
                        }
                    )
                edited = st.data_editor(
                    pd.DataFrame(rows),
                    hide_index=True,
                    use_container_width=True,
                    disabled=[c for c in rows[0].keys() if c not in ("Select", "Email")],
                    key="vet_editor",
                    height=360,
                )

                by_id = {q.get("id") or q.get("company_name"): q for q in qualified}
                to_save = []
                for _, row in edited.iterrows():
                    if not row.get("Select"):
                        continue
                    base = dict(by_id.get(row["_id"]) or {})
                    email = str(row.get("Email") or "").strip()
                    base["email"] = email
                    if not email:
                        st.warning(
                            f"{base.get('company_name')}: no email yet — type one in Email column."
                        )
                        continue
                    to_save.append(base)

                csave, cact = st.columns(2)
                if csave.button("Save selected vetted leads") and to_save:
                    added, updated = upsert_leads(to_save)
                    st.success(f"Saved {added} new, {updated} updated to Cloud DB.")
                    _refresh_leads()
                if cact.button("Save + Activate pipeline", type="primary") and to_save:
                    added, updated = upsert_leads(to_save)
                    leads = _refresh_leads()
                    keys = [lead_key(t) for t in to_save]
                    n, skipped = activate_sequence(leads, keys, force=False)
                    st.success(
                        f"Saved ({added}/{updated}) and activated {n}. Go to Pipeline → Start."
                    )
                    for s in skipped:
                        st.warning(s)
                    _refresh_leads()

            with st.expander("Show rejected / low-score (noise filtered out)"):
                qual_ids = {(q.get("id") or q.get("company_name")) for q in (result.get("qualified") or [])}
                weak = [
                    v
                    for v in (result.get("vetted") or [])
                    if (v.get("id") or v.get("company_name")) not in qual_ids
                ]
                if not weak:
                    st.write("None")
                else:
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {
                                    "Score": v.get("vet_score"),
                                    "Status": v.get("vet_status"),
                                    "Company": v.get("company_name"),
                                    "Reason": v.get("vet_reason"),
                                }
                                for v in weak
                            ]
                        ),
                        hide_index=True,
                        use_container_width=True,
                    )

    with tab_paca:
        from src.lead_discovery_agent import PACA_SEARCH_URL, paca_manual_search_instructions

        st.subheader("USDA PACA — best free reefer shipper list")
        st.markdown(
            f"""
This is a **federal** database of businesses licensed to buy/sell fresh & frozen produce
(your ideal reefer customer). Free and real.

**Live search (manual — site blocks bots):** [{PACA_SEARCH_URL}]({PACA_SEARCH_URL})

**2-minute workflow**
1. Open the link → search by **State** or **Zip / zip range**
2. Copy company name + city/state into Excel/Sheets
3. Save as CSV with columns: `company_name,state,zip,freight_type` (set freight_type to Reefer)
4. Use **Import CSV** tab — then Pipeline / Activate

{paca_manual_search_instructions("IL")}
"""
        )
        st.info(
            "We will not scrape PACA. Same rule as LinkedIn/ThomasNet — robots.txt says no bots."
        )

    with tab_import:
        st.markdown(
            "Import exports from ThomasNet / LinkedIn Sales Navigator / state agencies / PACA paste. "
            "We do not auto-scrape those sites (against their terms)."
        )
        uploaded = st.file_uploader("CSV", type=["csv"])
        if uploaded and st.button("Import"):
            rows = parse_import_csv(uploaded.read())
            if not rows:
                st.error("No rows found.")
            else:
                added, updated = upsert_leads(rows)
                st.success(f"Imported — {added} new, {updated} updated.")
                _refresh_leads()

    with tab_manual:
        with st.form("manual"):
            mc1, mc2 = st.columns(2)
            company_name = mc1.text_input("Company*")
            contact_name = mc1.text_input("Contact")
            email = mc1.text_input("Email*")
            phone = mc1.text_input("Phone")
            st_state = mc2.text_input("State")
            county_m = mc2.text_input("County")
            zip_m = mc2.text_input("Zip")
            freight_m = mc2.selectbox("Freight", ["Reefer", "Dry Van", "Box Truck", "Other"])
            lane = st.text_input("Lane")
            remarks = st.text_input("Remarks")
            if st.form_submit_button("Add"):
                if not company_name or not email:
                    st.error("Company + email required.")
                else:
                    upsert_leads(
                        [
                            {
                                "company_name": company_name,
                                "contact_name": contact_name,
                                "email": email,
                                "phone": phone,
                                "state": st_state,
                                "county": county_m,
                                "zip": zip_m,
                                "freight_type": freight_m,
                                "lane_or_region": lane,
                                "remarks": remarks,
                                "source": "manual",
                            }
                        ]
                    )
                    st.success("Added.")
                    _refresh_leads()

    with tab_limits:
        st.markdown(
            """
### Automated (legal)
| Source | What it does |
|--------|----------------|
| Google Places / Business | Statewide hub search (leave zip blank) — typically **hundreds** of businesses, not 1000s of emails |
| Google Programmable Search | Web results + read company sites for emails |
| Gemini LLM | Fit score 0–100 + one-line reason |
| Rules fallback | Works even without Gemini |

### Catch (read this)
- **Shippers:** need `google_places_api_key`. Blank zip = statewide. Emails are often empty until enrichment / manual fill.
- **Carriers:** **Carrier → Find Carriers** pulls FMCSA Census by state (VA can be 1000+). Emails usually blank; phone + MC are there.

### Manual but high-value
| Source | How |
|--------|-----|
| **USDA PACA** | 2 min search → CSV import (see PACA tab) |
| LinkedIn / ThomasNet / Yellow Pages | Export yourself → CSV import |

### Not scraped (ToS / robots.txt)
LinkedIn, ThomasNet, Yellow Pages directories, PACA live search automation, SAFER HTML pages.

### Your time after this
1. Find & Vet (or PACA CSV)
2. Select high Fit scores with email (or add email)
3. Save + Activate → Pipeline Start
4. Only jump in when Inbox Bot escalates rates / contracts / loads
"""
        )

def page_pipeline():
    st.title("Pipeline & Outreach")
    user = _current_user()
    if not can(user, "pipeline", "read"):
        st.error("No access to Pipeline.")
        return
    company = _company()
    leads = _refresh_leads()
    _storage_banner()
    if not is_super_admin(user):
        st.info("Pipeline shows only leads assigned to you.")

    f1, f2, f3 = st.columns(3)
    f_state = f1.text_input("State", "", key="pipe_state")
    f_zip = f2.text_input("Zip", "", key="pipe_zip")
    f_freight = f3.selectbox("Freight", ["", "Reefer", "Dry Van", "Box Truck"], key="pipe_fr")

    filtered = filter_leads(
        leads,
        state=f_state or None,
        zip_prefix=f_zip or None,
        freight_type=f_freight or None,
        hide_dnc=True,
    )
    if not filtered:
        st.warning("No outreach-eligible leads (DNC hidden).")
        return

    key_by_idx = []
    rows = []
    for l in filtered:
        step = next_action_for_lead(l)
        key_by_idx.append(lead_key(l))
        rows.append(
            {
                "Select": False,
                "Stage": stage_label(l.get("status") or "not_started"),
                "Indicator": contact_indicator(l),
                "Company": l.get("company_name"),
                "Email": l.get("email"),
                "State": l.get("state"),
                "Active": bool(l.get("active_sequence")),
                "Next": step if step else "—",
                "Days": days_until_next(l) if l.get("active_sequence") else "—",
                "Remarks": (l.get("remarks") or "")[:80],
            }
        )

    edited = st.data_editor(
        pd.DataFrame(rows),
        hide_index=True,
        use_container_width=True,
        disabled=[c for c in rows[0].keys() if c != "Select"],
        key="pipe_editor",
    )
    selected_keys = [
        key_by_idx[i] for i, sel in enumerate(edited["Select"].tolist()) if sel
    ]

    force = st.checkbox(
        "Force restart sequence on selected (still cannot email Do Not Contact)",
        value=False,
    )

    a1, a2, a3 = st.columns(3)
    if a1.button("Activate selected", type="primary"):
        if not can(user, "pipeline", "update"):
            st.error("No update permission.")
        elif not selected_keys:
            st.warning("Select leads first.")
        else:
            # Always mutate the full DB so other assignees are not wiped
            n, skipped = activate_sequence(_all_leads(), selected_keys, force=force)
            st.success(f"Activated {n}.")
            for s in skipped:
                st.warning(s)
            _refresh_leads()

    if a2.button("Start — send due emails"):
        if not can(user, "pipeline", "update"):
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
                full = _all_leads()
                results = run_due_emails(full, company, only_keys=keys)
                mode = "LIVE" if company.get("send_live_emails") else "DRY RUN"
                st.success(f"Processed {len(results)} ({mode}). Saved to permanent lead record.")
                for r in results:
                    if r.get("ok"):
                        st.write(f"✓ {r.get('lead')} → Email {r.get('step')} [{r.get('mode')}]")
                        if not company.get("send_live_emails"):
                            with st.expander(f"Preview {r.get('lead')}"):
                                st.code(r.get("body", ""))
                    else:
                        st.error(f"✗ {r.get('lead')}: {r.get('error')}")
                _refresh_leads()

    if a3.button("Mark selected Converted"):
        if not can(user, "pipeline", "update"):
            st.error("No update permission.")
        elif not selected_keys:
            st.warning("Select a lead first (checkbox), then click Converted.")
        else:
            full = _all_leads()
            for l in full:
                if lead_key(l) in selected_keys and can_access_lead(user, l):
                    mark_converted(l)
                    update_lead(l)
            st.success("Marked Converted. Open Leads List to see the green stage.")
            st.rerun()


def page_inbox():
    st.title("Inbox Bot")
    user = _current_user()
    if not can(user, "inbox", "read"):
        st.error("No access to Inbox Bot.")
        return
    st.caption("Paste a reply. Bot handles safe replies; escalates rates/contracts/loads to you.")
    if not is_super_admin(user):
        st.info("You only process replies for leads assigned to you.")
    company = _company()
    leads = _refresh_leads()
    with_email = [l for l in leads if l.get("email")]
    if not with_email:
        st.warning("Add leads first.")
        return

    labels = {
        f"{l.get('company_name')} <{l.get('email')}> [{stage_label(l.get('status'))}]": l
        for l in with_email
    }
    choice = st.selectbox("Which lead replied?", list(labels.keys()))
    lead = labels[choice]
    inbound = st.text_area("Paste their reply", height=160)

    if st.button("Process with Logistics Bot", type="primary") and inbound.strip():
        decision = handle_reply(lead, inbound, company)
        st.markdown(f"**Intent:** `{decision.intent}`")
        if decision.stop_sequence:
            mark_response(lead, positive=decision.mark_positive)
            st.info("Sequence stopped — recorded on lead forever.")

        conv = lead.get("conversation") or []
        conv.append(
            {
                "at": __import__("datetime").datetime.now().isoformat(),
                "direction": "inbound",
                "body": inbound,
                "intent": decision.intent,
            }
        )

        if decision.auto_send and company.get("bot_auto_reply", True) and decision.reply_body:
            from src.emailer import send_email

            result = send_email(
                lead["email"],
                decision.reply_subject,
                decision.reply_body,
                company,
                meta={"type": "bot_reply", "intent": decision.intent},
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
            st.warning("Escalated — you close rates / loads yourself.")

        if decision.escalate_to_owner and decision.owner_alert:
            notify_owner(
                company,
                f"{decision.intent.upper()}: {lead.get('company_name')}",
                decision.owner_alert,
            )
            st.info("Owner alert logged.")
            st.code(decision.owner_alert)

        rem = lead.get("remarks") or ""
        tag = f"Reply:{decision.intent}"
        if tag not in rem:
            lead["remarks"] = (rem + f" | {tag}").strip(" |")
        lead["conversation"] = conv
        _persist_one(lead)
        _refresh_leads()


def page_cloud():
    st.title("Cloud Hosting — fix Local DB")
    _storage_banner()

    status = secret_status()
    st.subheader("1) What the app sees right now")
    if status.get("error"):
        st.error(f"Could not read secrets: {status['error']}")
    st.write(f"Secret keys found: `{', '.join(status.get('keys') or ['(none)'])}`")
    st.write(
        f"Sheet ID: {'OK' if status.get('sheet_id_present') else 'MISSING'} "
        f"{status.get('sheet_id_preview') or ''}"
    )
    st.write(
        f"Service account loaded: {'OK' if status.get('gcp_loaded') else 'MISSING'} "
        f"{status.get('gcp_client_email') or ''}"
    )

    if using_cloud():
        st.success("Cloud secrets look present.")
        if st.button("Test Google Sheet connection"):
            try:
                from src.storage import test_sheet_connection

                st.success(test_sheet_connection())
            except Exception as e:
                st.error(f"Sheet connection failed: {e}")
                st.info(
                    "Most common fix: Share the Sheet with the service account "
                    "email as Editor, then try again."
                )
        return

    st.warning("Still Local DB — Secrets are missing or invalid. Follow step 2.")

    st.subheader("2) Paste your JSON here — app will build Secrets for you")
    st.caption(
        "Open the downloaded .json in Notepad → Ctrl+A → Ctrl+C → paste below."
    )
    json_text = st.text_area("Service account JSON", height=220, key="sa_json_paste")
    if st.button("Build Secrets text", type="primary") and json_text.strip():
        try:
            toml_text = build_simple_secrets_toml(
                "17R3l-l01CxE8h6psQ9087W2WO-OLKSBZ-uzljM2es7E",
                json_text,
            )
            st.session_state["generated_secrets_toml"] = toml_text
            st.success("Built. Copy the box below into Streamlit Secrets.")
        except Exception as e:
            st.error(f"Could not read that JSON: {e}")

    if st.session_state.get("generated_secrets_toml"):
        st.subheader("3) Copy this into Streamlit Secrets")
        st.markdown(
            """
1. Bottom-right **Manage app** → **Settings** → **Secrets**  
2. Delete everything in the Secrets box  
3. Copy **all** of the text below → paste into Secrets  
4. Click **Save changes** (must NOT say Invalid TOML)  
5. **Manage app → Reboot app**  
6. Refresh — sidebar should say **Cloud DB on**
"""
        )
        st.code(st.session_state["generated_secrets_toml"], language="toml")


def page_help():
    st.title("Help")
    st.markdown(
        """
### Shipper funnel
1. Keep broker boards for cash while direct accounts ramp (30–90 days).  
2. **Find Leads** by state/zip → add logistics email → Save.  
3. **Pipeline** → Activate → Start (emails on days 0 / 4 / 9 / 16).  
4. **Inbox Bot** for replies; you close rates and loads.  
5. **Leads List** is your memory — color = stage; red = never contact again.

### Carrier funnel (lease-on under LogixTrek MC)
1. **Find Carriers** — import PDF/Excel/CSV, or pull FMCSA demo / QCMobile MC lookups.  
2. Add emails → **Carrier Pipeline** → Activate → Start (same 0 / 4 / 9 / 16 cadence).  
3. Pitch: owner-operator under our MC with path toward ~$40k gross.  
4. **Carrier Inbox** for replies; mark **Hired** when they lease on.  
5. Data lives in Google Sheet tab `carrier_leads` (separate from shippers).

### Email templates
- **Shipper** and **Carrier** templates: **Org Setup → Email templates (Shipper + Carrier)**  
- Also previewed inside each funnel’s Pipeline page.

Email opens the door. **Phone within 2 hours** of a positive reply closes the account / lease-on.
"""
    )


def main():
    user = _require_auth()
    if not user:
        return

    pages_available = allowed_pages(user)
    if not pages_available:
        st.error("No modules enabled for your account. Ask Super Admin.")
        return

    shipper_pages = [
        p
        for p in ("Find Leads", "Leads List", "Pipeline & Outreach", "Inbox Bot")
        if p in pages_available
    ]
    carrier_pages = [
        p
        for p in ("Find Carriers", "Carrier Leads", "Carrier Pipeline", "Carrier Inbox")
        if p in pages_available
    ]
    top_pages = [
        p for p in ("Dashboard", "Org Setup", "Cloud Hosting", "Help") if p in pages_available
    ]

    if st.session_state.get("nav_page") not in pages_available:
        st.session_state.nav_page = pages_available[0]

    # Keep group open when browsing a funnel page
    cur = st.session_state.nav_page
    if cur in shipper_pages:
        st.session_state.nav_group = "shipper"
    elif cur in carrier_pages:
        st.session_state.nav_group = "carrier"

    def _goto(page: str, group: str | None = None):
        st.session_state.nav_page = page
        if group is not None:
            st.session_state.nav_group = group
        st.rerun()

    with st.sidebar:
        st.markdown("### LogixTrek Outreach")
        st.caption("v2026.09.08e · Shipper/Carrier templates + statewide pull")

        # Top-level: Dashboard first
        if "Dashboard" in top_pages:
            sel = cur == "Dashboard"
            if st.button(
                f"{'▾' if sel else '›'}  Dashboard",
                key="nav_Dashboard",
                type="primary" if sel else "secondary",
                use_container_width=True,
            ):
                _goto("Dashboard", group="")

        # Shipper group
        if shipper_pages:
            ship_open = st.session_state.get("nav_group") == "shipper"
            ship_active = cur in shipper_pages
            if st.button(
                f"{'▾' if ship_open else '›'}  Shipper",
                key="nav_group_shipper",
                type="primary" if ship_active else "secondary",
                use_container_width=True,
            ):
                # Toggle open; land on first shipper page
                if ship_open and ship_active:
                    st.session_state.nav_group = ""
                    st.rerun()
                else:
                    _goto(shipper_pages[0], group="shipper")
            if ship_open:
                for label in shipper_pages:
                    selected = cur == label
                    short = {
                        "Find Leads": "Find Leads",
                        "Leads List": "Leads List",
                        "Pipeline & Outreach": "Pipeline",
                        "Inbox Bot": "Inbox Bot",
                    }.get(label, label)
                    if st.button(
                        f"{'●' if selected else '○'}  {short}",
                        key=f"nav_{label}",
                        type="primary" if selected else "secondary",
                        use_container_width=True,
                    ):
                        _goto(label, group="shipper")

        # Carrier group
        if carrier_pages:
            car_open = st.session_state.get("nav_group") == "carrier"
            car_active = cur in carrier_pages
            if st.button(
                f"{'▾' if car_open else '›'}  Carrier",
                key="nav_group_carrier",
                type="primary" if car_active else "secondary",
                use_container_width=True,
            ):
                if car_open and car_active:
                    st.session_state.nav_group = ""
                    st.rerun()
                else:
                    _goto(carrier_pages[0], group="carrier")
            if car_open:
                for label in carrier_pages:
                    selected = cur == label
                    short = {
                        "Find Carriers": "Find Carriers",
                        "Carrier Leads": "Carrier Leads",
                        "Carrier Pipeline": "Pipeline",
                        "Carrier Inbox": "Inbox",
                    }.get(label, label)
                    if st.button(
                        f"{'●' if selected else '○'}  {short}",
                        key=f"nav_{label}",
                        type="primary" if selected else "secondary",
                        use_container_width=True,
                    ):
                        _goto(label, group="carrier")

        # Remaining top-level pages
        for label in ("Org Setup", "Cloud Hosting", "Help"):
            if label not in top_pages:
                continue
            sel = cur == label
            if st.button(
                f"{'▾' if sel else '›'}  {label}",
                key=f"nav_{label}",
                type="primary" if sel else "secondary",
                use_container_width=True,
            ):
                _goto(label, group="")

        company = _company()
        st.divider()
        st.caption(f"{user.get('name')} · {ROLE_PRESETS.get(user.get('role'), {}).get('label', user.get('role'))}")
        st.caption(company.get("my_company", ""))
        st.caption(company.get("my_mc", ""))
        if using_cloud():
            st.success("Cloud DB on")
        else:
            st.warning("Local DB")
        if company.get("send_live_emails"):
            st.error("LIVE EMAIL")
        else:
            st.success("Dry run")
        if st.button("Sign out", use_container_width=True):
            st.session_state.pop("auth_user", None)
            st.rerun()

    page = st.session_state.nav_page
    pages = {
        "Dashboard": page_dashboard,
        "Leads List": page_leads_list,
        "Find Leads": page_find_leads,
        "Pipeline & Outreach": page_pipeline,
        "Inbox Bot": page_inbox,
        "Carrier Leads": page_carrier_leads,
        "Find Carriers": page_find_carriers,
        "Carrier Pipeline": page_carrier_pipeline,
        "Carrier Inbox": page_carrier_inbox,
        "Org Setup": page_org_setup,
        "Cloud Hosting": page_cloud,
        "Help": page_help,
    }
    pages[page]()


if __name__ == "__main__":
    main()
