# End-to-End UAT Checklist — LogixTrek Direct Shipper Outreach

Print this page (or fill digitally). Mark each case **Pass**, **Fail**, or **Skip**. On **Fail**, write a short **Comment** and save a screenshot.

| Field | Fill in |
|--------|---------|
| **App URL** | https://direct-shipper-outreach-ccrnu6jzt5dwjua7srdhha.streamlit.app/ |
| **Version to confirm** | **v2026.09.28b · Lean core** — caption under **LogixTrek Outreach** in the left sidebar |
| **Tester name** | _______________________________ |
| **Date** | _______________ |

---

## Cloud smoke — 15 key lines (do these first)

After deploy, confirm the sidebar caption shows **v2026.09.28b**. Then click through:

1. **Login** — Super Admin email + PIN → sidebar shows your name / role.
2. **Version** — caption reads `v2026.09.28b · Lean core`.
3. **Notes FAB** — click 📝 (bottom-right). Three panes: Notebooks | section tabs + Pages | left-aligned page canvas. Typing stays left (not centered).
4. **Notes edit + Save** — type in a page → **Save** → toast “OneNote saved”; reopen FAB and confirm text stuck. (Voice/mic is **removed** from UI.)
5. **Sidebar Add Note** — **📝 Add Note** opens the same panel.
6. **Jump-top** — scroll down a long page → ↑ appears → click scrolls to top.
7. **Page switch** — move Shipper → Carrier → Dashboard; main area should match the selected page (no previous-page residue / sticky Notes overlay).
8. **Dry-run send** — **Send LIVE emails** OFF. Pipeline / due send still “sends” as dry-run (no real mail).
9. **DNC** — mark a lead Do Not Contact → bot / agent / campaign skip it.
10. **Today capacity** — Dashboard shows Capacity / Sent / Remaining (soft cap ± Gmail pool).
11. **Multi-Gmail** — Org Setup → Gmail send pool: 2–3 App Passwords, caps 200 (see `docs/MULTI_GMAIL_UAT.md`). Live test only to yourself.
12. **Autopilot dry-run** — Autopilot ON, LIVE OFF → **Run agent now** once; read summary; no real mail. (Autopilot stays OFF by default.)
13. **Inbox Bot** — paste a rate/pricing reply → escalate creates **owner notify + high-priority task**. Paste OOO / thanks → no escalate spam.
14. **Spanish** — Pipeline preview **Convert to Spanish**; Inbox paste Spanish → **Convert to English**; edit before send.
15. **Sign out** — sidebar **Sign out** returns to login.

**Safety:** keep **Send LIVE emails** OFF until Multi-Gmail / live steps. IMAP poll stays **OFF** unless App Passwords verified (`imap_poll_enabled`).

---

## Automation status (v2026.09.28b)

Many cases below are **covered by automated pytest** (mocked SMTP / Places / LLM / IMAP). Mark them **Skip** for human UAT unless you want a live click-through. Keep the **Human-only** list short.

### Automated in CI / `pytest` (do not need live click for regression)
| Area | Covered by tests |
|------|------------------|
| Bot intents (opt-out, escalate, positive, referral, unclear, ooo, thanks, timing, covered, info) | `test_core`, `test_purpose_95`, `test_coverage_boost` |
| Agent tools + escalate→notify + high-priority task | `test_agent_autonomy`, `test_purpose_95` |
| Autonomy pass / DNC skip / rules fallback | `test_agent_autonomy` |
| Shared capacity + week-plan estimate | `test_purpose_95` |
| Campaign shared-cap soft-stop (autopilot+LIVE) | `test_purpose_95` |
| Multi-Gmail pool pick / caps / dry-run | `test_mailboxes` |
| IMAP poll (mocked, flag default OFF) | `test_purpose_95` |
| Translate ES/EN helpers | `test_translate` |
| Notes / floating chrome helpers | `test_notes`, `test_floating_chrome` |
| Lead-for-X store/campaign/templates | `test_project_x` |
| LLM priority failover | `test_agent_autonomy` |
| CRM picklists / stages / schedule | various `test_*` |

