# Shipper 5-lead end-to-end screenplay (Cloud)

Follow this like a script on the live app. Exact UI labels match the current build.

| Field | Value |
|--------|--------|
| **App URL** | https://direct-shipper-outreach-ccrnu6jzt5dwjua7srdhha.streamlit.app/ |
| **Caption (sidebar)** | **v2026.10.08e · Notes drag** (under “LogixTrek Outreach”) |
| **Goal** | 5 shipper leads → outreach → **Converted** → agreement signed via Esign |

**What “convert” means in this app:** sequence stage / CRM win — not a separate “Convert” wizard. Click **Mark Converted ✅** (List) or **Mark selected Converted** (Pipeline). That sets Stage to **Converted ★**, sets CRM status / Sales stage to **Converted**, stops the email sequence, and records a convert outcome. Then you send the agreement for signature.

---

## Nav map (use these labels)

| Where | How to open |
|--------|-------------|
| Top group | Sidebar **▸ Shipper** |
| Find | **○ Find Shippers** |
| Hub | **○ Leads List** → horizontal buttons **List** \| **Pipeline** \| **Inbox** |
| Settings | Sidebar **▸ Settings** → **○ Esign Docs** / **○ Org Setup** / **○ Help** |
| Caption / LIVE | Sidebar under brand: caption, **Dry run** (green) or **LIVE EMAIL** (red), **Cloud DB on** |

Titles inside pages: **Find Shippers**, **Leads List**, **Pipeline & Outreach**, **Inbox Bot**, **Esign Docs**.

---

## Preconditions (do before Phase A)

1. Open the Cloud URL → sign in (Super Admin PIN or team login).
2. Sidebar caption must read: **v2026.10.08e · Notes drag**. If older → wait for rebuild or **Manage app → Reboot app**, then refresh.
3. Confirm **Cloud DB on** (green). If **Local DB**, fix Secrets / reboot first (`docs/CLOUD_HOSTING.md`).
4. **LIVE email gate (choose one mode for the whole run):**
   - **Safe rehearsal:** leave sidebar **Dry run** (green). Pipeline / one-off / esign still “send” but do not SMTP. You will copy `?esign=` links from success toasts.
   - **Real email:** **Settings → Org Setup → Company & SMTP**:
     - Paste Gmail **App password** under **Email setup** → **Save & enable LIVE**, or
     - Add pool rows under **Gmail send pool** → **Add Gmail to pool** / **Add mailbox**, then **Activate in send pool** as needed.
     - Toggle **Send LIVE emails** ON in the Org form (or use **Save & enable LIVE**) → **Save**.
     - Sidebar must show red **LIVE EMAIL**.
     - Optional: **Send test email** before touching leads.
5. **Autopilot:** keep **Auto-pilot (due leads)** OFF until this 5-lead walkthrough is done (avoids surprise sends).
6. **IMAP:** leave **IMAP poll — discover lead replies from Gmail** OFF unless you intentionally test reply discovery.
7. Have a shipper agreement PDF ready on disk (blank or LogixTrek template).

### Secrets / Org gates checklist

| Gate | Where | Needed for |
|------|--------|------------|
| Super Admin PIN / team login | Streamlit Secrets | Sign-in |
| Google Sheet / cloud DB | Secrets + **Cloud Hosting** | Persist leads |
| `smtp_password` or Gmail pool App Password | **Org Setup → Email setup** / **Gmail send pool** | LIVE send + PDF attachments |
| **Send LIVE emails** | Org form toggle or **Save & enable LIVE** | Real SMTP (else dry-run) |
| Optional Google Places / CSE | Org Setup | Find & Vet / email agent (not required if you paste emails) |

---

## Phase A — Import or add 5 shipper leads

Open **Shipper → Find Shippers**. Pick **one** path below (or mix until you have 5 with emails).

### Path A1 — CSV import (fast when you have a file)

1. Tab **Import CSV**.
2. Sub-tab **CSV file**.
3. Upload CSV → **Import CSV**.
4. Preferred columns: `company_name`, `contact_name`, `email`, `phone`, `state`, `zip`, `freight_type` (aliases like `company` / `contact` also work).
5. Success toast: **Imported — N new, M updated.**
6. Go to **Shipper → Leads List** (horizontal **List**). Confirm 5 rows with Email filled.

