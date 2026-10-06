"""
Esign Docs — overlay AcroForm fields on an original PDF (layout unchanged).

Sign fields are fillable text widgets (typed name), not PKI / DigSig certificates.
"""
from __future__ import annotations

import io
import json
import secrets
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .paths import DATA_DIR

ESIGN_DIR = DATA_DIR / "esign"
ESIGN_INDEX = ESIGN_DIR / "index.json"

FIELD_TYPES = ("text", "date", "sign")

# Default field size as fractions of page width/height
_DEFAULT_W = 0.28
_DEFAULT_H = 0.035


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_esign_dir() -> Path:
    ESIGN_DIR.mkdir(parents=True, exist_ok=True)
    return ESIGN_DIR


def load_index() -> dict[str, Any]:
    ensure_esign_dir()
    if not ESIGN_INDEX.exists():
        return {"version": 1, "docs": []}
    try:
        with open(ESIGN_INDEX, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"version": 1, "docs": []}
        data.setdefault("docs", [])
        return data
    except Exception:
        return {"version": 1, "docs": []}


def save_index(index: dict[str, Any]) -> None:
    ensure_esign_dir()
    with open(ESIGN_INDEX, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)


def doc_dir(doc_id: str) -> Path:
    return ensure_esign_dir() / doc_id


def new_field(
    *,
    field_type: str = "text",
    page: int = 0,
    x: float = 0.1,
    y_from_top: float = 0.15,
    w: float = _DEFAULT_W,
    h: float = _DEFAULT_H,
    label: str = "",
) -> dict[str, Any]:
    ft = (field_type or "text").lower().strip()
    if ft not in FIELD_TYPES:
        ft = "text"
    base_label = label.strip() or {
        "text": "Text",
        "date": "Date",
        "sign": "Sign",
    }.get(ft, "Field")
    fid = f"f_{uuid.uuid4().hex[:10]}"
    return {
        "id": fid,
        "type": ft,
        "name": f"{ft}_{fid}",
        "label": base_label,
        "page": max(0, int(page)),
        "x": float(max(0.0, min(0.95, x))),
        "y_from_top": float(max(0.0, min(0.95, y_from_top))),
        "w": float(max(0.05, min(0.9, w))),
        "h": float(max(0.02, min(0.2, h))),
    }


def pdf_page_count(pdf_bytes: bytes) -> int:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    return len(reader.pages)


def pdf_page_size(pdf_bytes: bytes, page_index: int = 0) -> tuple[float, float]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    if page_index < 0 or page_index >= len(reader.pages):
        raise IndexError(f"page {page_index} out of range")
    box = reader.pages[page_index].mediabox
    return float(box.width), float(box.height)


def _rect_from_norm(
    *,
    page_w: float,
    page_h: float,
    x: float,
    y_from_top: float,
    w: float,
    h: float,
) -> tuple[float, float, float, float]:
    """Normalize top-left fractions → PDF bottom-left Rect (llx, lly, urx, ury)."""
    llx = x * page_w
    field_h = h * page_h
    field_w = w * page_w
    # y_from_top is top edge of field as fraction from page top
    ury = page_h - (y_from_top * page_h)
    lly = ury - field_h
    urx = llx + field_w
    return llx, lly, urx, ury


