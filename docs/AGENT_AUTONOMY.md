# Agent autonomy + shared capacity (v2026.09.27a)

## LLM Priority 1 / 2 / 3

Open **Org Setup → Company & SMTP**:

1. Set **Priority 1 / 2 / 3 provider** (default: `gemini` → `groq` → `ollama`).
2. Set the matching **model** for each slot (e.g. `gemini-2.0-flash`, `llama-3.1-8b-instant`, `llama3.2`).
3. Paste Gemini / Groq keys as needed. Ollama needs a local install (`ollama pull llama3.2`).
4. Click **Save**.

`complete()` / `generate()` try each slot in order and log which engine answered. If all fail, callers use **rules** (templates / bot heuristics) so email and replies never hard-fail.

## Multi-Gmail send pool + shared caps

Add as many Gmail + App Password rows as you want under **Gmail send pool** (Org Setup) — no hard mailbox limit. Soft default / max **daily_cap = 200** per account for now. Typical starter: **3 × 200 ≈ 600/day** (example, not a hard pool max). Live sends round-robin across **activated** mailboxes; use **Retract** to pull one out of the pool without deleting. When all active accounts are at cap, sending soft-stops until the next America/Chicago day. Dry-runs do **not** count.

When **Autopilot** and **Send LIVE emails** are both ON:

- Campaign due-emails (Shipper / Carrier / Lead-for-X) and the autonomy pass **share** the same soft cap + pool remaining budget (`src/capacity.py`).
- Dashboard shows **Today capacity / Sent / Remaining** and a clear next-day resume message when exhausted.
- Optional **Prepare 4000-lead week plan** estimates days/weeks from current throughput.

- 3 accounts × 200 ≈ **600/day** pool capacity (illustrative)
- Optional **Autopilot daily target** (e.g. 400) so the agent stops earlier even if the pool still has room
- **4000 leads** @ ~500/day ≈ **8 days**; @ ~600/day ≈ **7 days**

See [MULTI_GMAIL_UAT.md](MULTI_GMAIL_UAT.md) for the click-through checklist. Never commit real App Passwords.

## Inbox without IMAP (default)

IMAP poll defaults **OFF** (`imap_poll_enabled = false`).

- **Inbox Bot** → expander **Paste from Gmail**: copy reply from Gmail → paste → Process.
- **mailto** deep-link + **Open Gmail inbox** for personal replies after escalations.
- Optional read-only IMAP poll (pool App Passwords) behind Org Setup toggle — enable only after passwords are confirmed. Unit-tested with mocks.

## Run agent / Auto-pilot

On the **Dashboard**:

- **Run agent now** — one autonomy pass over due / past-due leads (and active sequences). Works even when Auto-pilot is off.
- **Auto-pilot** — off by default. When on, the Dashboard runs a soft pass once per session. Configure max leads / daily email soft cap / autopilot daily target in Org Setup.

Dry-run mode: agent still “sends” via the emailer (`mode=dry_run`). Live sends only when **Send LIVE emails** is on.

## What the agent does alone vs when it escalates

**Alone (no human) — expanded safe intents:**
- Opt-out / STOP / DNC confirmation
- OOO / auto-reply (no outbound spam)
- Thanks-only, timing (“not now”), already-have-carrier, info requests
- Positive interest + referral redirect + unclear clarify (capability snapshot / clarifying question)
- Update CRM fields, notes, tasks, schedule follow-ups, nurture emails within caps

**Escalates to you (~5% involvement) — rate/contract/legal/load only:**
- `escalate_to_owner` **always** notifies the owner **and** creates a **high-priority** Dashboard task
- You close rates, contracts, insurance packets, and load commitments

## Safety

- Autopilot **defaults off** until you enable it
- Never emails `do_not_contact` / CRM DNC / converted
- Soft daily email cap (agent) + optional autopilot daily target + per-mailbox pool caps
- Shared caps when Autopilot + LIVE
- Lead-for-X templates, compose, and inbox bots use the same LLM failover + DNC guards
