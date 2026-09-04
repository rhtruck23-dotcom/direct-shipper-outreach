from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
COMPANY_FILE = CONFIG_DIR / "company.json"
COMPANY_DEFAULT = CONFIG_DIR / "company.default.json"
LEADS_CSV = DATA_DIR / "leads.csv"
STATE_JSON = DATA_DIR / "lead_state.json"
OUTBOUND_LOG = DATA_DIR / "outbound_log.json"
INBOX_JSON = DATA_DIR / "inbox.json"
ALERTS_JSON = DATA_DIR / "alerts.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