### Path A2 — Add one lead × 5 (manual)

1. Tab **Add one lead**.
2. Fill **Company\***, **Email\*** (required); optional Contact, Phone, State, Zip, Freight, Lane, Remarks.
3. Submit **Add** → toast **Added.**
4. Repeat until 5 leads exist. Open **Leads List** to verify.

### Path A3 — Paste dump (good for LinkedIn / Excel paste)

1. Tab **Paste dump (easiest)**.
2. Set **Default state**, **Freight**, paste into **Paste dump** → **Parse paste**.
3. Filter (recommend **Only rows with email**), edit Email column if needed.
4. **Save to Leads List** or **Save + Activate pipeline** (activation can also wait for Phase C).

### Path A4 — Find & Vet (discovery; emails often blank)

1. Tab **Find & Vet (main)** → set State → **Find & Vet shippers** (or **Demo Find & Vet**).
2. Check **Select** on rows you want; type Email where **NEEDS EMAIL**.
3. **Save selected vetted leads** or **Save + Activate pipeline**.

**Exit criteria:** **Leads List → List** shows **5 leads** you will use, each with a non-empty **Email**. Caption under the table shows missing-email count — aim for **0 missing email** on your five.

---

## Phase B — Enrich / confirm emails

1. Stay on **Shipper → Leads List → List**.
2. For each of the 5: **Select lead** dropdown → confirm Email in the table / CRM.
3. If blanks remain and you want the agent:
   - Expander **Email enrichment agent (public web)** → **Run email agent on missing emails**.
   - Or edit email on the lead after re-import / manual Add.
4. Optional CRM hygiene (per lead):
   - **CRM fields** → set **CRM status** (e.g. Working), **Sales stage**, **Priority** → **Save CRM fields**.
   - **Append note** that this lead is part of the 5-lead E2E run.

**Exit criteria:** all 5 have real emails you can send to (or a mailbox you control for self-test).

---

## Phase C — Pipeline cadence / convert

### C1 — Activate + start sequence

1. **Leads List** → horizontal **Pipeline** (page title **Pipeline & Outreach**).
2. Optional: filter **State** so only your five show.
3. **Select all** (or check **Select** on the five).
4. **Activate selected** → toast **Activated N.**
5. **Start — send due emails**:
   - Dry-run: toast **Processed N (DRY RUN)** + expandable body preview.
   - LIVE: toast **Processed N (LIVE)** — check Gmail Sent / Spam.
6. Cadence is Emails **1–4** on days **0 / 4 / 9 / 16** (templates under **Settings → Org Setup → Email templates (Shipper + Carrier)**). For a same-day walkthrough you only need Email 1.

### C2 — Replies (optional same day)

1. Horizontal **Inbox** (title **Inbox Bot**), or **Dashboard → Check inbox for replies**.
2. Fallback: expander **Paste from Gmail…** → paste reply → **Process with Logistics Bot**.
3. On interest: on **List**, open lead → **Mark Responded 📞** (stops sequence) and/or keep working CRM.

### C3 — Mark Converted (required for this screenplay)

When the shipper agrees (or you are self-testing the win path):

**Option List:** **Select lead** → **Mark Converted ✅** → toast **Converted.** Stage column = **Converted ★** (green).

**Option Pipeline:** check **Select** → **Mark selected Converted** → toast **Marked Converted. Open Leads List to see the green stage.**

Optional: under **CRM fields**, set **CRM status** / **Sales stage** to **Converted** → **Save CRM fields** (List buttons already sync these).

**Exit criteria:** all 5 show Stage **Converted ★** (or you convert each right before sending their agreement in Phase E).

---

## Phase D — Prepare agreement PDF (Esign Compose)

Do this **once** so all five share one template.

1. Sidebar **Settings → Esign Docs**.
2. Tab **Compose**.
3. In the React **PDF Field Editor**:
   - **Upload** your agreement PDF.
   - Place fields: **Text** / **Date** / **Sign** (and **Typewriter** / **Redact** if needed).
   - For CRM auto-prefill, label fields: `company_name`, `contact_name`, `email`, `date`.
   - **Save to Outreach** (in the editor). Streamlit shows editor package ready / Saved to Outreach…
