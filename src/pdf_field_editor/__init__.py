"""
PDF Field Editor embed — React SPA inside Streamlit Esign Docs.

Same product: Streamlit hosts CRM + Esign; field place/drag/resize/download
runs in the bundled Vite SPA (or an optional external URL override).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import streamlit as st
import streamlit.components.v1 as components

# Bump when shipping frontend fixes so Cloud iframe URL/key change (cache bust).
COMPONENT_VERSION = "2026.10.07j"

_FRONTEND = (Path(__file__).parent / "frontend").resolve()
_COMPONENT = None
if (_FRONTEND / "index.html").is_file():
    # Versioned component name → new /component/... path on Streamlit Cloud.
    _COMPONENT = components.declare_component(
        f"pdf_field_editor_v{COMPONENT_VERSION.replace('.', '_')}",
        path=str(_FRONTEND),
    )

DEFAULT_LOCAL_DEV_URL = "http://127.0.0.1:5173"


def resolve_pdf_field_editor_url() -> Optional[str]:
    """
    Optional external URL for the SPA (Vercel / Vite dev).

    Priority: st.secrets PDF_FIELD_EDITOR_URL → env → None (use bundled).
    """
    for key in ("PDF_FIELD_EDITOR_URL", "pdf_field_editor_url"):
        try:
            raw = st.secrets.get(key, None)
        except Exception:
            raw = None
        if raw is not None and str(raw).strip():
            return str(raw).strip().rstrip("/")
    env = (os.environ.get("PDF_FIELD_EDITOR_URL") or "").strip()
    return env.rstrip("/") or None


def bundled_frontend_ready() -> bool:
    return _COMPONENT is not None and (_FRONTEND / "index.html").is_file()


def _force_editor_iframe_height(height: int) -> None:
    """
    Custom components often start at iframe height 0 until setFrameHeight.
    Force a visible min-height so the React toolbar is never blank.
    """
    h = int(height)
    st.markdown(
        f"""
<style>
div[data-testid="stCustomComponentV1"] iframe {{
  min-height: {h}px !important;
  height: {h}px !important;
}}
</style>
""",
        unsafe_allow_html=True,
    )


def render_pdf_field_editor(*, height: int = 920, key: str = "pdf_field_editor") -> Any:
    """
    Embed the PDF Field Editor full-width in the current Streamlit page.

    Returns the latest setComponentValue from the SPA (e.g. save_to_outreach),
    or None when using an external iframe / no value yet.

    1) If PDF_FIELD_EDITOR_URL is set → iframe that URL (Cloud + Vercel, or local Vite).
    2) Else if bundled frontend exists → Streamlit custom component (same deploy).
    3) Else try local Vite default URL with a short hint.
    """
    h = max(640, int(height))
    url = resolve_pdf_field_editor_url()
    if url:
        bust = f"{url}{'&' if '?' in url else '?'}v={COMPONENT_VERSION}"
        st.caption(f"PDF Field Editor · {bust}")
        components.iframe(bust, height=h, scrolling=True)
        return None

    if bundled_frontend_ready() and _COMPONENT is not None:
        st.caption(
            f"PDF Field Editor · v{COMPONENT_VERSION} · Upload · "
            "Text / Date / Signature / Typewriter · Save to Outreach · download."
        )
        _force_editor_iframe_height(h)
        # Versioned key + height= so Cloud cannot reuse a stale iframe instance.
        return _COMPONENT(
            default=None,
            key=f"{key}_{COMPONENT_VERSION}",
            height=h,
        )

    # Local fallback: Vite dev server
    st.info(
        "Bundled editor assets missing. Start the SPA with "
        "`pnpm --dir pdf-field-editor dev` (port 5173), or run "
        "`scripts/dev_with_pdf_editor.ps1`. "
        "On Streamlit Cloud, set secret **PDF_FIELD_EDITOR_URL** or commit a build "
        "(`pnpm --dir pdf-field-editor build` → `src/pdf_field_editor/frontend/`)."
    )
    components.iframe(DEFAULT_LOCAL_DEV_URL, height=h, scrolling=True)
    return None
