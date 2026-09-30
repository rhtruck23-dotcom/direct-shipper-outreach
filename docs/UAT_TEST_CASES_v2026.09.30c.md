# UAT Test Cases — v2026.09.30c

Practical step-by-step for a **~30–45 min** first-pass UAT. Mark **Pass / Fail / Skip**. On Fail, note what you saw and save a screenshot as `T-XXX-fail.png` in `docs/uat_screenshots/`.

| Field | Fill in |
|--------|---------|
| **App URL** | https://direct-shipper-outreach-ccrnu6jzt5dwjua7srdhha.streamlit.app/ |
| **Version (sidebar caption)** | **v2026.09.30d · Gmail pool activate** |
| **Git commit (expected)** | `d8bf80e` |
| **Tester** | _______________________________ |
| **Date** | _______________ |
| **Safety (first pass)** | **Send LIVE emails = OFF** · **Autopilot = OFF** · IMAP poll OFF |

### Current nav (confirm once)

| Parent | Children |
|--------|----------|
| **Shipper** | Find Shippers · Leads List → horizontal **List \| Pipeline \| Inbox** (buttons, default List) |
| **Carrier** | Find Carriers · Leads List → same three buttons |
| **Lead for X** | Project Setup (includes Templates) · Find Leads · Leads List → same three buttons |
| **Settings** | Org Setup · Cloud Hosting · Help |

**Header cleanup (this build):** Leads List views have **no** under-title blurb and **no** cloud/local banner under the title. Sidebar still shows Cloud DB / Local DB + Dry run / LIVE EMAIL at the bottom.

**Notes voice lineage:** Mic fix shipped in **v2026.09.29b** (parent-realm Web Speech + Record; iframe `allow=microphone`). Current caption is **v2026.09.30d**; voice should still work.

---

## Part A — Automated (pytest covers — do not re-click for regression)

Run locally before / after deploy:

```text
py -3 -m pytest -q --cov=src --cov-config=.coveragerc
```

| Gate | Expected |
|------|----------|
| Pass count | **269 passed** (as of `d8bf80e` UAT prep) |
| Coverage | **≥ 90%** (observed **91.4%**) |

| Area | Covered by |
|------|------------|
| Bot intents (opt-out, escalate, positive, OOO, thanks, etc.) | `test_core`, `test_purpose_95`, `test_coverage_boost` |
| Agent tools, escalate→notify, high-priority task | `test_agent_autonomy`, `test_purpose_95` |
| Autonomy pass / DNC skip / rules fallback | `test_agent_autonomy` |
| Shared capacity + week-plan estimate | `test_purpose_95` |
| Campaign soft-stop (autopilot + LIVE) | `test_purpose_95` |
| Multi-Gmail pool pick / caps / dry-run | `test_mailboxes` |
| IMAP poll (mocked; flag default OFF) | `test_purpose_95` |
| Translate ES/EN | `test_translate` |
| Notes + floating chrome | `test_notes`, `test_floating_chrome` |
| Lead-for-X store / campaign / templates | `test_project_x` |
| Carrier funnel | `test_carrier_funnel` |
| LLM priority failover | `test_agent_autonomy` |
| CRM picklists / stages / schedule | various `test_*` |

**Human UAT:** skip re-testing these logic paths unless a Fail appears in the UI smoke below.

---

## Part B — Human-only (first pass · LIVE & Autopilot OFF)

Work top to bottom. The **★ Top 10** cases are the must-run set (~20–25 min). Remaining cases fill the rest of a 30–45 min session.

### ★ Top 10 must-run

| # | ID | Focus |
|---|-----|--------|
| 1 | H-01 | Login |
| 2 | H-02 | Version caption |
| 3 | H-03 | Nav shape + List\|Pipeline\|Inbox buttons |
| 4 | H-04 | No list header blurb / cloud banner |
| 5 | H-05 | Notes FAB + Save |
| 6 | H-06 | Notes voice / Record |
| 7 | H-07 | Dry-run Pipeline Start (Shipper) |
| 8 | H-08 | Inbox escalate paste (no live mail) |
| 9 | H-09 | DNC / sidebar Dry run + Autopilot OFF |
| 10 | H-10 | Sign out |

