from __future__ import annotations

import base64
import json
import mimetypes
import re
import sqlite3
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from collections import deque
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import quote
from zipfile import ZIP_DEFLATED, ZipFile

import bleach
import markdown as markdown_lib
import requests
from blog2md.cnblogs_url_to_md import CnblogsHtmlToMarkdownConverter
from blog2md.site_common import UrlHtmlCacheLoader
from blog2md.site_router import select_site
from blog2md import convert_url_to_md
from blog2md.wechat_url_to_md import WechatHtmlToMarkdownConverter
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from src.web.tools import (
    MarkdownFormatterService,
    build_formatter_config,
    build_unified_diff_from_texts,
    load_web_settings_from_toml,
)
from src.web.tools.markdown_formatter import MarkdownFormatValidationError, format_validation_report


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _init_history_db()
    _cleanup_cache_files_once()
    _start_cache_cleanup_worker()
    try:
        yield
    finally:
        _stop_cache_cleanup_worker()


app = FastAPI(title="blog2md web", version="0.1.0", lifespan=lifespan)
BASE_DIR = Path(__file__).resolve().parent
INDEX_HTML = BASE_DIR / "templates" / "index.html"
MAX_HISTORY = 20
RECENT_CONVERSIONS: deque[dict[str, Any]] = deque(maxlen=MAX_HISTORY)
RECENT_CONVERSIONS_LOCK = Lock()
HISTORY_DB_LOCK = Lock()
_CACHE_CLEANUP_STOP = threading.Event()
_CACHE_CLEANUP_THREAD: threading.Thread | None = None
MARKDOWN_IMAGE_TOKEN_RE = re.compile(r"!\[(?P<alt>[^]]*)\]\((?P<target>[^)]+)\)")
HTML_MEDIA_SRC_RE = re.compile(
    r'(<(?:img|video|audio|source)\b[^>]*?\bsrc=["\'])([^"\']+)(["\'])',
    re.IGNORECASE,
)
PREVIEW_ALLOWED_TAGS = set(bleach.sanitizer.ALLOWED_TAGS).union(
    {
        "p",
        "pre",
        "code",
        "blockquote",
        "hr",
        "br",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "img",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
    }
)
PREVIEW_ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "rel", "target"],
    "img": ["src", "alt", "title"],
    "code": ["class"],
    "pre": ["class"],
}


def _get_nested_dict(source: dict[str, Any], key: str) -> dict[str, Any]:
    value = source.get(key)
    return value if isinstance(value, dict) else {}


def _resolve_int_setting(value: Any, default: int, *, minimum: int = 1) -> int:
    if isinstance(value, int):
        return max(minimum, value)
    return default


def _resolve_path_setting(value: Any, default: str) -> Path:
    if isinstance(value, str) and value.strip():
        return Path(value).expanduser().resolve()
    return Path(default).expanduser().resolve()


WEB_SETTINGS = load_web_settings_from_toml()
WEB_HISTORY_SETTINGS = _get_nested_dict(WEB_SETTINGS, "history")
WEB_CACHE_SETTINGS = _get_nested_dict(WEB_SETTINGS, "cache")
HISTORY_DB_PATH = _resolve_path_setting(WEB_HISTORY_SETTINGS.get("db_path"), "cache/web_history.db")
CACHE_HTML_DIR = _resolve_path_setting(WEB_CACHE_SETTINGS.get("html_dir"), "cache/html")
CACHE_RETENTION_DAYS = _resolve_int_setting(WEB_CACHE_SETTINGS.get("retention_days"), 90)
CACHE_CLEANUP_INTERVAL_HOURS = _resolve_int_setting(WEB_CACHE_SETTINGS.get("cleanup_interval_hours"), 24)


class ConvertRequest(BaseModel):
    url: str


class PreviewRequest(BaseModel):
    url: str


class RenderMarkdownRequest(BaseModel):
    markdown: str
    asset_map: dict[str, str] | None = None