### Human-only (short list — secrets / live mail / UI click)
1. **T-002** Sign-in with real Super Admin PIN
2. **T-082 / T-090 / T-091** Confirm 2–3 real Gmail App Passwords in pool + live test send to yourself
3. **T-027** Flip Autopilot ON for a production week (keep LIVE intentional)
4. **T-031** Live Google Places / Gemini Find & Vet (needs API keys)
5. **T-071** Live LLM template generate for Lead-for-X (needs key)
6. **T-083** Cloud Sheet connection if deploying Streamlit Cloud
7. Optional: enable `imap_poll_enabled` only after App Passwords verified, then smoke-poll once
8. **T-122** Voice/mic — **removed from Notes UI** in lean build (Skip / N/A)

Everything else in this checklist is optional UI confirmation; failures should be rare if pytest is green.

---

## How to use

1. Work through the numbered cases in order when you can (some later cases need earlier setup).
2. For each case mark one result:
   - **Pass** — it worked as expected
   - **Fail** — something wrong, broken, confusing, or missing
   - **Skip** — you could not run it (no API key, no second Gmail, etc.) — say why in Comment
3. On **Fail**:
   - Write what you saw vs what you expected in **Comment**
   - Save a screenshot as `T-XXX-fail.png` (example: `T-012-fail.png`)
   - Put screenshots in folder: **`docs/uat_screenshots/`** (see that folder’s README)
4. When done, fill the **Summary** at the end and send this checklist + the fail screenshots back so we can fix.

**Safety tip:** Keep **Send LIVE emails** OFF (dry-run) until the Live email section. Live tests should only send to *your* email.

---

## A. Login / Super Admin PIN

### T-001 Open app and see login
**Precondition:** You have the App URL and a browser.
**Steps:**
1. Open the App URL.
2. Wait for the page to load.
**Expected:** You see **LogixTrek Outreach** login with Work email and PIN fields (or you are already signed in).
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-002 Sign in as Super Admin
**Precondition:** You know the Super Admin work email and PIN.
**Steps:**
1. Enter work email and PIN.
2. Click **Sign in**.
**Expected:** Login succeeds. Left sidebar shows your name / Super Admin and page list (Dashboard, Shipper, etc.). Wrong PIN shows an error and does not open the app.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-003 Confirm sidebar version caption
**Precondition:** Signed in.
**Steps:**
1. Look under **LogixTrek Outreach** in the left sidebar.
2. Read the small version / caption line.
**Expected:** Caption is visible. Note the exact text (should be **v2026.09.28b · Lean core** or the current build label). Write what you see in Comment.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:** (write exact caption here)  
**Screenshot:** (filename)

### T-004 Sign out
**Precondition:** Signed in.
**Steps:**
1. Scroll to bottom of sidebar.
2. Click **Sign out**.
**Expected:** You return to the login screen. Opening a page without signing in again is blocked.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

---

## B. Navigation (sidebar)

### T-010 Parent groups open and close
**Precondition:** Signed in as Super Admin.
**Steps:**
1. Click **Shipper** (parent) in the sidebar.
2. Click **Carrier**, then **Lead for X**, then **Settings**.
3. Click the open parent again to collapse if it allows.
**Expected:** Parent rows expand/collapse. Child pages appear under the open group. You can move between groups.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-011 Blue parent / orange child styling
**Precondition:** A nav group is open (e.g. Shipper).
**Steps:**
1. Look at parent buttons (Dashboard, Shipper, Carrier, Lead for X, Settings).
2. Look at child buttons under an open group (Find Leads, Pipeline, etc.).
**Expected:** Parents look **blue-ish**; child items look **orange-ish** / indented with a circle bullet. Selected page is clearly highlighted.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-012 All major pages reachable
**Precondition:** Super Admin signed in.
**Steps:**
1. Open each: Dashboard; Shipper → Find Leads, Leads List, Pipeline, Inbox Bot; Carrier → Find Carriers, Carrier Leads, Pipeline, Inbox; Lead for X → Project Setup, Templates, Find Leads, Leads List, Pipeline, Inbox; Settings → Org Setup, Cloud Hosting, Help.
**Expected:** Every page opens without a blank/error crash. Titles match the menu.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:** (list any page that failed)  
**Screenshot:** (filename)

