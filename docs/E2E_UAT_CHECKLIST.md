# End-to-End UAT Checklist (LIVE Cloud)

| Field | Value |
|--------|--------|
| **App URL** | https://direct-shipper-outreach-ccrnu6jzt5dwjua7srdhha.streamlit.app/ |
| **Caption to confirm** | **v2026.10.07j · Esign preview fix** (sidebar under “LogixTrek Outreach”) |
| **Commit** | `e2536a8` (origin/main) |
| **First pass** | Prefer LIVE OFF / Autopilot OFF until smoke is green; enable LIVE only for real send UAT |

### 0) Deploy gate (30 sec)

1. Open the Cloud URL → sign in (Super Admin PIN or team login).
2. Sidebar caption must read exactly: **v2026.10.07j · Esign preview fix**.
3. If caption is older, wait for Streamlit Cloud rebuild (push already on `main`) or reboot the app in the Cloud dashboard.
4. Esign Docs → Compose: empty viewer shows **Upload a PDF** (not a blank gray void). After Upload PDF, page canvas must show document content.

---

### 1) Shipper

1. Sidebar → **Shipper** → **Find** (or Leads List).
2. Find / filter a shipper lead (or open an existing one).
3. Open lead detail → confirm Pipeline / notes / one-off email UI loads.
4. Optional: dry-run send one outreach email; confirm toast shows dry-run (or LIVE if you enabled it).

### 2) Carrier

1. Sidebar → **Carrier** → **Find** / **Leads List**.
2. Open a carrier lead → confirm lease-on / sequence UI and list filters work.
3. Optional: dry-run or LIVE one-off / sequence step as needed for UAT.

### 3) Lead for X

1. Sidebar → **Lead for X** → **Project Setup** (templates) if needed, then **Find** / **Leads List**.
2. Open or create a project lead → confirm list + pipeline tabs load.
3. Optional: import / assign owner; confirm teammate visibility rules if testing multi-user.

### 4) PDF doc sign (Esign Docs Compose)

1. Sidebar → **Settings** → **Esign Docs** (Super Admin / Manager).
2. **Compose**: upload a PDF (or open a template).
3. In the React PDF Field Editor:
   - Place **Text / Date / Signature / Typewriter** fields as needed.
   - Use **Redact** (R): draw solid Black / White / Void / Redact covers.
4. **Save** (or Save to Outreach) → confirm fields + redactions persist on preview/download.
5. **Save & email** (or send fill link): recipient gets fillable PDF + `?esign=TOKEN` link (dry-run toast if LIVE off).
6. Open the public `?esign=TOKEN` page → fill/sign → submit → owner gets signed PDF when LIVE email is on.

---

### Blockers / secrets to watch

- **Streamlit Cloud Secrets**: SMTP App Password + `send_live_emails`, Google Sheet ID / `gcp_sa_b64`, Super Admin PIN (`docs/STREAMLIT_SECRETS.toml`).
- **LIVE email**: PDF attachments need Gmail pool or company SMTP App Password; OAuth-only paths may not attach.
- **IMAP reply poll**: default OFF; enable in Org Setup only if testing inbox discovery (read-only).
- **PDF editor**: Cloud embeds committed `src/pdf_field_editor/frontend/` — no external `PDF_FIELD_EDITOR_URL` required for this build.

### Related

- Multi-Gmail pool: `docs/MULTI_GMAIL_UAT.md`
- Cloud hosting: `docs/CLOUD_HOSTING.md`
- Older detailed cases: `docs/UAT_TEST_CASES_v2026.09.30c.md` (caption lineage; use **07j** above as source of truth)
