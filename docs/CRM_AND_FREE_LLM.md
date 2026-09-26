# CRM + free/local LLM (v2026.09.26c → autonomy in 26d)

## Honest scope

- **Ollama** = free local Llama (or Mistral) if you install [Ollama](https://ollama.com) on the machine running the app. Not magic cloud free forever.
- **Groq** = optional free-tier API key when set in secrets / Org Setup.
- **Gemini** = existing AI Studio key path.
- **Priority failover** = Org Setup Priority 1→2→3 (default gemini → groq → ollama → rules). See **`docs/AGENT_AUTONOMY.md`**.
- **Full RL is future.** We shipped **outcome learning** (feedback store of convert/DNC/reply patterns) + **RAG context pack v1** (scope + notes + recent conversation, concat/TF-IDF — no vector DB yet) + **agent autonomy** (CRM tools + due-lead runner).

## Enable Ollama (2 steps)

1. Install Ollama, then pull a model: `ollama pull llama3.2` (or `mistral`).
2. In **Org Setup → Company & SMTP**, set a Priority slot to `ollama` and the model name. Failover is Priority 1 → 2 → 3 → rules.

## Lead CRM

Open a lead under **Shipper → Leads List** or **Lead for X → Leads List** (Carrier Leads also has the panel):

- **Notes timeline** — append-only (does not wipe remarks)
- **One-off email** — subject/body via the shared emailer (live/dry-run)
- **Tasks** — title, due datetime, open/done, linked `lead_id` (`data/lead_tasks.json` + sheet tab `lead_tasks`)
- Picklists: CRM status, sales stage, priority, next contact

## Dashboard

Shows **Past due / Due today / Upcoming (7 days)** task cards with inline **Done**, optional sales-stage funnel counts, plus **Run agent now** / **Auto-pilot (due leads)**.