### T-013 Sidebar status badges
**Precondition:** Signed in.
**Steps:**
1. Check sidebar bottom: company name, MC#, Cloud DB / Local DB, LIVE EMAIL or Dry run.
**Expected:** Badges match reality (e.g. Dry run when live is off; Cloud DB on when cloud is connected).
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

---

## C. Dashboard (live / ops only)

### T-020 Live ops metrics (emails + campaigns) · *partial auto*
**Precondition:** Signed in.
**Steps:**
1. Open **Dashboard**.
2. Confirm **Today capacity** (Capacity / Sent / Remaining) and resume messaging if exhausted.
3. Confirm **Emails** (Sent today / Due sequences / Failures today).
4. Confirm **Campaigns** tiles: Shipper active / Carrier active / Lead for X active.
5. Optional: click **Prepare 4000-lead week plan** and confirm an estimate appears.
**Expected:** Ops numbers show (even if zero). Capacity strip clear. No Email Setup form on Dashboard.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-021 Status strip → Settings
**Precondition:** Dashboard open.
**Steps:**
1. Find the compact status strip: **Live ON/OFF** and **Pool remaining today**.
2. Click either control.
**Expected:** Navigates to **Settings → Org Setup**. Email setup / Save & enable LIVE / Gmail pool forms are there (not on Dashboard).
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-022 Live toggle in Org Setup (not Dashboard)
**Precondition:** Settings → Org Setup.
**Steps:**
1. Find **Email setup** / **Save & enable LIVE** / **Send LIVE emails**.
2. Confirm current state (should start OFF / dry-run for safe testing).
**Expected:** Toggle is clear. Sidebar shows **Dry run** when off and **LIVE EMAIL** when on. Dashboard only shows Live ON/OFF strip.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-023 Gmail pool in Org Setup
**Precondition:** Settings → Org Setup → Company & SMTP (scroll to Gmail send pool).
**Steps:**
1. Find **Gmail send pool**.
2. Note mailboxes and Remaining today / sent vs cap (e.g. `0/200`).
3. Return to Dashboard and confirm the status strip shows the same remaining figure.
**Expected:** Pool management is only in Org Setup. Dashboard strip matches remaining capacity.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-024 Clickable campaign tiles
**Precondition:** Dashboard open.
**Steps:**
1. Click **Shipper active** tile → confirm Pipeline (or shipper funnel) opens.
2. Click **Carrier active** → Carrier Pipeline.
3. Click **Lead for X active** → X Pipeline.
**Expected:** Each tile navigates to the related funnel page without crash.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-025 Clickable task tiles + open lead
**Precondition:** Optional — create a CRM task in Leads List first (or skip if none).
**Steps:**
1. On Dashboard find **Tasks & events** tiles: Past due / Due today / Upcoming.
2. Click a tile (expands the matching list on mobile-friendly columns).
3. If a task row appears, click the task title/row (opens related lead).
4. Mark **Done** once.
**Expected:** Tiles expand lists. Clicking a row opens Shipper / Carrier / Lead for X leads list with that lead selected when possible. Done updates the task.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-026 Run agent now
**Precondition:** Prefer dry-run (LIVE off). At least one lead with email is helpful but not required.
**Steps:**
1. On Dashboard under **Agent**, click **Run agent now**.
2. Wait for success / summary message. Note escalations count if shown.
**Expected:** Agent runs without crashing. Summary appears (even if “nothing due”). DNC leads are not emailed.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-027 Autopilot toggle (compact)
**Precondition:** Dashboard Agent section.
**Steps:**
1. Turn **Autopilot** ON briefly.
2. Confirm it saves / stays on after refresh of the control.
3. Turn it **OFF** again when finished testing (recommended).
**Expected:** Toggle works. Leaving ON may process due leads — turn OFF if you do not want that. Detailed caps remain in Org Setup.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-028 Note reminders on Dashboard
**Precondition:** Create a note with a reminder (see Notes section T-120) or skip if none.
**Steps:**
1. On Dashboard find **Note reminders** tiles (Past due / Due today / Upcoming).
2. Click a reminder row → note opens in Notebooks & Notes panel.
3. Click **Done** on a reminder.
**Expected:** Reminder buckets show. Opening note works. Done clears it from open reminders.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-029 Involvement moved to Org Setup
**Precondition:** Super Admin.
**Steps:**
1. Confirm Dashboard does **not** show “Your involvement (target ≤5%)” as a primary panel.
2. Open **Settings → Org Setup** → expander **Your involvement target**.
**Expected:** Involvement % and human/app step breakdown are under Org Setup only.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

---

## D. Shipper — Find Leads

### T-030 Paste dump → parse → save
**Precondition:** Shipper → Find Leads. Have a short paste with company + email (fake test data OK).
**Steps:**
1. Open **Paste dump** (or similar) tab.
2. Paste 1–3 sample contacts with emails.
3. Click **Parse paste**.
4. Save into leads (Save / Save + Activate if shown).
**Expected:** Rows parse. You can save. Lead appears later in Leads List / Pipeline.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-031 Find & Vet (API keys)
**Precondition:** Google Places (and ideally Gemini) keys in Org Setup. Skip if no keys.
**Steps:**
1. Open Find & Vet / Places-style tab.
2. Enter a State (e.g. VA or IL).
3. Run search / vet if buttons are available.
**Expected:** Results return or a clear error if quota/key missing. No hard crash.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-032 Import CSV
**Precondition:** A small CSV with company_name / email columns (or known sample).
**Steps:**
1. Open Import tab → **CSV file**.
2. Upload CSV → **Import CSV**.
**Expected:** Rows import or clear validation messages. Leads show up in list.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-033 Import National Shipper PDF
**Precondition:** A shipper PDF if you have one. Skip if none.
**Steps:**
1. Import tab → **National Shipper PDF**.
2. Upload → **Parse PDF**.
3. Select a few rows → Save if offered.
**Expected:** Parse produces a table; save works for selected rows.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-034 Manual add lead
**Precondition:** Find Leads → Manual tab.
**Steps:**
1. Fill company, email, state (minimum).
2. Save / add lead.
**Expected:** Lead is created and visible in Leads List.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

---

## E. Shipper — Leads List (CRM)

### T-040 Open Leads List and color stages
**Precondition:** At least one shipper lead exists.
**Steps:**
1. Open **Shipper → Leads List**.
2. Scan stage colors / indicators.
**Expected:** List loads. Colors match Help legend (gray / blue / green / red DNC, etc.). Cloud or Local banner shows.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-041 Select lead and save CRM fields
**Precondition:** Leads List with edit access.
**Steps:**
1. Select a lead.
2. Change **CRM status**, **Sales stage**, and **Priority**.
3. Optionally set next contact date/time.
4. Click **Save CRM fields**.
**Expected:** Success message. Values stick after leaving and returning to the lead.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-042 Append note
**Precondition:** Lead selected in Leads List.
**Steps:**
1. Type a note in **Add note**.
2. Click **Append note**.
**Expected:** Note appears in notes timeline with timestamp / author.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-043 One-off email (prefer dry-run)
**Precondition:** Lead with email. LIVE preferably OFF.
**Steps:**
1. Enter subject and body under **Send one-off email**.
2. Click **Send one-off**.
**Expected:** Success with mode dry-run or LIVE. Does not break the page. Independent of the 4-step sequence.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-044 Create CRM task
**Precondition:** Lead selected.
**Steps:**
1. Enter task title and due date/time.
2. Click **Create task**.
3. Optionally open Dashboard and confirm it appears under CRM tasks.
**Expected:** Task created; can mark Done later.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

---

## F. Shipper — Pipeline & Inbox

### T-050 Pipeline activate selected
**Precondition:** Leads with emails; DNC not selected. LIVE preferably OFF.
**Steps:**
1. Open **Shipper → Pipeline**.
2. Filter by State if helpful.
3. Check **Select** on 1–2 leads (or Select all carefully).
4. Click **Activate selected**.
**Expected:** Success count. Active sequence shows true / next step appears. DNC cannot be forced into email.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-051 Start due emails — dry-run first
**Precondition:** Activated leads; **Send LIVE emails** OFF.
**Steps:**
1. Click **Start — send due emails**.
2. Read results (✓ and previews).
**Expected:** Processed as **DRY RUN**. Body preview available. No real email sent. Lead stage / contact updates in record.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-052 Note about live pipeline send
**Precondition:** Only after email pool is set up (see Live email section).
**Steps:**
1. When ready for live, turn LIVE ON, select a **test lead that is your own email**, Activate/Start once.
2. Confirm inbox receipt, then turn LIVE OFF if still testing.
**Expected:** Live send only when intentional. Comment with Pass/Fail/Skip for live pipeline.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-053 Inbox Bot — safe reply · *logic auto*
**Precondition:** A shipper lead with email.
**Steps:**
1. Open **Inbox Bot**.
2. Confirm **Paste from Gmail** expander + Open Gmail / mailto helpers.
3. Select the lead.
4. Paste a friendly reply (e.g. “Thanks, interested — call me next week.”).
5. Click **Process with Logistics Bot**.
6. Confirm an **Outbound reply draft** appears (edit + **Convert to Spanish** available).
7. Click **Send reply** (dry-run OK).
**Expected:** Intent shown (positive). Safe reply drafted — **no owner escalate** for routine positive. Sequence may stop. No crash.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-054 Inbox Bot — escalate (rate/contract) · *logic auto*
**Precondition:** Same as T-053.
**Steps:**
1. Paste a reply that asks for rates / contract / load details.
2. Process with bot.
**Expected:** Escalates — owner notified **and** high-priority Dashboard task created. Bot does not invent rates.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-055 Inbox Bot — STOP / DNC
**Precondition:** Use a disposable test lead (not a real customer you still want).
**Steps:**
1. Paste “Please remove me / STOP / do not contact.”
2. Process.
**Expected:** Lead moves toward Do Not Contact / sequence stops. Future emails blocked. Dashboard DNC count can increase.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

---

## G. Carrier funnel

### T-060 Find Carriers — paste or import
**Precondition:** Carrier → Find Carriers.
**Steps:**
1. Use Paste and/or CSV/PDF import and/or FMCSA pull (demo OK).
2. Save at least one carrier lead with an email (manual fill OK).
**Expected:** Carrier lead saved. Visible under Carrier Leads.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-061 Carrier Leads list + deal stage
**Precondition:** At least one carrier lead.
**Steps:**
1. Open **Carrier Leads**.
2. Select a lead.
3. If deal stage control exists, change it (e.g. Applied → Packet sent) and save / observe.
4. Optionally **Mark Hired**.
**Expected:** List and edit work. Deal stages show (Applied, Packet sent, Docs under review, Signed & onboarded, Not qualified). Hired marks converted under MC.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-062 Carrier Pipeline activate + dry-run Start
**Precondition:** Carrier with email; LIVE OFF.
**Steps:**
1. Open **Carrier Pipeline**.
2. Select lead(s) → **Activate** → **Start** (due emails).
**Expected:** Dry-run lease-on emails process (days 0/4/9/16 cadence). No crash.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-063 Carrier Inbox
**Precondition:** Carrier lead with email.
**Steps:**
1. Open **Carrier Inbox**.
2. Paste a reply → **Process with Carrier Bot**.
**Expected:** Bot handles opt-out / interest; escalates pay / lease terms to you.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

---

## H. Lead for X

### T-070 Project Setup + scope
**Precondition:** Lead for X → Project Setup.
**Steps:**
1. Create a project (name + type buyer/seller/other).
2. Paste a short **Project Scope**.
3. Save / Select so it becomes active.
**Expected:** Project listed and selectable as active. Scope saved.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-071 Templates generate from scope
**Precondition:** Active project with scope.
**Steps:**
1. Open **Lead for X → Templates**.
2. Click **Generate from Project Scope (LLM)** (or equivalent).
3. Preview emails 1–4.
**Expected:** Templates generate (LLM or rules fallback). Preview readable and on-scope.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-072 Find / import leads into project
**Precondition:** Active project.
**Steps:**
1. Open **X Find Leads**.
2. Paste dump or import CSV with emails.
3. Save into the active project.
**Expected:** Leads appear under X Leads List for that project.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-073 X Pipeline activate + dry-run Start
**Precondition:** X leads with emails; LIVE OFF.
**Steps:**
1. Open **X Pipeline**.
2. Select → Activate → Start due emails.
**Expected:** Dry-run sequence runs for the active project. Previews OK.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-074 X Inbox
**Precondition:** X lead with email; active project.
**Steps:**
1. Open **X Inbox**.
2. Paste a reply → process.
**Expected:** Bot uses project scope framing; safe vs escalate behavior is clear.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

---

## I. Settings

### T-080 Org Setup — company & SMTP
**Precondition:** Super Admin → Settings → Org Setup → Company & SMTP.
**Steps:**
1. Confirm company name, MC#, sender email, etc.
2. Change a harmless field (e.g. phone) → **Save**.
3. Reload page / revisit and confirm it stuck (session or cloud).
**Expected:** Form saves with success message. LIVE toggle and SMTP fields visible.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-081 LLM priority 1 / 2 / 3
**Precondition:** Org Setup → Company & SMTP.
**Steps:**
1. Find **LLM priority failover**.
2. Confirm Priority 1, 2, 3 provider + model fields.
3. Save (optional small change).
4. Confirm priorities save; agent still works with failover when keys missing.
**Expected:** Three priority slots save. App still works if a key is missing (falls through to next / rules).
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-082 Gmail send pool — add 2–3 mailboxes
**Precondition:** You have 2–3 Gmail App Passwords ready. Do **not** put real passwords in this checklist file.
**Steps:**
1. Open **Settings → Org Setup** → **Gmail send pool** (not on Dashboard).
2. Add mailbox 1 (email + App Password + daily cap e.g. 200) → Add.
3. Add mailbox 2 (and 3 if available).
4. Confirm each shows ON · pw✓ and `0/cap today` (or similar).
5. Open Dashboard and confirm **Pool remaining today** strip updates.
**Expected:** Pool lists all mailboxes. **Remaining today** ≈ sum of caps. Dashboard strip only — no pool edit forms on Dashboard.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:** (how many mailboxes added)  
**Screenshot:** (filename)

### T-083 Cloud Hosting page
**Precondition:** Settings → Cloud Hosting.
**Steps:**
1. Open the page.
2. Read status (secret keys / sheet / service account).
3. If Cloud DB on, optionally **Test Google Sheet connection**.
**Expected:** Status is understandable. Cloud success or clear Local DB instructions. No crash.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-084 Help page
**Precondition:** Settings → Help.
**Steps:**
1. Open Help.
2. Skim Shipper / Carrier / Lead for X steps.
**Expected:** Readable how-to matching the menus you used.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-085 Email templates preview (Org Setup)
**Precondition:** Org Setup → Email templates tab.
**Steps:**
1. Open Shipper templates 1–4 and Carrier templates 1–4.
**Expected:** Subjects/bodies preview for both funnels.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

---

## J. Live email & Gmail rotation

> Only with intentional LIVE. Prefer sending only to yourself.