class OptimizeMarkdownRequest(BaseModel):
    markdown: str
    asset_map: dict[str, str] | None = None
    model: str | None = None
    base_url: str | None = None
    max_retries: int | None = None
    add_toc: bool = False


class ExportMarkdownZipRequest(BaseModel):
    markdown: str
    asset_map: dict[str, str] | None = None
    markdown_filename: str | None = None
    title: str | None = None


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


def _build_degraded_meta_payload(
    *,
    source_url: str,
    zip_name: str,
    markdown_path: Path,
    image_paths: list[Path],
    cache_html_path: Path,
    from_cache: bool,
    site_name: str | None,
    title: str | None,
    metadata_error: str | None,
) -> dict[str, Any]:
    return {
        "converted_at": datetime.now(timezone.utc).isoformat(),
        "source_url": source_url,
        "site_name": site_name,
        "title": title,
        "author": None,
        "published_at": None,
        "updated_at": None,
        "cache_html_path": str(cache_html_path),
        "from_cache": from_cache,
        "markdown_filename": markdown_path.name,
        "image_count": len(image_paths),
        "zip_name": zip_name,
        "metadata_degraded": True,
        "metadata_error": metadata_error or "unknown metadata error",
    }


def _resolve_zip_name(*, title: str | None, markdown_path: Path) -> str:
    base = _sanitize_filename(title or markdown_path.stem or "article")
    return f"{base}.zip"


def _is_metadata_error(exc: ValueError) -> bool:
    message = str(exc)
    lowered = message.lower()
    return "元信息" in message or "metadata" in lowered


def _convert_without_metadata(*, url: str, output_markdown: Path, cache_dir: Path, timeout: int) -> dict[str, Any]:
    site = select_site(url)
    loader = UrlHtmlCacheLoader(cache_dir=cache_dir, timeout=timeout)
    html, cache_file, from_cache = loader.load(url)

    if site == "cnblogs":
        converter = CnblogsHtmlToMarkdownConverter(timeout=timeout)
    elif site == "wechat":
        converter = WechatHtmlToMarkdownConverter(timeout=timeout)
    else:  # pragma: no cover - guarded by select_site
        raise ValueError(f"未实现站点解析器: {site}")

    title, markdown, image_files = converter.convert_html_with_assets(
        html,
        output_markdown=output_markdown,
        source_url=url,
    )

    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.write_text(markdown, encoding="utf-8")

    return {
        "markdown_path": output_markdown,
        "image_paths": image_files,
        "cache_html_path": cache_file,
        "from_cache": from_cache,
        "site_name": site,
        "title": title,
    }


def _build_asset_map(markdown_path: Path, image_paths: list[Path]) -> dict[str, str]:
    asset_map: dict[str, str] = {}
    for image_path in image_paths:
        if not image_path.exists():
            continue

        try:
            key = image_path.relative_to(markdown_path.parent)
        except ValueError:
            key = Path(image_path.name)

        mime_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        asset_map[str(key).replace("\\", "/")] = f"data:{mime_type};base64,{encoded}"
    return asset_map


def _rewrite_markdown_assets(markdown_text: str, asset_map: dict[str, str] | None = None) -> str:
    if not asset_map:
        return markdown_text

    def _replace_markdown_image(match: re.Match[str]) -> str:
        target = match.group("target").strip()
        replacement = asset_map.get(target)
        if replacement is None:
            return match.group(0)
        return f"![{match.group('alt')}]({replacement})"

    rewritten = MARKDOWN_IMAGE_TOKEN_RE.sub(_replace_markdown_image, markdown_text)

    def _replace_html_media(match: re.Match[str]) -> str:
        target = match.group(2).strip()
        replacement = asset_map.get(target)
        if replacement is None:
            return match.group(0)
        return f"{match.group(1)}{replacement}{match.group(3)}"

    return HTML_MEDIA_SRC_RE.sub(_replace_html_media, rewritten)


