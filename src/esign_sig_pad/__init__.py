"""Minimal Streamlit signature pad for the public ?esign=TOKEN fill page."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import streamlit.components.v1 as components

_FRONTEND = (Path(__file__).parent / "frontend").resolve()
_COMPONENT = None
if (_FRONTEND / "index.html").is_file():
    _COMPONENT = components.declare_component("esign_sig_pad", path=str(_FRONTEND))


def render_signature_pad(*, key: str, height: int = 220) -> Optional[str]:
    """
    Draw pad that returns a PNG data URL via setComponentValue, or None / ''.
    """
    if _COMPONENT is None:
        return None
    value: Any = _COMPONENT(default="", key=key, height=height)
    if value is None:
        return None
    text = str(value).strip()
    if text.startswith("data:image"):
        return text
    return ""
