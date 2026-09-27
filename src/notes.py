"""
Global notebooks + optional sections + pages/notes (OneNote-like).

Hierarchy: Notebook → Section (optional) → Page

Local  -> data/notebooks.json + data/note_sections.json + data/notes.json
Cloud  -> Google Sheet worksheets "notebooks", "note_sections", "notes"
Audio blobs (voice) stay local under data/note_audio/ (Sheet stores path/meta only).

Pages store body as markdown/HTML string (highlights via <mark> / ==text==).
"""
from __future__ import annotations

import base64
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from .paths import DATA_DIR

NOTEBOOKS_JSON = DATA_DIR / "notebooks.json"
SECTIONS_JSON = DATA_DIR / "note_sections.json"
NOTES_JSON = DATA_DIR / "notes.json"
NOTE_AUDIO_DIR = DATA_DIR / "note_audio"

NOTEBOOK_COLUMNS = ["id", "name", "created_at", "updated_at"]
SECTION_COLUMNS = ["id", "notebook_id", "name", "created_at", "updated_at"]
NOTE_COLUMNS = [
    "id",
    "notebook_id",
    "section_id",
    "title",
    "body",
    "color",
    "reminder_at",
    "reminder_done",
    "audio_path",
    "audio_mime",
    "created_at",
    "updated_at",
    "created_by",
]

