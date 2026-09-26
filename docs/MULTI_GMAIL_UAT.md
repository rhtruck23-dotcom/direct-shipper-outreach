# Multi-Gmail send pool UAT (v2026.09.26e)

Click through this checklist after deploy. **Do not commit real App Passwords.**

## Goal

Send ~400+/day via multiple Gmail accounts (soft ~200/day each). Example accounts:
`heronmb3@gmail.com`, `rhtruck23@gmail.com` (+ more). With 3 × 200 ≈ 600/day pool capacity;
set **Autopilot daily target** to ~400 if you want a slower intentional pace.

| Leads | Pace | Calendar days |
|------:|-----:|--------------:|
| 4000 | ~500/day | ≈ 8 days |
| 4000 | ~600/day | ≈ 7 days |

## Safety (always)

- [ ] **Send LIVE emails** is intentional (Dashboard / Org Setup). Leave OFF for dry-run UAT.
- [ ] DNC / `do_not_contact` leads are never emailed (spot-check one DNC lead).
- [ ] Dry-run sends do **not** increment pool counters.

---

## 1) Add 3 Gmails to the pool

1. Open **Dashboard** or **Org Setup → Company & SMTP**.
2. Scroll to **Gmail send pool**.
3. For each account (App Password from Google Account → Security → 2-Step → App passwords):
   - Gmail address (e.g. `heronmb3@gmail.com`)
   - App password (16 characters — placeholder in docs only: `xxxx xxxx xxxx xxxx`)
   - Daily cap **200**
   - Click **Add mailbox**
4. Repeat for `rhtruck23@gmail.com` and a third Gmail.
5. Confirm each shows **ON · pw✓** and `0/200 today`.
6. Confirm **Remaining today** shows **600/600** (or 200 × N).

---

## 2) Enable LIVE + test send

1. Turn **Send LIVE emails** ON (Email setup card → **Save & enable LIVE**, or Org Setup toggle).
2. **Send test email** to yourself.
3. Confirm success message shows **via** one of the pool addresses.
4. Confirm that mailbox usage moved to **1/200**.
5. Send a second test — confirm rotation to another pool mailbox (round-robin).

---

## 3) Autopilot settings for ~4000 in 7–8 days

1. **Org Setup → Agent autonomy**:
   - Auto-pilot (due leads) → **ON** (or enable on Dashboard)
   - Daily email soft cap (agent) → e.g. **500** or **600**
   - Autopilot daily target → e.g. **400** if you want ~400/day even with 600 pool capacity; **0** to use soft cap only
   - Max leads per agent pass → raise as needed (e.g. 50–100)
2. Ensure leads have emails, are not DNC, and have due next-contact / active sequences.
3. Click **Run agent now** once; confirm emails go out and pool counters rise.
4. Leave Auto-pilot ON — agent rotates silently in the backend; when all mailboxes hit cap, sending stops until the next America/Chicago day.

---

## 4) Cap / exhaust behavior

1. Temporarily set one mailbox daily cap to **1**, send a live test until that account shows `1/1`.
2. Confirm further live sends use other mailboxes.
3. Temporarily cap all at **1** and exhaust them — next live send should fail with pool-at-cap message (not crash).
4. Restore caps to **200**.

---

## 5) Dry-run check

1. Turn **Send LIVE emails** OFF.
2. Run agent / campaign step.
3. Confirm outbound log shows `dry_run` and pool **Remaining today** did not change.

---

## Done when

- [ ] 3 Gmails in pool, cap 200 each, enabled
- [ ] Live test rotates and logs mailbox
- [ ] Autopilot ON + target/cap set for intended daily volume
- [ ] DNC never emailed; dry-run does not burn caps
