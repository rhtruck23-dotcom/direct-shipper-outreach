"""
Esign field placer — Streamlit custom component.

Uses Streamlit.setComponentValue (bidirectional API) so right-click
Add text/date/sign returns {op,type,x,y,page} to Python. Unlike
components.html + hidden Apply bridge, this works in Cloud iframes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import streamlit.components.v1 as components

_FRONTEND = (Path(__file__).parent / "frontend").absolute()
_component_func = components.declare_component("esign_placer", path=str(_FRONTEND))


def esign_placer(
    *,
    src: str,
    fields: list[dict[str, Any]],
    page: int = 0,
    def_w: float = 0.28,
    def_h: float = 0.04,
    next_type: str = "text",
    key: Optional[str] = None,
    height: Optional[int] = None,
) -> Any:
    """
    Interactive PDF-page placer.

    Returns a dict from the browser via setComponentValue, e.g.:
      {op:'add', type:'text', x:0.25, y:0.4, page:0, t:<unix_ms>}
    or None before the first interaction.
    """
    return _component_func(
        src=src,
        fields=fields or [],
        page=int(page),
        def_w=float(def_w),
        def_h=float(def_h),
        next_type=str(next_type or "text").lower(),
        height=height,
        key=key,
        default=None,
    )
