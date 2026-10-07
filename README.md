# Direct Shipper Outreach — LogixTrek LLC

Free **web app** (Streamlit Community Cloud) — no Python on your PC needed for daily use.

## Use it on the internet
See **`docs/CLOUD_HOSTING.md`** — Streamlit Cloud (\$0) + Google Sheet permanent lead memory.

## What you get
- Search leads by state / zip (Google Places or CSV)
- 4-email sequence + logistics bot for replies
- **Leads List** with color-coded stages, contact indicator, remarks
- **Never re-bother**: Do Not Contact is permanent; contact history is kept even if you re-import

## Color stages
| Color | Meaning |
|--------|---------|
| Gray | Not started |
| Light→blue | Email 1–2 sent |
| Yellow | Email 3 |
| Purple | Email 4 done |
| Green | Responded |
| Dark green | Converted |
| Red | Do not contact |

## Local test (optional)
Only if you install Python: double-click `START_APP.bat`

### Local with PDF Field Editor (recommended for Esign)
PDF Field Editor is the same product — embedded in **Settings → Esign Docs → Compose**.

```powershell
# One shot: Streamlit :8501 + Vite :5173
powershell -ExecutionPolicy Bypass -File scripts\dev_with_pdf_editor.ps1
```

Or separately: `python -m streamlit run app.py` and `pnpm --dir pdf-field-editor dev`.

For Streamlit Cloud **one deploy** (no external URL): build and commit the embed assets:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_pdf_field_editor.ps1
```

That writes `src/pdf_field_editor/frontend/` which Streamlit serves via a custom component iframe.

Optional Cloud override: set secret `PDF_FIELD_EDITOR_URL` to a Vercel/Netlify URL of `pdf-field-editor/` (see `docs/CLOUD_HOSTING.md`).

## PDF Field Editor
React SPA source: [`pdf-field-editor/`](./pdf-field-editor/). In the web app it appears inside **Esign Docs**, not as a separate product.
