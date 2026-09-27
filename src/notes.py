"""
Global notebooks → sections → pages (OneNote-like).

Local  -> data/onenote_notebooks.json + data/onenote_sections.json + data/onenote_pages.json
         (migrates legacy data/notebooks.json, note_sections.json, notes.json)
Cloud  -> Google Sheet worksheets "notebooks", "note_sections", "notes"
Audio blobs stay local under data/note_audio/ (Sheet stores path/meta only).

Pages store body_html (persisted as `body` for sheet compatibility).
"""
from __future__ import annotations

import base64
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from .paths import DATA_DIR

# Canonical OneNote paths
NOTEBOOKS_JSON = DATA_DIR / "onenote_notebooks.json"
SECTIONS_JSON = DATA_DIR / "onenote_sections.json"
NOTES_JSON = DATA_DIR / "onenote_pages.json"
# Legacy flat / pre-clone paths (read once for migration)
_LEGACY_NOTEBOOKS = DATA_DIR / "notebooks.json"
_LEGACY_SECTIONS = DATA_DIR / "note_sections.json"
_LEGACY_NOTES = DATA_DIR / "notes.json"
NOTE_AUDIO_DIR = DATA_DIR / "note_audio"

NOTEBOOK_COLUMNS = ["id", "name", "created_at", "updated_at"]
SECTION_COLUMNS = ["id", "notebook_id", "name", "order", "created_at", "updated_at"]
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

DEFAULT_NOTEBOOK_NAME = "Quick Notes"
DEFAULT_SECTION_NAME = "General"


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
        "order": 0,
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
    try:
        s["order"] = int(s.get("order") or 0)
    except Exception:
        s["order"] = 0
    s["created_at"] = str(s.get("created_at") or "")
    s["updated_at"] = str(s.get("updated_at") or "")
    if not s["id"]:
        s["id"] = f"sec_{uuid.uuid4().hex[:10]}"
    return s


def _normalize_note(raw: dict) -> dict[str, Any]:
    n = _blank_note()
    # Accept body_html from client snapshot
    if "body_html" in raw and raw.get("body_html") not in (None,) and "body" not in raw:
        raw = {**raw, "body": raw.get("body_html")}
    elif raw.get("body_html") and not raw.get("body"):
        raw = {**raw, "body": raw.get("body_html")}
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


def _merge_legacy_local(canonical: Path, legacy: Path) -> list[dict]:
    rows = _load_json_list(canonical)
    if rows:
        return rows
    return _load_json_list(legacy)


def load_notebooks() -> list[dict]:
    if _using_cloud():
        try:
            rows = _load_sheet_rows("notebooks", NOTEBOOK_COLUMNS, _normalize_notebook)
            if rows:
                return rows
        except Exception:
            pass
    raw = _merge_legacy_local(NOTEBOOKS_JSON, _LEGACY_NOTEBOOKS)
    return [_normalize_notebook(x) for x in raw]


def save_notebooks(notebooks: list[dict]) -> None:
    normalized = [_normalize_notebook(n) for n in notebooks]
    if _using_cloud():
        try:
            _save_sheet_rows("notebooks", NOTEBOOK_COLUMNS, normalized, _normalize_notebook)
            _save_json_list(NOTEBOOKS_JSON, normalized)
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
    raw = _merge_legacy_local(SECTIONS_JSON, _LEGACY_SECTIONS)
    return [_normalize_section(x) for x in raw]


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
    raw = _merge_legacy_local(NOTES_JSON, _LEGACY_NOTES)
    return [_migrate_note_row(_normalize_note(x)) for x in raw]


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


def ensure_default_section(notebook_id: str, *, name: str = DEFAULT_SECTION_NAME) -> dict:
    """Return (or create) the default section for a notebook."""
    nid = (notebook_id or "").strip()
    if not nid:
        nid = ensure_default_notebook()["id"]
    sections = load_sections()
    for s in sections:
        if s.get("notebook_id") == nid and (s.get("name") or "") == name:
            return s
    # Prefer first section if any exist for this notebook
    existing = [s for s in sections if s.get("notebook_id") == nid]
    if existing and name == DEFAULT_SECTION_NAME:
        existing.sort(key=lambda x: (x.get("order") or 0, x.get("name") or ""))
        # Still create General if none named General — OneNote clone expects it
        pass
    now = _utc_now()
    order = max([int(s.get("order") or 0) for s in existing], default=-1) + 1
    sec = _normalize_section(
        {
            "id": f"sec_{uuid.uuid4().hex[:10]}",
            "notebook_id": nid,
            "name": name,
            "order": order,
            "created_at": now,
            "updated_at": now,
        }
    )
    sections.append(sec)
    save_sections(sections)
    return sec