---

### H-01 ★ Login as Super Admin

**Steps:**
1. Open App URL.
2. Enter Super Admin work email + PIN → **Sign in**.

**Expected:** App opens. Sidebar shows name · Super Admin (or role label), company, MC#.

**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**

---

### H-02 ★ Confirm version caption

**Steps:**
1. Look under **LogixTrek Outreach** in the left sidebar.

**Expected:** Exact caption: `v2026.09.30d · Gmail pool activate`.

**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:** (paste exact text if different)

---

### H-03 ★ Nav shape + horizontal List \| Pipeline \| Inbox

**Steps:**
1. Expand **Shipper** → open **Find Shippers**, then **Leads List**.
2. On Leads List, click **List**, **Pipeline**, **Inbox** (three broad buttons — not faint underlines).
3. Expand **Carrier** → **Find Carriers**, **Leads List** → click the same three buttons.
4. Expand **Lead for X** → **Project Setup**, **Find Leads**, **Leads List** → same three buttons.
5. Confirm Pipeline / Inbox are **not** separate sidebar children.

**Expected:** Menu matches table above. Default tab is **List**. Selected button is clearly primary. Pages load without crash.

**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**

---

### H-04 ★ List header cleanup (no blurb / cloud banner)

**Steps:**
1. Open **Shipper → Leads List** (List tab).
2. Look directly under the page title.
3. Repeat for **Carrier → Leads List** and **Lead for X → Leads List**.

**Expected:** Title + content only — **no** under-title marketing blurb and **no** cloud/local banner under the title. (Sidebar bottom may still say Cloud DB on / Local DB.)

**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**

---

### H-05 ★ Notes FAB + Save

**Steps:**
1. Click bottom-right **📝** (or sidebar **📝 Add Note**).
2. Confirm three panes: Notebooks | sections + Pages | left-aligned canvas.
3. Type a short line → **Save**.
4. Close panel → reopen → confirm text stuck.
5. Switch Shipper → Carrier → Dashboard once; confirm no sticky Notes overlay / wrong page residue.

**Expected:** Left-aligned editor; toast/save success; content persists; page switches clean.

**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**

---

### H-06 ★ Notes voice + Record (lineage v2026.09.29b)

**Steps:**
1. Open Notes on a page (Chrome/Edge, HTTPS).
2. **🎤 Voice** → allow mic if prompted → speak → **⏹ Stop**.
3. Confirm transcript in body.
4. **⏺ Record** → speak → **⏹ Stop** → confirm audio player on page.
5. **Save** → reopen → player still works.

**Expected:** Dictation inserts text; recording embeds playable audio. Mic permission works on click (parent-realm fix from 09.29b).

**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**

---

### H-07 ★ Shipper Pipeline dry-run Start

**Precondition:** LIVE OFF (sidebar **Dry run**). At least one non-DNC shipper lead with email (create via Find → paste/manual if needed).

**Steps:**
1. **Shipper → Leads List → Pipeline**.
2. Select 1 lead → **Activate selected** (if not already active).
3. **Start — send due emails** (or equivalent Start control).

**Expected:** Processed as **dry-run** (previews OK). No real email. No crash.

**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**

---

### H-08 ★ Inbox Bot escalate (paste only)

**Steps:**
1. **Shipper → Leads List → Inbox**.
2. Select a lead with email.
3. Paste a rate/pricing/contract question → **Process with Logistics Bot**.

**Expected:** Escalates (owner notify and/or high-priority task). Bot does **not** invent rates. No live send required.

**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**

---

### H-09 ★ Safety strip: Dry run + Autopilot OFF + DNC skip

**Steps:**
1. Confirm sidebar shows **Dry run** (not LIVE EMAIL).
2. Dashboard → Agent: confirm **Autopilot** is **OFF** (leave OFF).
3. Mark a disposable test lead **Do Not Contact** (or use an existing DNC).
4. Optional: try Pipeline Start / Run agent — DNC must not be emailed.

**Expected:** Dry run + Autopilot OFF for first pass. DNC never emailed.

**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**

