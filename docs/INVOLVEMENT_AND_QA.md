# Involvement metric (target ≤5%)

Computed by `src/involvement.py` and shown on the Dashboard.

## Typical 20-lead batch (keys configured)

| Who | Effort units | What |
|-----|--------------|------|
| **App** | 118 | Places, search, email enrich, LLM vet, emails 1–4, safe bot, DNC memory, agent autonomy |
| **You** | 6 | Click Find & Vet (1), skim shortlist (1), fill leftover emails (1), Activate/Start (1), close escalations (2) |

**Involvement = 6 / 124 ≈ 4.8%** (≤5% target)

## What “vetted pull from source” means in tests
- Unit/integration tests **mock** Google Places, CSE, Gemini, Sheets, SMTP
- They prove the pipeline wiring is correct without burning API quota
- **Live** pull still needs your Secrets keys (Places + Gemini + optional CSE)

## Run QA locally
```
python -m pip install -r requirements.txt pytest-cov
python -m pytest -q --cov=src --cov-config=.coveragerc
```
Gate: all tests pass + coverage ≥95% (`fail_under = 95` in `.coveragerc`).
