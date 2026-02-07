from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/debug", tags=["debug"])
_DEBUG_PANEL_PATH = Path(__file__).resolve().parents[1] / "static" / "debug_panel.html"


@router.get("/panel", response_class=HTMLResponse)
def debug_panel() -> HTMLResponse:
    html = _DEBUG_PANEL_PATH.read_text(encoding="utf-8")
    return HTMLResponse(content=html)
