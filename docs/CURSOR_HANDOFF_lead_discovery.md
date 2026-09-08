# Lead Discovery — wired into Find & Vet (from Claude handoff + Cursor)

## What the app does now
1. **Google Places** — automated by state/zip
2. **Google Programmable Search + site read** — automated (needs CSE key + cx)
3. **Gemini LLM** — fit score 0–100 + reason
4. **USDA PACA** — manual 2-min search → CSV import (robots.txt blocks bots)
   Live tool: https://apps.mrp.usda.gov/public_search

## Secrets to add (keep your existing gcp_sa_b64 / sheet id)
```
google_places_api_key = "..."
gemini_api_key = "..."
google_cse_api_key = "..."
google_cse_id = "..."
```

## Get keys
| Key | Where |
|-----|--------|
| Places | Google Cloud → enable Places API (New) |
| Gemini | https://aistudio.google.com/apikey |
| CSE | https://programmablesearchengine.google.com/ + Cloud Custom Search API |

## Not scraped
LinkedIn, ThomasNet, Yellow Pages, PACA live search automation.
