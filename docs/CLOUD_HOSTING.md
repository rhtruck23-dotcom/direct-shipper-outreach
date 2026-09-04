# Free web hosting — Streamlit Community Cloud + Google Sheets

You do **not** need Python on your PC. The app runs on the internet.

## Cost: \$0
| Piece | What it does |
|--------|----------------|
| Streamlit Community Cloud | Hosts the clickable website |
| Google Sheet | Permanent memory of every lead / email / Do Not Contact |
| GitHub | Free code storage Streamlit reads from |

## Steps

### 1. Google Sheet (your lead memory)
1. New Google Sheet named **LogixTrek Leads**
2. Google Cloud Console → new project → enable **Google Sheets API** and **Drive API**
3. Create a **Service Account** → Download JSON key
4. Share the Sheet with the service account email as **Editor**
5. Copy Sheet ID from the browser URL

### 2. Put code on GitHub
- Create a free GitHub account if needed
- Upload / push the `direct-shipper-outreach` folder as a repo
- (Ask Cursor to push it for you if you prefer)

### 3. Deploy the website
1. Open https://share.streamlit.io
2. Sign in with GitHub → **New app**
3. Repository = your repo · Branch = `main` · Main file = `app.py`
4. Click **Deploy**
5. **Settings → Secrets** → paste contents from `STREAMLIT_SECRETS.toml` (with your real Sheet ID + service account JSON fields + SMTP password)
6. Save → app restarts
7. Bookmark the URL (works on phone)

### 4. Daily use
1. Open the URL
2. Find Leads (state/zip) → add emails → save
3. Pipeline → Activate → Start
4. Leads List → see color stages + remarks
5. Inbox Bot when someone replies

Dry-run stays OFF for live email until you set `send_live_emails = true` in secrets.
