# Agent autonomy + LLM priority failover (v2026.09.26d)

## LLM Priority 1 / 2 / 3

Open **Org Setup → Company & SMTP**:

1. Set **Priority 1 / 2 / 3 provider** (default: `gemini` → `groq` → `ollama`).
2. Set the matching **model** for each slot (e.g. `gemini-2.0-flash`, `llama-3.1-8b-instant`, `llama3.2`).
3. Paste Gemini / Groq keys as needed. Ollama needs a local install (`ollama pull llama3.2`).
4. Click **Save**.

`complete()` / `generate()` try each slot in order and log which engine answered. If all fail, callers use **rules** (templates / bot heuristics) so email and replies never hard-fail.

## Run agent / Auto-pilot

On the **Dashboard**:

- **Run agent now** — one autonomy pass over due / past-due leads (and active sequences). Works even when Auto-pilot is off.
- **Auto-pilot (due leads)** — off by default. When on, the Dashboard runs a soft pass once per session. Configure max leads / daily email soft cap (default 50) in Org Setup.

Dry-run mode: agent still “sends” via the emailer (`mode=dry_run`). Live sends only when **Send LIVE emails** is on.

## What the agent does alone vs when it escalates

**Alone (no human):**
- Update CRM status / sales stage / priority / next contact
- Append notes, create tasks, schedule follow-ups
- Toggle active sequence (never for DNC)
- Send nurture / one-off emails within the daily soft cap (respects DNC + live/dry-run)

**Escalates to you (~5% involvement):**
- Rate, pricing, contract, insurance, legal, load-now / commit language
- Review Dashboard **CRM tasks** past-due / due-today cards
- Close deals the agent paused for you

## Safety

- Autopilot **defaults off** until you enable it
- Never emails `do_not_contact` / CRM DNC / converted
- Soft daily email cap (agent)
- Lead-for-X templates, compose, and inbox bots use the same LLM failover + DNC guards
