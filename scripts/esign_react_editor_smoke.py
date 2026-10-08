"""Smoke: Compose React PDF Field Editor only (no auth). Run:
  py -3 -m streamlit run scripts/esign_react_editor_smoke.py --server.port 8610
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from src.pdf_field_editor import render_pdf_field_editor

st.set_page_config(page_title="Esign React editor smoke", layout="wide")
st.caption("v2026.10.07j · Esign React editor only · smoke")
st.markdown("#### Compose")
render_pdf_field_editor(height=960, key="smoke_pdf_field_editor")
