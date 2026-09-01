from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(include_in_schema=False)

_WEB_ROOT = Path(__file__).resolve().parent.parent / "web"


@router.get("/admin", response_class=FileResponse)
@router.get("/admin/", response_class=FileResponse)
def admin_console() -> FileResponse:
    return FileResponse(
        _WEB_ROOT / "admin.html",
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )
