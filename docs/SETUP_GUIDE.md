# Setup guide (non-technical)

## 0. Install Python (required once)
This PC did not have Python yet when the app was built. Do this first:

1. Download **Python 3.12** from https://www.python.org/downloads/
2. Run the installer
3. **Check the box: "Add python.exe to PATH"**
4. Click Install
5. Close and reopen any open terminals

## 1. Start the app
1. Open folder: `C:\Users\abuba\Projects\direct-shipper-outreach`
2. Double-click **`START_APP.bat`**
3. Wait for the browser window (usually http://localhost:8501)

## 2. Org Setup (already pre-filled for LogixTrek LLC)
Confirm:
- MC-1590829 / DOT-4146389
- Phone (443) 891-8543
- Address Macomb, IL
- Email accounts@logixtrek.com

### To send real email (Gmail example)
1. Turn on 2-Step Verification on the Google account that owns the mailbox
2. Create an **App Password**
3. Paste it in Org Setup → SMTP password
4. Host `smtp.gmail.com`, port `587`
5. Only then flip **Send LIVE emails**

Until then, everything is **dry run** (safe previews).

### Google Places (optional)
1. Google Cloud Console → enable **Places API (New)**
2. Create an API key
3. Paste in Org Setup
4. Without a key: use **Demo search** or **Import CSV**

### SMS alerts (optional)
Copy `.env.example` to `.env` and fill Twilio + your cell. Otherwise you only get email/in-app alerts.

## 3. Daily workflow
1. Find Leads → search or import → add emails → Save
2. Pipeline → select → Activate → Start
3. When someone replies → Inbox Bot → paste reply → Process
4. When bot says ESCALATE → call them yourself and close the deal

## 4. Gemini AI Studio (optional)
See `docs/GEMINI_AI_STUDIO.md` for a prompt pack if you want to run pieces there too.