4. Below the editor — **Save & send**:
   - Set **Template / document name** (e.g. `Shipper Agreement`).
   - Optional: **Print / review PDF**.
   - Click **Save as template** → toast with template id.
5. Confirm under tab **My documents** that the template appears (status / title).

**Do not rely on** old Streamlit “Place field” / “Place X%” UI — it is gone. Compose is React editor only.

**Exit criteria:** at least one saved template visible when a lead CRM shows **Send for signature → Template** dropdown.

---

## Phase E — Send for signature (each of 5 leads)

For **each** lead slot (1–5):

1. **Shipper → Leads List → List**.
2. **Select lead** = that shipper.
3. Scroll to CRM section **#### Send for signature** (below **Send one-off email**).
4. **Template** = the Phase D template.
5. Confirm **To** (defaults to lead email); optional **Optional note**.
6. Caption shows **🟢 LIVE** or **🟡 dry-run (safe)**.
7. Click **Send for signature**.
8. Success: **Sent (live|dry_run). Fill link query: `?esign=TOKEN`** — copy the query string.
9. Recipient (or you, for self-test):
   - Open `https://direct-shipper-outreach-ccrnu6jzt5dwjua7srdhha.streamlit.app/?esign=TOKEN` (app URL + the query from the toast / email body).
   - Fill fields / draw or type signature → submit.
10. Alternate from Compose for a one-off (not per-lead template): **Save & email for signature** with **Recipient email** filled — still produces `?esign=` link.

**Exit criteria:** five outbound esign sends logged (lead **History** / conversation may show `outbound_esign`), and five fill links used or ready.

---

## Phase F — Confirm signed back in the app

1. **Settings → Esign Docs → My documents**.
2. Expand each doc for your five sends.
3. Status should move to **signed** after recipient submit.
4. Download **Download signed PDF** when present.
5. Optional: lead **History** on **List** still shows the outbound esign entry; notes can record “Agreement signed YYYY-MM-DD”.

**Exit criteria:** five documents **signed** with downloadable signed PDFs (LIVE notify email may also arrive to owner when SMTP is live).

---

## Checklist — 5 lead slots (paste when ready)

Fill these when you provide the five leads; then run Phases A–F against the rows.

| # | Company | Contact | Email | Phone | State | Freight | Source path (CSV / Add one / Paste / Vet) | Activated? | Converted ★? | Esign sent? | Signed? |
|---|---------|---------|-------|-------|-------|---------|---------------------------------------------|------------|--------------|-------------|--------|
| 1 | | | | | | | | ☐ | ☐ | ☐ | ☐ |
| 2 | | | | | | | | ☐ | ☐ | ☐ | ☐ |
| 3 | | | | | | | | ☐ | ☐ | ☐ | ☐ |
| 4 | | | | | | | | ☐ | ☐ | ☐ | ☐ |
| 5 | | | | | | | | ☐ | ☐ | ☐ | ☐ |

**Template name used:** _______________________  
**LIVE or Dry run:** _______________________  
**Date run:** _______________________

---

## Quick reference — exact buttons

| Step | Button / control |
|------|------------------|
| Import CSV | **Import CSV** |
| Manual add | **Add** |
| Activate | **Activate selected** or **Save + Activate pipeline** |
| Send sequence | **Start — send due emails** |
| Win | **Mark Converted ✅** / **Mark selected Converted** |
| Save CRM | **Save CRM fields** |
| Editor save | **Save to Outreach** |
| Template | **Save as template** |
| Compose email | **Save & email for signature** |
| Per-lead send | **Send for signature** |
| Enable SMTP | **Save & enable LIVE** / **Send LIVE emails** |

---

## Related docs

- Deploy / caption smoke: `docs/E2E_UAT_CHECKLIST.md`
- Multi-Gmail pool: `docs/MULTI_GMAIL_UAT.md`
- Cloud Secrets: `docs/CLOUD_HOSTING.md`
- In-app overview: sidebar **Settings → Help**