def _render_markdown_preview(markdown_text: str, asset_map: dict[str, str] | None = None) -> str:
    rewritten = _rewrite_markdown_assets(markdown_text, asset_map)
    rendered = markdown_lib.markdown(
        rewritten,
        extensions=["fenced_code", "tables", "sane_lists", "nl2br"],
    )
    return bleach.clean(
        rendered,
        tags=PREVIEW_ALLOWED_TAGS,
        attributes=PREVIEW_ALLOWED_ATTRIBUTES,
        protocols=["http", "https", "mailto", "data"],
        strip=True,
    )


def _convert_with_fallback(*, url: str, output_markdown: Path, cache_dir: Path, timeout: int) -> dict[str, Any]:
    metadata_error: str | None = None

    markdown_path: Path
    image_paths: list[Path]
    cache_html_path: Path
    from_cache: bool
    site_name: str | None
    title: str | None
    meta_payload: dict[str, Any]

    try:
        result = convert_url_to_md(
            url=url,
            output=output_markdown,
            cache_dir=cache_dir,
            timeout=timeout,
        )

        markdown_path = result.markdown_path
        image_paths = result.image_paths
        cache_html_path = result.cache_html_path
        from_cache = result.from_cache
        site_name = result.metadata.site_name
        title = result.metadata.title

        zip_name = _resolve_zip_name(title=title, markdown_path=markdown_path)
        try:
            meta_payload = _build_meta_payload(result, source_url=url, zip_name=zip_name)
        except Exception as exc:
            metadata_error = str(exc)
            meta_payload = _build_degraded_meta_payload(
                source_url=url,
                zip_name=zip_name,
                markdown_path=markdown_path,
                image_paths=image_paths,
                cache_html_path=cache_html_path,
                from_cache=from_cache,
                site_name=site_name,
                title=title,
                metadata_error=metadata_error,
            )
    except ValueError as exc:
        if not _is_metadata_error(exc):
            raise

        metadata_error = str(exc)
        fallback = _convert_without_metadata(
            url=url,
            output_markdown=output_markdown,
            cache_dir=cache_dir,
            timeout=timeout,
        )

        markdown_path = fallback["markdown_path"]
        image_paths = fallback["image_paths"]
        cache_html_path = fallback["cache_html_path"]
        from_cache = fallback["from_cache"]
        site_name = fallback["site_name"]
        title = fallback["title"]
        zip_name = _resolve_zip_name(title=title, markdown_path=markdown_path)
        meta_payload = _build_degraded_meta_payload(
            source_url=url,
            zip_name=zip_name,
            markdown_path=markdown_path,
            image_paths=image_paths,
            cache_html_path=cache_html_path,
            from_cache=from_cache,
            site_name=site_name,
            title=title,
            metadata_error=metadata_error,
        )

    markdown_text = markdown_path.read_text(encoding="utf-8")
    asset_map = _build_asset_map(markdown_path, image_paths)

    return {
        "markdown_path": markdown_path,
        "markdown_text": markdown_text,
        "image_paths": image_paths,
        "cache_html_path": cache_html_path,
        "from_cache": from_cache,
        "site_name": site_name,
        "title": title,
        "zip_name": zip_name,
        "metadata": meta_payload,
        "asset_map": asset_map,
    }


def _record_history(item: dict[str, Any]) -> None:
    _insert_history_record(item)


