# Involvement metric (target ≤10%)

Computed by `src/involvement.py` and shown on the Dashboard.

## Typical 20-lead batch (keys configured)

| Who | Effort units | What |
|-----|--------------|------|
| **App** | 83 | Places search, Google Search+site read, email enrich, LLM vet, emails 1–4, safe bot replies, Cloud DNC memory |
| **You** | 7 | Click Find & Vet (1), skim shortlist (2), fill leftover emails (1), Activate/Start (1), close escalations (2) |

**Involvement = 7 / 90 ≈ 7.8%** (≤10% target)

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
