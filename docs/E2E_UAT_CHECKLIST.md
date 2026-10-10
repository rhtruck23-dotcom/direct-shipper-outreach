# End-to-End UAT Checklist (LIVE Cloud)

| Field | Value |
|--------|--------|
| **App URL** | https://direct-shipper-outreach-ccrnu6jzt5dwjua7srdhha.streamlit.app/ |
| **Caption to confirm** | **v2026.10.08e · Notes drag** (sidebar under “LogixTrek Outreach”) |
| **Stable tag** | `esign-react-stable-08c` → commit `8468795` (pre-cleanup working baseline) |
| **Cleanup commit** | (origin/main after 08d push — see git log) |
| **Local automated (this pass)** | pytest esign+rbac+carrier+project_x: **79 passed**; pdf-field-editor vitest: **11 passed**; Playwright e2e: **1 passed** |
| **First pass** | Prefer LIVE OFF / Autopilot OFF until smoke is green; enable LIVE only for real send UAT |

### Status legend

| Mark | Meaning |
|------|---------|
| **AUTOMATED** | Covered by local pytest / Playwright in this pass |
| **MANUAL** | Requires Cloud login, secrets, or human browser (not automated here) |

---

### 0) Deploy gate (30 sec) — MANUAL (Cloud login)

1. Open the Cloud URL → sign in (Super Admin PIN or team login).
2. Sidebar caption must read exactly: **v2026.10.08e · Notes drag**.
3. If caption is older, wait for Streamlit Cloud rebuild (push already on `main`) or reboot the app in the Cloud dashboard.
4. Notes FAB → purple **📓 OneNote** title bar: hover shows grab cursor; drag moves window; position persists across reruns. Save / Save & close still work.
5. Esign Docs → Compose: **React PDF Field Editor only** (Upload / Text / Date / Sign / Typewriter / Redact / Save). Must NOT show Streamlit “Place field” / “Place X%” / Preview Prev/Next. Empty viewer shows **Upload a PDF**. Below editor: **Save & send** (Recipient + Save as template + Save & email) and **Print / review PDF**.

| Check | Result |
|-------|--------|
| Caption 08e on Cloud | **MANUAL** — requires Cloud login after deploy |
| Notes drag handle + persist | **AUTOMATED** source guards · **MANUAL** Cloud drag smoke |
| React Compose present / no Place UI | **AUTOMATED** — `tests/test_esign.py` source + AppTest guards |

---

### 1) Shipper

| Step | Result |
|------|--------|
| Sidebar → Shipper → Find / Leads List loads | **AUTOMATED** (rbac / CRM smoke paths) · **MANUAL** full UI on Cloud |
| Open lead detail → Pipeline / notes / one-off email UI | **MANUAL** (Cloud login) |
| Optional dry-run send | **MANUAL** (needs SMTP / secrets for LIVE; dry-run local possible) |

**UAT status: PARTIAL** — local automated smoke PASS; Cloud interactive path MANUAL.

---

### 2) Carrier

| Step | Result |
|------|--------|
| Sidebar → Carrier → Find / Leads List | **AUTOMATED** — `tests/test_carrier_funnel.py` |
| Lease-on / sequence UI + filters | **MANUAL** (Cloud login) |
| Optional dry-run / LIVE one-off | **MANUAL** (secrets) |

**UAT status: PARTIAL** — local automated funnel tests PASS; Cloud interactive path MANUAL.

---

### 3) Lead for X

| Step | Result |
|------|--------|
| Project Setup / Find / Leads List | **AUTOMATED** — `tests/test_project_x.py` |
| Open/create project lead + pipeline | **MANUAL** (Cloud login) |
| Import / owner visibility | **MANUAL** (multi-user secrets) |

**UAT status: PARTIAL** — local automated project_x tests PASS; Cloud interactive path MANUAL.

---

### 4) PDF doc sign (Esign Docs Compose)

| Step | Result |
|------|--------|
| Compose embeds React PDF Field Editor only | **AUTOMATED** — `test_esign_compose_embeds_pdf_field_editor`, no Place strings |
| Place Text / Date / Sign / Typewriter / Redact | **AUTOMATED** — pdf-field-editor unit + e2e (if Playwright ran) · **MANUAL** Cloud visual |
| Save to Outreach → Save & send / Print | **AUTOMATED** — consume/save unit tests · **MANUAL** Cloud click path |
| Save as template / Save & email | **AUTOMATED** (unit/send helpers) · **MANUAL** for real SMTP |
| My documents multi-delete | **MANUAL** (Cloud) |
| Public `?esign=TOKEN` fill/sign/submit | **AUTOMATED** (esign complete_signing unit) · **MANUAL** Cloud + LIVE email |

**UAT status: PARTIAL** — local esign + editor tests PASS; Cloud login / LIVE email MANUAL.

---

### Blockers / secrets to watch

- **Streamlit Cloud Secrets**: SMTP App Password + `send_live_emails`, Google Sheet ID / `gcp_sa_b64`, Super Admin PIN (`docs/STREAMLIT_SECRETS.toml`).
- **LIVE email**: PDF attachments need Gmail pool or company SMTP App Password; OAuth-only paths may not attach.
- **IMAP reply poll**: default OFF; enable in Org Setup only if testing inbox discovery (read-only).
- **PDF editor**: Cloud embeds committed `src/pdf_field_editor/frontend/` — no external `PDF_FIELD_EDITOR_URL` required for this build.
- **Cloud login**: without PIN/credentials this agent cannot complete interactive Cloud UAT — treat Cloud steps as MANUAL-required for the user.

### Related

- Multi-Gmail pool: `docs/MULTI_GMAIL_UAT.md`
- Cloud hosting: `docs/CLOUD_HOSTING.md`
- Older detailed cases: `docs/UAT_TEST_CASES_v2026.09.30c.md` (caption lineage; use **08d** above as source of truth)