def _init_history_db() -> None:
    HISTORY_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(HISTORY_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversion_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _insert_history_record(item: dict[str, Any]) -> None:
    payload_text = json.dumps(item, ensure_ascii=False)
    created_at = datetime.now(timezone.utc).isoformat()
    with HISTORY_DB_LOCK:
        with sqlite3.connect(HISTORY_DB_PATH) as conn:
            conn.execute(
                "INSERT INTO conversion_history (payload, created_at) VALUES (?, ?)",
                (payload_text, created_at),
            )
            conn.commit()


def _read_history_records(limit: int) -> list[dict[str, Any]]:
    with HISTORY_DB_LOCK:
        with sqlite3.connect(HISTORY_DB_PATH) as conn:
            rows = conn.execute(
                "SELECT payload FROM conversion_history ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row[0])
            if isinstance(payload, dict):
                items.append(payload)
        except Exception:
            continue
    return items


def _clear_history_records_for_tests() -> None:
    _init_history_db()
    with HISTORY_DB_LOCK:
        with sqlite3.connect(HISTORY_DB_PATH) as conn:
            conn.execute("DELETE FROM conversion_history")
            conn.commit()


def _cleanup_cache_files_once() -> int:
    if not CACHE_HTML_DIR.exists():
        return 0

    cutoff = time.time() - (CACHE_RETENTION_DAYS * 24 * 3600)
    removed = 0
    for path in CACHE_HTML_DIR.rglob("*"):
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
        except FileNotFoundError:
            continue
    return removed


def _cache_cleanup_worker() -> None:
    interval_seconds = CACHE_CLEANUP_INTERVAL_HOURS * 3600
    while not _CACHE_CLEANUP_STOP.wait(interval_seconds):
        _cleanup_cache_files_once()


def _start_cache_cleanup_worker() -> None:
    global _CACHE_CLEANUP_THREAD
    if _CACHE_CLEANUP_THREAD is not None and _CACHE_CLEANUP_THREAD.is_alive():
        return

    _CACHE_CLEANUP_STOP.clear()
    _CACHE_CLEANUP_THREAD = threading.Thread(
        target=_cache_cleanup_worker,
        name="cache-cleanup-worker",
        daemon=True,
    )
    _CACHE_CLEANUP_THREAD.start()


def _stop_cache_cleanup_worker() -> None:
    global _CACHE_CLEANUP_THREAD
    _CACHE_CLEANUP_STOP.set()
    if _CACHE_CLEANUP_THREAD is not None:
        _CACHE_CLEANUP_THREAD.join(timeout=2)
    _CACHE_CLEANUP_THREAD = None


def _build_content_disposition(filename: str) -> str:
    # Starlette encodes headers as latin-1, so keep filename= ASCII only.
    fallback = _ascii_fallback_filename(filename)
    encoded = quote(filename, safe="")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"


def _ndjson_line(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


def _normalize_markdown_filename(name: str | None) -> str:
    candidate = (name or "article.md").strip()
    if not candidate:
        candidate = "article.md"
    safe = _sanitize_filename(Path(candidate).name)
    if not safe.lower().endswith(".md"):
        safe = f"{safe}.md"
    return safe


def _safe_zip_asset_path(path_text: str) -> str:
    normalized = str(path_text).replace("\\", "/").strip().lstrip("/")
    parts = [part for part in normalized.split("/") if part and part not in {".", ".."}]
    if not parts:
        return "assets/file.bin"
    return "/".join(parts)


def _decode_data_uri(uri: str) -> bytes | None:
    if not uri.startswith("data:"):
        return None
    marker = ";base64,"
    if marker not in uri:
        return None
    payload = uri.split(marker, 1)[1]
    try:
        return base64.b64decode(payload)
    except Exception:
        return None


def _build_markdown_zip_bytes(
    *,
    markdown_text: str,
    markdown_filename: str,
    asset_map: dict[str, str] | None,
    title: str | None,
) -> tuple[bytes, dict[str, Any], str]:
    image_count = 0
    zip_name = _resolve_zip_name(title=title, markdown_path=Path(markdown_filename))
    buf = BytesIO()

    with ZipFile(buf, "w", compression=ZIP_DEFLATED) as zf:
        zf.writestr(markdown_filename, markdown_text)

        if asset_map:
            for rel_path, data_uri in asset_map.items():
                content = _decode_data_uri(data_uri)
                if content is None:
                    continue
                zf.writestr(_safe_zip_asset_path(rel_path), content)
                image_count += 1

        meta = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "markdown_filename": markdown_filename,
            "image_count": image_count,
            "zip_name": zip_name,
            "title": title,
        }
        zf.writestr("meta.json", json.dumps(meta, ensure_ascii=False, indent=2))

    buf.seek(0)
    return buf.read(), meta, zip_name


def _extract_headings_for_toc(markdown_text: str) -> list[tuple[int, str]]:
    headings: list[tuple[int, str]] = []
    in_fence = False

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        if re.match(r"^\s*```", line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        match = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$", line)
        if not match:
            continue

        level = len(match.group(1))
        if level > 4:
            continue

        title = re.sub(r"\s+#+\s*$", "", match.group(2)).strip()
        if not title:
            continue
        headings.append((level, title))

    if len(headings) >= 2 and headings[0][0] == 1:
        return headings[1:]
    return headings


def _slugify_heading(text: str) -> str:
    slug = text.strip().lower()
    slug = re.sub(r"[`~!@#$%^&*()+=\[\]{}|\\:;\"'<>,.?/]+", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "section"


def _build_toc_markdown(markdown_text: str) -> str | None:
    headings = _extract_headings_for_toc(markdown_text)
    if not headings:
        return None

    min_level = min(level for level, _ in headings)
    slug_counts: dict[str, int] = {}
    lines = ["## 目录"]

    for level, title in headings:
        base_slug = _slugify_heading(title)
        count = slug_counts.get(base_slug, 0)
        slug_counts[base_slug] = count + 1
        slug = base_slug if count == 0 else f"{base_slug}-{count}"

        indent = "  " * max(level - min_level, 0)
        lines.append(f"{indent}- [{title}](#{slug})")

    return "\n".join(lines)


def _prepend_toc(markdown_text: str) -> tuple[str, bool]:
    toc = _build_toc_markdown(markdown_text)
    if not toc:
        return markdown_text, False

    content = markdown_text.lstrip("\n")
    return f"{toc}\n\n{content}", True


@app.get("/api/history")
def history(limit: int = Query(default=10, ge=1, le=MAX_HISTORY)) -> dict[str, list[dict[str, Any]]]:
    items = _read_history_records(limit)
    return {"items": items}



@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    if not INDEX_HTML.exists():
        raise HTTPException(status_code=500, detail="UI template not found")
    return HTMLResponse(INDEX_HTML.read_text(encoding="utf-8"))


@app.post("/api/preview")
def preview(payload: PreviewRequest) -> dict[str, Any]:
    url = payload.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            output_markdown = tmp_path / "article.md"
            artifacts = _convert_with_fallback(
                url=url,
                output_markdown=output_markdown,
                cache_dir=Path("cache") / "html",
                timeout=20,
            )

            return {
                "url": url,
                "markdown": artifacts["markdown_text"],
                "asset_map": artifacts["asset_map"],
                "preview_html": _render_markdown_preview(artifacts["markdown_text"], artifacts["asset_map"]),
                "metadata": artifacts["metadata"],
            }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch remote content: {exc}") from exc
    except Exception as exc:  # pragma: no cover - generic fallback
        raise HTTPException(status_code=500, detail=f"Unexpected preview error: {exc}") from exc


@app.post("/api/render-markdown")
def render_markdown(payload: RenderMarkdownRequest) -> dict[str, str]:
    return {
        "html": _render_markdown_preview(payload.markdown, payload.asset_map),
    }


@app.post("/api/export-markdown-zip")
def export_markdown_zip(payload: ExportMarkdownZipRequest) -> StreamingResponse:
    markdown_text = payload.markdown.strip()
    if not markdown_text:
        raise HTTPException(status_code=400, detail="Markdown is required")

    markdown_filename = _normalize_markdown_filename(payload.markdown_filename)
    zip_bytes, _, zip_name = _build_markdown_zip_bytes(
        markdown_text=payload.markdown,
        markdown_filename=markdown_filename,
        asset_map=payload.asset_map,
        title=payload.title,
    )

    headers = {"Content-Disposition": _build_content_disposition(zip_name)}
    return StreamingResponse(BytesIO(zip_bytes), media_type="application/zip", headers=headers)


@app.post("/api/optimize/stream")
def optimize_markdown_stream(payload: OptimizeMarkdownRequest) -> StreamingResponse:
    markdown = payload.markdown.strip()
    if not markdown:
        raise HTTPException(status_code=400, detail="Markdown is required")

    config = build_formatter_config(
        model_name=payload.model,
        base_url=payload.base_url,
        max_retries=payload.max_retries,
    )

    def _event_stream():
        service = MarkdownFormatterService(config=config)

        try:
            yield _ndjson_line({"type": "status", "message": "开始调用大模型优化 Markdown。"})
            for event in service.stream_format_markdown_content(markdown):
                event_type = event["type"]
                if event_type == "attempt_start":
                    yield _ndjson_line(
                        {
                            "type": "status",
                            "attempt_no": event["attempt_no"],
                            "message": f"第{event['attempt_no']}次生成开始。",
                        }
                    )
                    continue

                if event_type == "chunk":
                    yield _ndjson_line(
                        {
                            "type": "chunk",
                            "attempt_no": event["attempt_no"],
                            "text": event["text"],
                        }
                    )
                    continue

                if event_type == "restored":
                    yield _ndjson_line(
                        {
                            "type": "status",
                            "attempt_no": event["attempt_no"],
                            "message": f"第{event['attempt_no']}次生成已自动回填受保护元素: {', '.join(event['categories'])}",
                        }
                    )
                    continue

                if event_type == "attempt_failed":
                    yield _ndjson_line(
                        {
                            "type": "warning",
                            "attempt_no": event["attempt_no"],
                            "message": event["report"],
                        }
                    )
                    continue

                if event_type == "attempt_warning":
                    yield _ndjson_line(
                        {
                            "type": "warning",
                            "attempt_no": event["attempt_no"],
                            "message": "\n".join(event.get("issues", [])) or "检测到非严重问题，已直接接受本次结果。",
                        }
                    )
                    continue

                if event_type == "complete":
                    optimized_markdown = event["markdown"]
                    toc_applied = False
                    if payload.add_toc:
                        optimized_markdown, toc_applied = _prepend_toc(optimized_markdown)

                    yield _ndjson_line(
                        {
                            "type": "done",
                            "attempt_no": event["attempt_no"],
                            "markdown": optimized_markdown,
                            "restored_categories": event.get("restored_categories", []),
                            "toc_applied": toc_applied,
                            "preview_html": _render_markdown_preview(optimized_markdown, payload.asset_map),
                            "diff_text": build_unified_diff_from_texts(
                                markdown,
                                optimized_markdown,
                                fromfile="before.md",
                                tofile="after.md",
                            ),
                        }
                    )
                    return
        except MarkdownFormatValidationError as exc:
            yield _ndjson_line({"type": "error", "detail": format_validation_report(exc)})
        except Exception as exc:  # pragma: no cover - network/model failure fallback
            yield _ndjson_line({"type": "error", "detail": str(exc)})

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(_event_stream(), media_type="application/x-ndjson", headers=headers)


@app.post("/api/convert")
def convert(payload: ConvertRequest) -> StreamingResponse:
    url = payload.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            output_markdown = tmp_path / "article.md"
            cache_dir = Path("cache") / "html"
            timeout = 20
            artifacts = _convert_with_fallback(
                url=url,
                output_markdown=output_markdown,
                cache_dir=cache_dir,
                timeout=timeout,
            )

            zip_bytes = _build_zip_bytes(artifacts["markdown_path"], artifacts["image_paths"], artifacts["metadata"])
            _record_history(artifacts["metadata"])
    except ValueError as exc:
        # Unsupported domain or parse failures from blog2md.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch remote content: {exc}") from exc
    except Exception as exc:  # pragma: no cover - generic fallback
        raise HTTPException(status_code=500, detail=f"Unexpected conversion error: {exc}") from exc

    content_disposition = _build_content_disposition(artifacts["zip_name"])
    headers = {"Content-Disposition": content_disposition}
    return StreamingResponse(BytesIO(zip_bytes), media_type="application/zip", headers=headers)