def build_fillable_pdf(original_pdf: bytes, fields: list[dict[str, Any]]) -> bytes:
    """
    Clone original PDF and overlay AcroForm text widgets only.
    Does not redraw or reflow page content.
    """
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import (
        ArrayObject,
        BooleanObject,
        DictionaryObject,
        FloatObject,
        NameObject,
        NumberObject,
        TextStringObject,
    )

    reader = PdfReader(io.BytesIO(original_pdf))
    writer = PdfWriter()
    writer.append(reader)

    field_refs: list = []
    for i, field in enumerate(fields or []):
        page_i = int(field.get("page") or 0)
        if page_i < 0 or page_i >= len(writer.pages):
            continue
        page = writer.pages[page_i]
        box = page.mediabox
        page_w, page_h = float(box.width), float(box.height)
        llx, lly, urx, ury = _rect_from_norm(
            page_w=page_w,
            page_h=page_h,
            x=float(field.get("x") or 0.1),
            y_from_top=float(field.get("y_from_top") or 0.15),
            w=float(field.get("w") or _DEFAULT_W),
            h=float(field.get("h") or _DEFAULT_H),
        )
        name = str(field.get("name") or f"field_{i}")
        label = str(field.get("label") or name)
        ftype = str(field.get("type") or "text")
        # Sign: slightly larger text; Date/Text: standard
        font_size = 14 if ftype == "sign" else 11
        annot = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Widget"),
                NameObject("/FT"): NameObject("/Tx"),
                NameObject("/T"): TextStringObject(name),
                NameObject("/TU"): TextStringObject(label),
                NameObject("/V"): TextStringObject(""),
                NameObject("/DV"): TextStringObject(""),
                NameObject("/Rect"): ArrayObject(
                    [
                        FloatObject(llx),
                        FloatObject(lly),
                        FloatObject(urx),
                        FloatObject(ury),
                    ]
                ),
                NameObject("/F"): NumberObject(4),  # Print
                NameObject("/Ff"): NumberObject(0),
                NameObject("/MK"): DictionaryObject(),
                NameObject("/DA"): TextStringObject(f"/Helv {font_size} Tf 0 g"),
            }
        )
        added = writer.add_annotation(page_i, annot)
        field_refs.append(added.indirect_reference)

    if field_refs:
        root = writer._root_object
        if NameObject("/AcroForm") not in root:
            acro = DictionaryObject(
                {
                    NameObject("/Fields"): ArrayObject(field_refs),
                    NameObject("/NeedAppearances"): BooleanObject(True),
                }
            )
            root[NameObject("/AcroForm")] = writer._add_object(acro)
        else:
            form = root["/AcroForm"].get_object()
            existing = form.get("/Fields", ArrayObject())
            if not isinstance(existing, ArrayObject):
                existing = ArrayObject()
            for ref in field_refs:
                existing.append(ref)
            form[NameObject("/Fields")] = existing
            form[NameObject("/NeedAppearances")] = BooleanObject(True)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def fill_form_values(fillable_pdf: bytes, values: dict[str, str]) -> bytes:
    """Write values into existing AcroForm text fields. Leaves page artwork intact."""
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(fillable_pdf))
    writer = PdfWriter()
    writer.append(reader)
    clean = {str(k): str(v if v is not None else "") for k, v in (values or {}).items()}
    if clean:
        for page in writer.pages:
            try:
                writer.update_page_form_field_values(page, clean)
            except Exception:
                pass
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def create_document(
    *,
    title: str,
    original_pdf: bytes,
    owner_email: str,
    owner_name: str = "",
    fields: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    ensure_esign_dir()
    doc_id = f"es_{uuid.uuid4().hex[:12]}"
    d = doc_dir(doc_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "original.pdf").write_bytes(original_pdf)
    field_list = list(fields or [])
    fillable = build_fillable_pdf(original_pdf, field_list) if field_list else original_pdf
    (d / "fillable.pdf").write_bytes(fillable)
    token = secrets.token_urlsafe(24)
    meta = {
        "id": doc_id,
        "title": (title or "Untitled").strip() or "Untitled",
        "owner_email": (owner_email or "").strip().lower(),
        "owner_name": owner_name or "",
        "status": "ready" if field_list else "draft",
        "fields": field_list,
        "token": token,
        "recipient_email": "",
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "signed_at": "",
        "pages": pdf_page_count(original_pdf),
    }
    (d / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    index = load_index()
    index["docs"].insert(
        0,
        {
            "id": doc_id,
            "title": meta["title"],
            "status": meta["status"],
            "owner_email": meta["owner_email"],
            "created_at": meta["created_at"],
            "updated_at": meta["updated_at"],
        },
    )
    save_index(index)
    return meta


def load_document(doc_id: str) -> Optional[dict[str, Any]]:
    meta_path = doc_dir(doc_id) / "meta.json"
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_document_meta(meta: dict[str, Any]) -> None:
    doc_id = meta["id"]
    d = doc_dir(doc_id)
    d.mkdir(parents=True, exist_ok=True)
    meta["updated_at"] = _utc_now()
    (d / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    index = load_index()
    found = False
    for row in index.get("docs") or []:
        if row.get("id") == doc_id:
            row["title"] = meta.get("title")
            row["status"] = meta.get("status")
            row["updated_at"] = meta.get("updated_at")
            found = True
            break
    if not found:
        index.setdefault("docs", []).insert(
            0,
            {
                "id": doc_id,
                "title": meta.get("title"),
                "status": meta.get("status"),
                "owner_email": meta.get("owner_email"),
                "created_at": meta.get("created_at"),
                "updated_at": meta.get("updated_at"),
            },
        )
    save_index(index)


def update_fields(doc_id: str, fields: list[dict[str, Any]]) -> dict[str, Any]:
    meta = load_document(doc_id)
    if not meta:
        raise FileNotFoundError(doc_id)
    original = (doc_dir(doc_id) / "original.pdf").read_bytes()
    fillable = build_fillable_pdf(original, fields)
    (doc_dir(doc_id) / "fillable.pdf").write_bytes(fillable)
    meta["fields"] = deepcopy(fields)
    meta["status"] = "ready" if fields else "draft"
    save_document_meta(meta)
    return meta


def read_fillable_pdf(doc_id: str) -> bytes:
    path = doc_dir(doc_id) / "fillable.pdf"
    if not path.exists():
        raise FileNotFoundError(doc_id)
    return path.read_bytes()


def read_original_pdf(doc_id: str) -> bytes:
    path = doc_dir(doc_id) / "original.pdf"
    if not path.exists():
        raise FileNotFoundError(doc_id)
    return path.read_bytes()


def read_signed_pdf(doc_id: str) -> Optional[bytes]:
    path = doc_dir(doc_id) / "signed.pdf"
    if not path.exists():
        return None
    return path.read_bytes()


def find_by_token(token: str) -> Optional[dict[str, Any]]:
    token = (token or "").strip()
    if not token:
        return None
    for row in load_index().get("docs") or []:
        meta = load_document(row.get("id") or "")
        if meta and meta.get("token") == token:
            return meta
    # Fallback scan folders
    ensure_esign_dir()
    for child in ESIGN_DIR.iterdir():
        if not child.is_dir():
            continue
        meta = load_document(child.name)
        if meta and meta.get("token") == token:
            return meta
    return None


def mark_sent(doc_id: str, recipient_email: str) -> dict[str, Any]:
    meta = load_document(doc_id)
    if not meta:
        raise FileNotFoundError(doc_id)
    meta["recipient_email"] = (recipient_email or "").strip().lower()
    meta["status"] = "sent"
    # Rotate token for a fresh fill link each send
    if not meta.get("token"):
        meta["token"] = secrets.token_urlsafe(24)
    save_document_meta(meta)
    return meta


def complete_signing(
    doc_id: str,
    values: dict[str, str],
    *,
    signer_email: str = "",
) -> dict[str, Any]:
    """Fill AcroForm values, store signed.pdf, mark completed."""
    meta = load_document(doc_id)
    if not meta:
        raise FileNotFoundError(doc_id)
    fillable = read_fillable_pdf(doc_id)
    signed = fill_form_values(fillable, values)
    (doc_dir(doc_id) / "signed.pdf").write_bytes(signed)
    (doc_dir(doc_id) / "values.json").write_text(
        json.dumps(
            {
                "values": values,
                "signer_email": (signer_email or "").strip().lower(),
                "at": _utc_now(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    meta["status"] = "signed"
    meta["signed_at"] = _utc_now()
    if signer_email:
        meta["signer_email"] = signer_email.strip().lower()
    save_document_meta(meta)
    return meta


def list_documents(*, owner_email: str = "", limit: int = 50) -> list[dict[str, Any]]:
    rows = list(load_index().get("docs") or [])
    owner = (owner_email or "").strip().lower()
    if owner:
        rows = [r for r in rows if (r.get("owner_email") or "").lower() == owner]
    return rows[: max(1, int(limit))]


def fill_link_path(token: str) -> str:
    """Query string fragment for the public fill page."""
    return f"?esign={token}"