---

### H-10 ★ Sign out

**Steps:**
1. Sidebar → **Sign out**.

**Expected:** Returns to login. App content not usable until sign-in again.

**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**

---

## Part C — Human stretch (if time remains in 30–45 min)

### H-11 Dashboard capacity + campaign tiles

**Steps:**
1. Open **Dashboard**.
2. Confirm Today capacity (Capacity / Sent / Remaining).
3. Click **Shipper active** (or equivalent) → lands on **Leads List → Pipeline**.

**Expected:** Numbers show (even if zero). Tile navigates correctly.

**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**

---

### H-12 Find Shippers — paste → save

**Steps:**
1. **Shipper → Find Shippers** → Paste dump.
2. Paste 1–2 fake contacts with emails → Parse → Save.

**Expected:** Lead appears in **Leads List**.

**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**

---

### H-13 Carrier Leads List + Pipeline dry-run

**Steps:**
1. Ensure one carrier with email (Find Carriers paste/import or existing).
2. **Carrier → Leads List** (List) → open lead.
3. **Pipeline** → Activate → Start (LIVE OFF).

**Expected:** List loads without header blurb/banner. Dry-run OK.

**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**

---

### H-14 Lead for X — Project Setup + Templates + List tabs

**Steps:**
1. **Lead for X → Project Setup** — confirm project + **Templates** section on same page.
2. Open **Leads List** → click List / Pipeline / Inbox.
3. Confirm no under-title blurb/cloud banner.

**Expected:** Templates live on Project Setup (not a separate sidebar child). Tabs work.

**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**

---

### H-15 Org Setup — LIVE stays OFF; Gmail pool visible

**Steps:**
1. **Settings → Org Setup**.
2. Confirm **Send LIVE emails** OFF / dry-run.
3. Glance at **Gmail send pool** — caption mentions unlimited adds + Activate/Retract; soft max 200/day (3×200≈600 example).
4. Confirm Dashboard status strip / sidebar still Dry run.

**Expected:** LIVE remains OFF for first pass. Pool UI present for later live UAT (`docs/MULTI_GMAIL_UAT.md`).

**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**

---

### H-16 Inbox safe reply (positive) · optional

**Steps:**
1. Shipper Inbox → paste “Thanks, interested — call next week.” → Process.

**Expected:** Safe draft / positive intent; **no** unnecessary escalate for routine interest.

**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**

---

### H-17 Jump-top chrome · optional

**Steps:**
1. Scroll a long page → click **↑** if shown.

**Expected:** Scrolls to top.

**Result:** [ ] Pass  [ ] Fail  [ ] Skip  
**Comment:**

---

## Part D — Deferred (secrets / live mail — not first pass)

Keep **LIVE OFF** and **Autopilot OFF** until Part B–C are green.

| ID | When | Notes |
|----|------|--------|
| L-01 | Live Gmail App Passwords (2–3) in pool | See `docs/MULTI_GMAIL_UAT.md` |
| L-02 | Live test send to **yourself** only | Then turn LIVE OFF again |
| L-03 | Autopilot ON for a planned dry week | Prefer LIVE OFF first |
| L-04 | Live Places / Gemini Find & Vet | Needs API keys |
| L-05 | Live LLM template generate (Lead for X) | Needs key |
| L-06 | Cloud Sheet connection test | Streamlit Cloud secrets |
| L-07 | Enable `imap_poll_enabled` once | Only after App Passwords verified |

---

## Summary

| Count | Number |
|--------|--------|
| **Pass** | _____ |
| **Fail** | _____ |
| **Skip** | _____ |

### Priority fails

| Priority | Test ID | Problem | Screenshot |
|----------|---------|---------|------------|
| P1 | | | |
| P2 | | | |
| P3 | | | |

### Sign-off

| | |
|--|--|
| **Overall** | [ ] Ready for daily dry-run use &nbsp;&nbsp; [ ] Needs fixes before live email &nbsp;&nbsp; [ ] Blocked |
| **Tester / date** | _______________ |

**Long-form archive:** older expanded cases lived in `docs/E2E_UAT_CHECKLIST.md` (now points here).
