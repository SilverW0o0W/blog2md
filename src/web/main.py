from __future__ import annotations

import json
import re
import tempfile
from collections import deque
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import quote
from zipfile import ZIP_DEFLATED, ZipFile

import requests
from blog2md import convert_url_to_md
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel


app = FastAPI(title="blog2md web", version="0.1.0")
BASE_DIR = Path(__file__).resolve().parent
INDEX_HTML = BASE_DIR / "templates" / "index.html"
MAX_HISTORY = 20
RECENT_CONVERSIONS: deque[dict[str, Any]] = deque(maxlen=MAX_HISTORY)
RECENT_CONVERSIONS_LOCK = Lock()


class ConvertRequest(BaseModel):
    url: str


def _sanitize_filename(name: str) -> str:
    safe = re.sub(r"[^\w\-.]+", "_", name.strip(), flags=re.UNICODE)
    return safe.strip("._") or "article"


def _ascii_fallback_filename(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name.strip())
    return safe.strip("._") or "article.zip"


def _build_zip_bytes(markdown_path: Path, image_paths: list[Path], metadata: dict[str, Any]) -> bytes:
    buf = BytesIO()
    with ZipFile(buf, "w", compression=ZIP_DEFLATED) as zf:
        zf.write(markdown_path, arcname=markdown_path.name)
        for image in image_paths:
            if not image.exists():
                continue
            try:
                arcname = image.relative_to(markdown_path.parent)
            except ValueError:
                arcname = Path("assets") / image.name
            zf.write(image, arcname=str(arcname).replace("\\", "/"))
        zf.writestr("meta.json", json.dumps(metadata, ensure_ascii=False, indent=2))

    buf.seek(0)
    return buf.read()


def _build_meta_payload(result: Any, *, source_url: str, zip_name: str) -> dict[str, Any]:
    return {
        "converted_at": datetime.now(timezone.utc).isoformat(),
        "source_url": source_url,
        "site_name": result.metadata.site_name,
        "title": result.metadata.title,
        "author": result.metadata.author,
        "published_at": result.metadata.published_at,
        "updated_at": result.metadata.updated_at,
        "cache_html_path": str(result.cache_html_path),
        "from_cache": result.from_cache,
        "markdown_filename": result.markdown_path.name,
        "image_count": len(result.image_paths),
        "zip_name": zip_name,
    }


def _record_history(item: dict[str, Any]) -> None:
    with RECENT_CONVERSIONS_LOCK:
        RECENT_CONVERSIONS.appendleft(item)


def _build_content_disposition(filename: str) -> str:
    # Starlette encodes headers as latin-1, so keep filename= ASCII only.
    fallback = _ascii_fallback_filename(filename)
    encoded = quote(filename, safe="")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"


@app.get("/api/history")
def history(limit: int = Query(default=10, ge=1, le=MAX_HISTORY)) -> dict[str, list[dict[str, Any]]]:
    with RECENT_CONVERSIONS_LOCK:
        items = list(RECENT_CONVERSIONS)[:limit]
    return {"items": items}


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    if not INDEX_HTML.exists():
        raise HTTPException(status_code=500, detail="UI template not found")
    return HTMLResponse(INDEX_HTML.read_text(encoding="utf-8"))


@app.post("/api/convert")
def convert(payload: ConvertRequest) -> StreamingResponse:
    url = payload.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            output_markdown = tmp_path / "article.md"

            result = convert_url_to_md(
                url=url,
                output=output_markdown,
                cache_dir=Path("cache") / "html",
                timeout=20,
            )

            zip_name = f"{_sanitize_filename(result.metadata.title)}.zip"
            meta_payload = _build_meta_payload(result, source_url=url, zip_name=zip_name)
            zip_bytes = _build_zip_bytes(result.markdown_path, result.image_paths, meta_payload)
            _record_history(meta_payload)
    except ValueError as exc:
        # Unsupported domain or parse failures from blog2md.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch remote content: {exc}") from exc
    except Exception as exc:  # pragma: no cover - generic fallback
        raise HTTPException(status_code=500, detail=f"Unexpected conversion error: {exc}") from exc

    content_disposition = _build_content_disposition(zip_name)
    headers = {"Content-Disposition": content_disposition}
    return StreamingResponse(BytesIO(zip_bytes), media_type="application/zip", headers=headers)