### T-090 Test send (live)
**Precondition:** At least one pool mailbox or SMTP App Password; LIVE ON.
**Steps:**
1. Turn **Send LIVE emails** ON (Save if needed).
2. Send **test email** to yourself from the email setup card.
3. Check your inbox (and spam).
**Expected:** Success message; email arrives. Message may show **via** a pool address. Pool counter increases by 1.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-091 Multi-Gmail rotation (2+ mailboxes)
**Precondition:** Two or more enabled pool mailboxes; LIVE ON.
**Steps:**
1. Send test email twice (or more).
2. Note which mailbox is used each time (success text / pool counters).
**Expected:** Sends rotate across mailboxes (round-robin). Counters rise on different accounts.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-092 Daily cap behavior (note)
**Precondition:** Pool with known caps. Optional: temporarily set one mailbox cap to **1**.
**Steps:**
1. Exhaust one mailbox cap with a live test (or note current sent/cap).
2. Send again — should use another mailbox.
3. If all mailboxes at cap, next live send should fail with a clear pool-at-cap message (not a crash).
4. Restore caps to normal (e.g. 200).
**Expected:** Caps respected. Clear message when pool exhausted. Restore caps after test.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:** (write what happened)  
**Screenshot:** (filename)

### T-093 Dry-run does not burn pool caps
**Precondition:** Pool counters noted; then LIVE OFF.
**Steps:**
1. Turn LIVE OFF.
2. Run agent or Pipeline Start again.
3. Compare Remaining today / sent counts.
**Expected:** Dry-run does **not** increase live pool usage.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

---

## K. Agent autonomy & safety

### T-100 Run agent now (due leads)
**Precondition:** One non-DNC lead with email and due/active sequence if possible; prefer dry-run.
**Steps:**
1. Dashboard → **Run agent now**.
2. Open **Last agent pass** expander if shown.
**Expected:** Summary of what the agent did (or why it skipped). No hang forever.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-101 DNC safety — agent / pipeline skip
**Precondition:** A lead marked Do Not Contact (from T-055 or manually).
**Steps:**
1. Try to include that lead in Pipeline Start or Run agent.
2. Confirm it is not emailed.
**Expected:** DNC is never emailed. Warnings or skip messages may appear. DNC count on Dashboard still lists them.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

---

## L. RBAC (light)

### T-110 Create a teammate (if possible)
**Precondition:** Super Admin → Org Setup → **Team & Access (RBAC)**.
**Steps:**
1. Add teammate: Name, Email, Role (e.g. Nurturer/Rep), Temporary PIN.
2. Click **Create user**.
3. (Optional) Sign out, sign in as that user, confirm they only see assigned leads / limited modules.
4. Sign back in as Super Admin.
**Expected:** User created. Optional login as teammate shows restricted view. Org Setup stays Super Admin only.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:** (role created; what they could/couldn’t see)  
**Screenshot:** (filename)

### T-111 Assign a lead to teammate (optional)
**Precondition:** Teammate exists; Super Admin.
**Steps:**
1. In Team & Access, use assignment controls for shipper or carrier leads.
2. Assign one lead to the teammate.
3. If you can, log in as teammate and confirm only assigned leads show.
**Expected:** Assignment saves. Teammate cannot see unassigned / owner-pool leads.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

---

## M. Notes / floating Add Note

### T-120 Floating Add Note on every page
**Precondition:** Signed in.
**Steps:**
1. From Dashboard, click **📝 Add Note** in the sidebar (and/or the bottom-right 📝 FAB).
2. Navigate to Shipper → Leads List and confirm Add Note is still available.
3. Navigate to Carrier and Lead for X — confirm previous page content does not linger.
**Expected:** Add Note on every authenticated page. **📝** opens three panes (Notebooks | sections+Pages | canvas). Editor is **left-aligned**. No mic/voice buttons. No stuck “Loading…”.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-121 Create notebook + note with reminder
**Precondition:** OneNote panel open (📝 FAB).
**Steps:**
1. Click **+** on Notebooks → name e.g. “UAT”.
2. Click **+** on section tabs (or use General) → **+** on Pages → set title + body (left-aligned).
3. Set reminder datetime in the toolbar → **Save**.
4. Open Dashboard → **Note reminders** and confirm it appears in Due today / Upcoming.
**Expected:** Note persists (`data/onenote_*.json`; cloud sheet tabs when configured). Reminder shows on Dashboard.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-122 Voice note — REMOVED (lean build)
**Status:** Mic / upload / voice-to-text controls are **hidden** until reliable. Mark **Skip**.
**Result:** [ ] Pass  [ ] Fail  [x] Skip  
**Comment:** Removed from UI in v2026.09.28b  

### T-123 Open note from Dashboard reminder + mark done
**Precondition:** Reminder exists from T-121.
**Steps:**
1. Dashboard → click reminder row.
2. Confirm page title/body opens in OneNote panel (correct notebook/section selected).
3. Mark reminder **Done**.
4. Confirm it leaves the open reminder tiles.
**Expected:** Click opens note; Done clears from past/due/upcoming buckets.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-124 OneNote pages — notebook / section / page / highlight
**Precondition:** Floating 📝 OneNote panel open.
**Steps:**
1. **+** Notebooks → create a notebook; rename inline if needed.
2. **+** on section tabs → add a section (double-click tab to rename); **+** Pages → add a page.
3. Set title + body; use Bold / Italic / highlight / text color / bullets. Confirm left-align.
4. Set reminder; click **Save** (or Save & close).
5. Close and re-open 📝 — confirm hierarchy + body persist.
**Expected:** Three-pane editing works. Save persists to `data/onenote_*.json`. FAB + jump-top present. No voice controls.

---

## N. Spanish / English email convert

### T-130 Convert to Spanish — CRM one-off
**Precondition:** Open a lead CRM panel (Shipper or Lead for X Leads List) with email.
**Steps:**
1. Enter English subject + body under **Send one-off email**.
2. Click **Convert to Spanish**.
3. Confirm draft updates (editable); original visible in expander.
4. Optionally edit, then Send (dry-run OK) or discard.
**Expected:** Natural Spanish draft via LLM failover (or rules fallback). Merge fields / MC numbers preserved when present. No crash.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-131 Convert to Spanish — Pipeline preview
**Precondition:** Shipper, Carrier, or Lead-for-X **Pipeline** page.
**Steps:**
1. Open **Email 1–4 preview** expander.
2. On any step, click **Convert to Spanish**.
3. Confirm side-by-side original + editable translation appears.
**Expected:** Translation shows; MC/names preserved when in template. Works on all three funnels.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

### T-132 Convert to English — Inbox inbound
**Precondition:** Inbox Bot (Shipper, Carrier, or X).
**Steps:**
1. Paste a short Spanish reply (e.g. “Gracias, me interesa — llámeme la próxima semana.”).
2. Click **Convert to English**.
3. Confirm inbound text becomes English (original in expander).
4. Process → edit outbound draft → optional **Convert to Spanish** → Send reply.
**Expected:** Inbound English conversion + outbound Spanish convert both work; user can edit before send.
**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**  
**Screenshot:** (filename)

---

## Summary

| Count | Number |
|--------|--------|
| **Pass** | _____ |
| **Fail** | _____ |
| **Skip** | _____ |
| **Total run** (Pass+Fail+Skip) | _____ |

### Priority bugs (list Fail IDs first)

| Priority | Test ID | Short problem | Screenshot file |
|----------|---------|---------------|-----------------|
| P1 (blocks work) | | | |
| P1 | | | |
| P2 (wrong / confusing) | | | |
| P2 | | | |
| P3 (nice to fix) | | | |

### Notes for the team

_Write anything else here (browser, slow pages, “I didn’t understand X”):_

_______________________________________________________________________________

_______________________________________________________________________________

---

## Sign-off

| | |
|--|--|
| **Tester name** | _______________________________ |
| **Date finished** | _______________ |
| **Overall verdict** | [ ] Ready for daily use &nbsp;&nbsp; [ ] Needs fixes before live email &nbsp;&nbsp; [ ] Blocked |
| **Signature / initials** | _______________ |

**How to send fails back:** Email or chat this filled checklist (PDF/print photo OK) plus the files in `docs/uat_screenshots/` (or a zip). Name files like `T-012-fail.png` so we can match them to test IDs.
