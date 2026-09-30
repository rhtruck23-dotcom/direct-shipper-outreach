# End-to-End UAT Checklist

**Active test cases for this build:**  
→ **[`docs/UAT_TEST_CASES_v2026.09.30c.md`](UAT_TEST_CASES_v2026.09.30c.md)** (caption bumped to **v2026.09.30d**)

| Field | Value |
|--------|--------|
| **App URL** | https://direct-shipper-outreach-ccrnu6jzt5dwjua7srdhha.streamlit.app/ |
| **Version** | **v2026.09.30d · Gmail pool activate** (sidebar caption) |
| **Commit** | _(fill after push)_ |
| **First pass** | LIVE OFF · Autopilot OFF |

### What changed in this build (vs older checklist)

- Gmail send pool: **Activate in send pool** / **Retract**; unlimited mailboxes; soft max **daily_cap = 200**; 3×200≈600/day is an example only.
- Leads hubs use broad horizontal **List \| Pipeline \| Inbox** buttons (not faint radio underlines).
- Sidebar: Shipper = Find + Leads List; Carrier = Find + Leads List; Lead for X = Project Setup (templates) + Find + Leads List.
- **No** under-title blurb / cloud banner on Shipper, Carrier, or Lead-for-X list views.
- Notes mic parent-realm fix remains in lineage from **v2026.09.29b**.

### Automated gate

```text
py -3 -m pytest -q --cov=src --cov-config=.coveragerc
```

Expect **≥269 passed**, coverage **≥ 90%**.

### Related

- Multi-Gmail live pool: `docs/MULTI_GMAIL_UAT.md`
- Fail screenshots: `docs/uat_screenshots/`