def migrate_flat_notes_to_hierarchy() -> dict[str, Any]:
    """
    Migrate legacy flat notes into Notebook → Section → Page.

    - Default notebook: Quick Notes
    - Default section: General
    - Each orphan / flat note becomes one page under General
    Idempotent.
    """
    notebooks = load_notebooks()
    sections = load_sections()
    pages = load_notes()
    now = _utc_now()
    changed = False

    # Ensure Quick Notes notebook
    quick = next(
        (n for n in notebooks if (n.get("name") or "") == DEFAULT_NOTEBOOK_NAME),
        None,
    )
    if not quick:
        # Rename lone "General" notebook if that was the old default
        if len(notebooks) == 1 and (notebooks[0].get("name") or "") in (
            "General",
            "Untitled",
            "",
        ):
            notebooks[0]["name"] = DEFAULT_NOTEBOOK_NAME
            notebooks[0]["updated_at"] = now
            quick = notebooks[0]
            changed = True
        else:
            quick = _normalize_notebook(
                {
                    "id": f"nb_{uuid.uuid4().hex[:10]}",
                    "name": DEFAULT_NOTEBOOK_NAME,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            notebooks.append(quick)
            changed = True

    # Ensure every notebook has a General section
    sec_by_nb: dict[str, dict] = {}
    for nb in notebooks:
        nid = nb["id"]
        general = next(
            (
                s
                for s in sections
                if s.get("notebook_id") == nid
                and (s.get("name") or "") == DEFAULT_SECTION_NAME
            ),
            None,
        )
        if not general:
            order = (
                max(
                    [
                        int(s.get("order") or 0)
                        for s in sections
                        if s.get("notebook_id") == nid
                    ],
                    default=-1,
                )
                + 1
            )
            general = _normalize_section(
                {
                    "id": f"sec_{uuid.uuid4().hex[:10]}",
                    "notebook_id": nid,
                    "name": DEFAULT_SECTION_NAME,
                    "order": order,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            sections.append(general)
            changed = True
        sec_by_nb[nid] = general

    nb_ids = {n["id"] for n in notebooks}
    for i, page in enumerate(pages):
        p = _migrate_note_row(page)
        nid = (p.get("notebook_id") or "").strip()
        if not nid or nid not in nb_ids:
            p["notebook_id"] = quick["id"]
            changed = True
            nid = quick["id"]
        sid = (p.get("section_id") or "").strip()
        valid_secs = {
            s["id"] for s in sections if s.get("notebook_id") == nid
        }
        if not sid or sid not in valid_secs:
            p["section_id"] = sec_by_nb[nid]["id"]
            changed = True
        pages[i] = p

    if changed:
        save_notebooks(notebooks)
        save_sections(sections)
        save_notes(pages)

    return {
        "notebooks": notebooks,
        "sections": sections,
        "pages": pages,
        "changed": changed,
    }


def ensure_default_notebook() -> dict:
    """Ensure Quick Notes + General exist; return the default notebook."""
    state = migrate_flat_notes_to_hierarchy()
    notebooks = state["notebooks"]
    quick = next(
        (n for n in notebooks if (n.get("name") or "") == DEFAULT_NOTEBOOK_NAME),
        notebooks[0] if notebooks else None,
    )
    if quick is None:
        now = _utc_now()
        quick = _normalize_notebook(
            {
                "id": f"nb_{uuid.uuid4().hex[:10]}",
                "name": DEFAULT_NOTEBOOK_NAME,
                "created_at": now,
                "updated_at": now,
            }
        )
        save_notebooks([quick])
        ensure_default_section(quick["id"])
    else:
        ensure_default_section(quick["id"])
    return quick


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
    ensure_default_section(nb["id"])
    return nb


def create_section(*, notebook_id: str, name: str = "", order: Optional[int] = None) -> dict:
    sections = load_sections()
    now = _utc_now()
    nid = notebook_id or ensure_default_notebook()["id"]
    if order is None:
        existing = [s for s in sections if s.get("notebook_id") == nid]
        order = max([int(s.get("order") or 0) for s in existing], default=-1) + 1
    sec = _normalize_section(
        {
            "id": f"sec_{uuid.uuid4().hex[:10]}",
            "notebook_id": nid,
            "name": (name or "").strip() or "New section",
            "order": order,
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
    secs.sort(key=lambda s: (int(s.get("order") or 0), s.get("name") or ""))
    return secs


def delete_notebook(notebook_id: str) -> bool:
    nid = (notebook_id or "").strip()
    if not nid:
        return False
    all_nb = load_notebooks()
    notebooks = [n for n in all_nb if n.get("id") != nid]
    if len(notebooks) == len(all_nb):
        return False
    if not notebooks:
        return False  # keep at least one notebook
    save_notebooks(notebooks)
    save_sections([s for s in load_sections() if s.get("notebook_id") != nid])
    save_notes([p for p in load_notes() if p.get("notebook_id") != nid])
    return True


def delete_section(section_id: str) -> bool:
    sid = (section_id or "").strip()
    if not sid:
        return False
    sections = load_sections()
    before = len(sections)
    sections = [s for s in sections if s.get("id") != sid]
    if len(sections) == before:
        return False
    save_sections(sections)
    # Orphan pages → move to General of same notebook if possible
    pages = load_notes()
    changed = False
    for i, p in enumerate(pages):
        if p.get("section_id") == sid:
            general = ensure_default_section(p.get("notebook_id") or "")
            pages[i] = {**p, "section_id": general["id"], "updated_at": _utc_now()}
            changed = True
    if changed:
        save_notes(pages)
    return True


def delete_page(page_id: str) -> bool:
    pid = (page_id or "").strip()
    if not pid:
        return False
    notes = load_notes()
    before = len(notes)
    notes = [n for n in notes if n.get("id") != pid]
    if len(notes) == before:
        return False
    save_notes(notes)
    return True


def rename_notebook(notebook_id: str, name: str) -> Optional[dict]:
    notebooks = load_notebooks()
    out = None
    for i, n in enumerate(notebooks):
        if n.get("id") == notebook_id:
            notebooks[i] = {
                **n,
                "name": (name or "").strip() or n.get("name") or "Untitled",
                "updated_at": _utc_now(),
            }
            out = notebooks[i]
            break
    if out:
        save_notebooks(notebooks)
    return out


def rename_section(section_id: str, name: str) -> Optional[dict]:
    sections = load_sections()
    out = None
    for i, s in enumerate(sections):
        if s.get("id") == section_id:
            sections[i] = {
                **s,
                "name": (name or "").strip() or s.get("name") or "Untitled section",
                "updated_at": _utc_now(),
            }
            out = sections[i]
            break
    if out:
        save_sections(sections)
    return out


def _write_audio_b64(note_id: str, audio_b64: str, audio_mime: str = "") -> tuple[str, str]:
    """Decode base64 audio and write under note_audio/. Returns (rel_path, mime)."""
    raw = (audio_b64 or "").strip()
    if not raw:
        return "", ""
    # Allow data-URL prefix
    mime = (audio_mime or "").strip() or "audio/webm"
    if raw.startswith("data:"):
        try:
            header, b64part = raw.split(",", 1)
            raw = b64part
            if ";base64" in header and header.startswith("data:"):
                mime = header[5:].split(";")[0] or mime
        except Exception:
            pass
    try:
        audio_bytes = base64.b64decode(raw)
    except Exception:
        return "", ""
    if not audio_bytes:
        return "", ""
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
    rel = str(path.relative_to(DATA_DIR)).replace("\\", "/")
    return rel, mime


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
    audio_b64: str = "",
) -> dict:
    ensure_default_notebook()
    notes = load_notes()
    now = _utc_now()
    note_id = f"note_{uuid.uuid4().hex[:10]}"
    audio_path = ""
    mime = (audio_mime or "").strip()
    if audio_b64 and not audio_bytes:
        audio_path, mime = _write_audio_b64(note_id, audio_b64, mime)
    elif audio_bytes:
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
    nid = notebook_id or ensure_default_notebook()["id"]
    sid = (section_id or "").strip()
    if not sid:
        sid = ensure_default_section(nid)["id"]
    note = _normalize_note(
        {
            "id": note_id,
            "notebook_id": nid,
            "section_id": sid,
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
    if "body_html" in fields and "body" not in fields:
        fields = {**fields, "body": fields.pop("body_html")}
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


def page_to_client(note: dict) -> dict[str, Any]:
    """Serialize a page for the client OneNote panel (includes body_html)."""
    n = _migrate_note_row(note)
    return {
        "id": n["id"],
        "notebook_id": n["notebook_id"],
        "section_id": n["section_id"],
        "title": n["title"],
        "body_html": n["body"],
        "body": n["body"],
        "color": n["color"],
        "reminder_at": n["reminder_at"],
        "reminder_done": n["reminder_done"],
        "audio_path": n["audio_path"],
        "audio_mime": n["audio_mime"],
        "audio_b64": "",
        "created_at": n["created_at"],
        "updated_at": n["updated_at"],
        "created_by": n["created_by"],
    }


def export_tree_for_client() -> dict[str, Any]:
    """Full hierarchy for zero-rerun client panel."""
    ensure_default_notebook()
    notebooks = load_notebooks()
    sections = load_sections()
    pages = [page_to_client(p) for p in load_notes()]
    return {
        "notebooks": [
            {
                "id": n["id"],
                "name": n["name"],
                "created_at": n.get("created_at") or "",
                "updated_at": n.get("updated_at") or "",
            }
            for n in notebooks
        ],
        "sections": [
            {
                "id": s["id"],
                "notebook_id": s["notebook_id"],
                "name": s["name"],
                "order": int(s.get("order") or 0),
                "created_at": s.get("created_at") or "",
                "updated_at": s.get("updated_at") or "",
            }
            for s in sections
        ],
        "pages": pages,
    }


def apply_onenote_snapshot(
    snapshot: dict[str, Any],
    *,
    created_by: str = "",
    company: Optional[dict] = None,
    transcribe_audio: bool = False,
) -> dict[str, Any]:
    """
    Replace hierarchy from client Save payload.
    Decodes audio_b64 onto pages; optionally Gemini-transcribes and appends.
    """
    now = _utc_now()
    notebooks_in = snapshot.get("notebooks") or []
    sections_in = snapshot.get("sections") or []
    pages_in = snapshot.get("pages") or []

    notebooks = [_normalize_notebook(n) for n in notebooks_in if isinstance(n, dict)]
    if not notebooks:
        notebooks = [
            _normalize_notebook(
                {
                    "id": f"nb_{uuid.uuid4().hex[:10]}",
                    "name": DEFAULT_NOTEBOOK_NAME,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        ]

    sections = [_normalize_section(s) for s in sections_in if isinstance(s, dict)]
    nb_ids = {n["id"] for n in notebooks}
    # Drop sections pointing at missing notebooks
    sections = [s for s in sections if s.get("notebook_id") in nb_ids]

    pages_out: list[dict] = []
    for raw in pages_in:
        if not isinstance(raw, dict):
            continue
        p = _normalize_note(raw)
        if p.get("notebook_id") not in nb_ids:
            p["notebook_id"] = notebooks[0]["id"]
        audio_b64 = str(raw.get("audio_b64") or "").strip()
        if audio_b64:
            rel, mime = _write_audio_b64(
                p["id"], audio_b64, str(raw.get("audio_mime") or p.get("audio_mime") or "")
            )
            if rel:
                p["audio_path"] = rel
                p["audio_mime"] = mime
            if transcribe_audio or raw.get("transcribe_on_save"):
                try:
                    audio_bytes = base64.b64decode(
                        audio_b64.split(",", 1)[-1] if "," in audio_b64 else audio_b64
                    )
                    transcript = transcribe_audio_with_gemini(
                        audio_bytes,
                        mime_type=p.get("audio_mime") or "audio/webm",
                        company=company,
                    )
                    if transcript:
                        body = p.get("body") or ""
                        sep = "" if not body or body.endswith(("\n", " ")) else " "
                        p["body"] = (body + sep + transcript).strip() if body else transcript
                except Exception:
                    pass
        if created_by and not p.get("created_by"):
            p["created_by"] = created_by
        if not p.get("updated_at"):
            p["updated_at"] = now
        pages_out.append(p)

    # Ensure each notebook has at least one section
    for nb in notebooks:
        if not any(s.get("notebook_id") == nb["id"] for s in sections):
            sections.append(
                _normalize_section(
                    {
                        "id": f"sec_{uuid.uuid4().hex[:10]}",
                        "notebook_id": nb["id"],
                        "name": DEFAULT_SECTION_NAME,
                        "order": 0,
                        "created_at": now,
                        "updated_at": now,
                    }
                )
            )

    # Fix pages with missing section
    sec_ids = {s["id"] for s in sections}
    general_by_nb: dict[str, str] = {}
    for s in sections:
        if (s.get("name") or "") == DEFAULT_SECTION_NAME:
            general_by_nb[s["notebook_id"]] = s["id"]
    for p in pages_out:
        if p.get("section_id") not in sec_ids:
            gid = general_by_nb.get(p["notebook_id"])
            if not gid:
                sec = _normalize_section(
                    {
                        "id": f"sec_{uuid.uuid4().hex[:10]}",
                        "notebook_id": p["notebook_id"],
                        "name": DEFAULT_SECTION_NAME,
                        "order": 0,
                        "created_at": now,
                        "updated_at": now,
                    }
                )
                sections.append(sec)
                sec_ids.add(sec["id"])
                general_by_nb[p["notebook_id"]] = sec["id"]
                gid = sec["id"]
            p["section_id"] = gid

    save_notebooks(notebooks)
    save_sections(sections)
    save_notes(pages_out)
    return export_tree_for_client()


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