PAGE_COLORS = ("default", "yellow", "green", "pink", "blue")
HIGHLIGHT_STYLES = {
    "yellow": "#fff59d",
    "green": "#c8e6c9",
    "pink": "#f8bbd0",
    "blue": "#bbdefb",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_dt(value: str) -> Optional[datetime]:
    s = (value or "").strip()
    if not s:
        return None
    try:
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            return datetime.fromisoformat(s + "T00:00:00")
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None


def parse_reminder_date(value: str) -> Optional[date]:
    dt = _parse_dt(value)
    return dt.date() if dt else None


def _using_cloud() -> bool:
    try:
        from . import storage

        return storage.using_cloud()
    except Exception:
        return False


def _blank_notebook() -> dict[str, Any]:
    return {"id": "", "name": "", "created_at": "", "updated_at": ""}


def _blank_section() -> dict[str, Any]:
    return {
        "id": "",
        "notebook_id": "",
        "name": "",
        "created_at": "",
        "updated_at": "",
    }


def _blank_note() -> dict[str, Any]:
    return {
        "id": "",
        "notebook_id": "",
        "section_id": "",
        "title": "",
        "body": "",
        "color": "default",
        "reminder_at": "",
        "reminder_done": False,
        "audio_path": "",
        "audio_mime": "",
        "created_at": "",
        "updated_at": "",
        "created_by": "",
    }


def _normalize_notebook(raw: dict) -> dict[str, Any]:
    nb = _blank_notebook()
    for k in nb:
        if k in raw and raw[k] not in (None,):
            nb[k] = raw[k]
    nb["id"] = str(nb.get("id") or "").strip()
    nb["name"] = str(nb.get("name") or "").strip() or "Untitled"
    nb["created_at"] = str(nb.get("created_at") or "")
    nb["updated_at"] = str(nb.get("updated_at") or "")
    if not nb["id"]:
        nb["id"] = f"nb_{uuid.uuid4().hex[:10]}"
    return nb


def _normalize_section(raw: dict) -> dict[str, Any]:
    s = _blank_section()
    for k in s:
        if k in raw and raw[k] not in (None,):
            s[k] = raw[k]
    s["id"] = str(s.get("id") or "").strip()
    s["notebook_id"] = str(s.get("notebook_id") or "").strip()
    s["name"] = str(s.get("name") or "").strip() or "Untitled section"
    s["created_at"] = str(s.get("created_at") or "")
    s["updated_at"] = str(s.get("updated_at") or "")
    if not s["id"]:
        s["id"] = f"sec_{uuid.uuid4().hex[:10]}"
    return s


def _normalize_note(raw: dict) -> dict[str, Any]:
    n = _blank_note()
    for k in n:
        if k in raw and raw[k] not in (None,):
            n[k] = raw[k]
    n["id"] = str(n.get("id") or "").strip()
    n["notebook_id"] = str(n.get("notebook_id") or "").strip()
    n["section_id"] = str(n.get("section_id") or "").strip()
    n["title"] = str(n.get("title") or "").strip()
    n["body"] = str(n.get("body") or "")
    color = str(n.get("color") or "default").strip().lower() or "default"
    n["color"] = color if color in PAGE_COLORS else "default"
    n["reminder_at"] = str(n.get("reminder_at") or "").strip()
    n["reminder_done"] = str(n.get("reminder_done")).lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    n["audio_path"] = str(n.get("audio_path") or "").strip()
    n["audio_mime"] = str(n.get("audio_mime") or "").strip()
    n["created_at"] = str(n.get("created_at") or "")
    n["updated_at"] = str(n.get("updated_at") or "")
    n["created_by"] = str(n.get("created_by") or "").strip()
    if not n["id"]:
        n["id"] = f"note_{uuid.uuid4().hex[:10]}"
    return n


def wrap_highlight(text: str, color: str = "yellow") -> str:
    """Wrap text in a colored <mark> span (stored in page body HTML/markdown)."""
    hex_color = HIGHLIGHT_STYLES.get((color or "yellow").lower(), HIGHLIGHT_STYLES["yellow"])
    inner = (text or "").strip() or "highlighted"
    return f'<mark style="background:{hex_color}">{inner}</mark>'


def wrap_bold(text: str) -> str:
    inner = (text or "").strip() or "bold"
    return f"**{inner}**"


def wrap_color_span(text: str, color: str = "blue") -> str:
    text_colors = {
        "yellow": "#f9a825",
        "green": "#2e7d32",
        "pink": "#c2185b",
        "blue": "#1565c0",
    }
    tc = text_colors.get((color or "blue").lower(), "#1565c0")
    inner = (text or "").strip() or "colored"
    return f'<span style="color:{tc}">{inner}</span>'


def _load_json_list(path: Path) -> list[dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [x for x in data if isinstance(x, dict)]


def _save_json_list(path: Path, rows: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)


def _open_worksheet(title: str, columns: list[str], *, create_if_missing: bool = False):
    import gspread
    from . import storage

    sh = storage._open_spreadsheet()
    try:
        return sh.worksheet(title)
    except gspread.WorksheetNotFound:
        if not create_if_missing:
            raise
        ws = sh.add_worksheet(title=title, rows=1000, cols=max(len(columns), 12))
        ws.update("A1", [columns], value_input_option="USER_ENTERED")
        return ws


def _load_sheet_rows(title: str, columns: list[str], normalize) -> list[dict]:
    import gspread

    try:
        ws = _open_worksheet(title, columns, create_if_missing=False)
    except gspread.WorksheetNotFound:
        return []
    values = ws.get_all_values()
    if not values or len(values) < 2:
        return []
    header = [str(h).strip() for h in values[0]]
    out: list[dict] = []
    for row in values[1:]:
        raw = {
            header[i]: (row[i] if i < len(row) else "")
            for i in range(len(header))
            if header[i]
        }
        if raw.get("id") or raw.get("name") or raw.get("title"):
            out.append(normalize(raw))
    return out


def _save_sheet_rows(title: str, columns: list[str], rows: list[dict], normalize) -> None:
    ws = _open_worksheet(title, columns, create_if_missing=True)
    values = [columns]
    for raw in rows:
        row = normalize(raw)
        values.append(
            [
                str(
                    row.get(c, "")
                    if c != "reminder_done"
                    else ("true" if row.get("reminder_done") else "false")
                )
                for c in columns
            ]
        )
    ws.clear()
    ws.update("A1", values, value_input_option="USER_ENTERED")


def load_notebooks() -> list[dict]:
    if _using_cloud():
        try:
            rows = _load_sheet_rows("notebooks", NOTEBOOK_COLUMNS, _normalize_notebook)
            if rows:
                return rows
        except Exception:
            pass
    return [_normalize_notebook(x) for x in _load_json_list(NOTEBOOKS_JSON)]


def save_notebooks(notebooks: list[dict]) -> None:
    normalized = [_normalize_notebook(n) for n in notebooks]
    if _using_cloud():
        try:
            _save_sheet_rows("notebooks", NOTEBOOK_COLUMNS, normalized, _normalize_notebook)
            _save_json_list(NOTEBOOKS_JSON, normalized)  # local backup
            return
        except Exception:
            pass
    _save_json_list(NOTEBOOKS_JSON, normalized)


def load_sections() -> list[dict]:
    if _using_cloud():
        try:
            rows = _load_sheet_rows("note_sections", SECTION_COLUMNS, _normalize_section)
            if rows:
                return rows
        except Exception:
            pass
    return [_normalize_section(x) for x in _load_json_list(SECTIONS_JSON)]


def save_sections(sections: list[dict]) -> None:
    normalized = [_normalize_section(s) for s in sections]
    if _using_cloud():
        try:
            _save_sheet_rows(
                "note_sections", SECTION_COLUMNS, normalized, _normalize_section
            )
            _save_json_list(SECTIONS_JSON, normalized)
            return
        except Exception:
            pass
    _save_json_list(SECTIONS_JSON, normalized)


def load_notes() -> list[dict]:
    if _using_cloud():
        try:
            rows = _load_sheet_rows("notes", NOTE_COLUMNS, _normalize_note)
            if rows:
                return [_migrate_note_row(r) for r in rows]
        except Exception:
            pass
    return [_migrate_note_row(_normalize_note(x)) for x in _load_json_list(NOTES_JSON)]


def _migrate_note_row(note: dict) -> dict:
    """Ensure color / section_id exist on legacy notes (pre-OneNote schema)."""
    n = _normalize_note(note)
    if not n.get("color"):
        n["color"] = "default"
    if n.get("section_id") is None:
        n["section_id"] = ""
    return n


def save_notes(notes: list[dict]) -> None:
    normalized = [_migrate_note_row(n) for n in notes]
    if _using_cloud():
        try:
            _save_sheet_rows("notes", NOTE_COLUMNS, normalized, _normalize_note)
            _save_json_list(NOTES_JSON, normalized)
            return
        except Exception:
            pass
    _save_json_list(NOTES_JSON, normalized)


def ensure_default_notebook() -> dict:
    notebooks = load_notebooks()
    if notebooks:
        return notebooks[0]
    now = _utc_now()
    nb = _normalize_notebook(
        {"id": f"nb_{uuid.uuid4().hex[:10]}", "name": "General", "created_at": now, "updated_at": now}
    )
    save_notebooks([nb])
    return nb


def create_notebook(name: str) -> dict:
    notebooks = load_notebooks()
    now = _utc_now()
    nb = _normalize_notebook(
        {
            "id": f"nb_{uuid.uuid4().hex[:10]}",
            "name": (name or "").strip() or "Untitled",
            "created_at": now,
            "updated_at": now,
        }
    )
    notebooks.append(nb)
    save_notebooks(notebooks)
    return nb


def create_section(*, notebook_id: str, name: str = "") -> dict:
    sections = load_sections()
    now = _utc_now()
    sec = _normalize_section(
        {
            "id": f"sec_{uuid.uuid4().hex[:10]}",
            "notebook_id": notebook_id or ensure_default_notebook()["id"],
            "name": (name or "").strip() or "New section",
            "created_at": now,
            "updated_at": now,
        }
    )
    sections.append(sec)
    save_sections(sections)
    return sec


def pages_for_notebook(notebook_id: str, *, section_id: Optional[str] = None) -> list[dict]:
    nid = (notebook_id or "").strip()
    pages = [n for n in load_notes() if n.get("notebook_id") == nid]
    if section_id is not None:
        sid = (section_id or "").strip()
        if sid == "":
            pages = [p for p in pages if not (p.get("section_id") or "").strip()]
        else:
            pages = [p for p in pages if (p.get("section_id") or "") == sid]
    pages.sort(key=lambda n: n.get("updated_at") or "", reverse=True)
    return pages


def sections_for_notebook(notebook_id: str) -> list[dict]:
    nid = (notebook_id or "").strip()
    secs = [s for s in load_sections() if s.get("notebook_id") == nid]
    secs.sort(key=lambda s: s.get("name") or "")
    return secs


def create_note(
    *,
    notebook_id: str,
    title: str = "",
    body: str = "",
    reminder_at: str = "",
    created_by: str = "",
    audio_bytes: Optional[bytes] = None,
    audio_mime: str = "",
    color: str = "default",
    section_id: str = "",
) -> dict:
    ensure_default_notebook()
    notes = load_notes()
    now = _utc_now()
    note_id = f"note_{uuid.uuid4().hex[:10]}"
    audio_path = ""
    mime = (audio_mime or "").strip()
    if audio_bytes:
        NOTE_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        ext = ".webm"
        if "wav" in mime:
            ext = ".wav"
        elif "mpeg" in mime or "mp3" in mime:
            ext = ".mp3"
        elif "ogg" in mime:
            ext = ".ogg"
        elif "mp4" in mime or "m4a" in mime:
            ext = ".m4a"
        path = NOTE_AUDIO_DIR / f"{note_id}{ext}"
        path.write_bytes(audio_bytes)
        audio_path = str(path.relative_to(DATA_DIR)).replace("\\", "/")
    note = _normalize_note(
        {
            "id": note_id,
            "notebook_id": notebook_id or ensure_default_notebook()["id"],
            "section_id": (section_id or "").strip(),
            "title": (title or "").strip() or "Untitled page",
            "body": body or "",
            "color": color or "default",
            "reminder_at": (reminder_at or "").strip(),
            "reminder_done": False,
            "audio_path": audio_path,
            "audio_mime": mime,
            "created_at": now,
            "updated_at": now,
            "created_by": created_by or "",
        }
    )
    notes.append(note)
    save_notes(notes)
    return note


def update_note(note_id: str, **fields) -> Optional[dict]:
    notes = load_notes()
    out = None
    for i, n in enumerate(notes):
        if n.get("id") == note_id:
            updated = {**n, **fields, "updated_at": _utc_now()}
            notes[i] = _normalize_note(updated)
            out = notes[i]
            break
    if out is None:
        return None
    save_notes(notes)
    return out


def get_note(note_id: str) -> Optional[dict]:
    nid = (note_id or "").strip()
    for n in load_notes():
        if n.get("id") == nid:
            return n
    return None


def mark_reminder_done(note_id: str) -> Optional[dict]:
    return update_note(note_id, reminder_done=True)


def attach_audio_to_note(
    note_id: str,
    audio_bytes: bytes,
    *,
    audio_mime: str = "audio/webm",
) -> Optional[dict]:
    """Save/replace voice blob on an existing page."""
    if not audio_bytes:
        return get_note(note_id)
    note = get_note(note_id)
    if not note:
        return None
    NOTE_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    mime = (audio_mime or "").strip() or "audio/webm"
    ext = ".webm"
    if "wav" in mime:
        ext = ".wav"
    elif "mpeg" in mime or "mp3" in mime:
        ext = ".mp3"
    elif "ogg" in mime:
        ext = ".ogg"
    elif "mp4" in mime or "m4a" in mime:
        ext = ".m4a"
    path = NOTE_AUDIO_DIR / f"{note_id}{ext}"
    path.write_bytes(audio_bytes)
    rel = str(path.relative_to(DATA_DIR)).replace("\\", "/")
    return update_note(note_id, audio_path=rel, audio_mime=mime)


def classify_reminder_bucket(
    note: dict,
    *,
    today: Optional[date] = None,
    upcoming_days: int = 7,
) -> str:
    """Return: past_due | due_today | upcoming | later | done | no_due"""
    if note.get("reminder_done"):
        return "done"
    due = parse_reminder_date(note.get("reminder_at") or "")
    if not due:
        return "no_due"
    today = today or date.today()
    if due < today:
        return "past_due"
    if due == today:
        return "due_today"
    if due <= today + timedelta(days=upcoming_days):
        return "upcoming"
    return "later"


def group_open_reminders(
    notes: Optional[list[dict]] = None,
    *,
    today: Optional[date] = None,
    upcoming_days: int = 7,
) -> dict[str, list[dict]]:
    today = today or date.today()
    buckets: dict[str, list[dict]] = {
        "past_due": [],
        "due_today": [],
        "upcoming": [],
        "later": [],
        "no_due": [],
    }
    for n in notes if notes is not None else load_notes():
        if n.get("reminder_done"):
            continue
        if not (n.get("reminder_at") or "").strip():
            continue
        b = classify_reminder_bucket(n, today=today, upcoming_days=upcoming_days)
        if b in buckets:
            buckets[b].append(n)
    for k in buckets:
        buckets[k].sort(key=lambda x: x.get("reminder_at") or "")
    return buckets


def read_note_audio_bytes(note: dict) -> Optional[bytes]:
    rel = (note.get("audio_path") or "").strip()
    if not rel:
        return None
    path = DATA_DIR / rel
    if not path.exists():
        # allow absolute leftover paths
        path = Path(rel)
    if not path.exists():
        return None
    try:
        return path.read_bytes()
    except Exception:
        return None


def transcribe_audio_with_gemini(
    audio_bytes: bytes,
    *,
    mime_type: str = "audio/webm",
    company: Optional[dict] = None,
) -> str:
    """
    Best-effort Gemini multimodal transcription.
    Returns empty string when key missing or API fails.
    """
    from .llm import DEFAULT_GEMINI_MODEL, gemini_key, provider_model

    key = gemini_key(company)
    if not key or not audio_bytes:
        return ""
    import requests

    model = provider_model("gemini", company) or DEFAULT_GEMINI_MODEL
    mime = (mime_type or "audio/webm").strip() or "audio/webm"
    b64 = base64.b64encode(audio_bytes).decode("ascii")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    prompt = (
        "Transcribe this voice note into plain text. "
        "Return only the transcript, no preamble."
    )
    try:
        resp = requests.post(
            url,
            params={"key": key},
            json={
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {"inline_data": {"mime_type": mime, "data": b64}},
                        ]
                    }
                ]
            },
            timeout=90,
        )
        if resp.status_code != 200:
            return ""
        data = resp.json()
        return (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
            or ""
        ).strip()
    except Exception:
        return ""
