#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""图片下载与路径改写工具。"""

from __future__ import annotations

import mimetypes
import os
import shutil
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import Tag


class ImageDownloadTool:
    """下载图片并把 HTML 中图片地址改写为本地相对路径。"""

    def __init__(self, *, timeout: int = 20, assets_dir_name: str | None = None) -> None:
        self.timeout = timeout
        self.assets_dir_name = assets_dir_name

    def download(
        self,
        root: Tag,
        *,
        output_markdown: Path,
        source_url: str | None,
        source_file: Path | None,
    ) -> list[Path]:
        output_dir = output_markdown.parent
        assets_dir_name = self.assets_dir_name or f"{output_markdown.stem}_images"
        assets_dir = output_dir / assets_dir_name
        assets_dir.mkdir(parents=True, exist_ok=True)

        downloaded: list[Path] = []
        seen: dict[str, str] = {}

        for index, img in enumerate(root.find_all("img"), start=1):
            if not isinstance(img, Tag):
                continue

            raw_src = get_image_src(img)
            if not raw_src:
                continue

            resolved = self._resolve_source(raw_src, source_url=source_url, source_file=source_file)
            if not resolved:
                continue

            if resolved in seen:
                img["data-local-src"] = seen[resolved]
                continue

            suffix = self._guess_extension(resolved)
            filename = f"image_{index:03d}{suffix}"
            local_path = assets_dir / filename

            try:
                self._fetch_to_path(resolved, local_path)
            except Exception:
                continue

            rel = os.path.relpath(local_path, output_dir).replace("\\", "/")
            img["data-local-src"] = rel
            seen[resolved] = rel
            downloaded.append(local_path)

        return downloaded

    def _fetch_to_path(self, source: str, target: Path) -> None:
        parsed = urlparse(source)
        if parsed.scheme in {"http", "https"}:
            response = requests.get(source, timeout=self.timeout)
            response.raise_for_status()
            target.write_bytes(response.content)
            return

        file_path = Path(source)
        if not file_path.exists():
            raise FileNotFoundError(source)
        shutil.copyfile(file_path, target)

    def _guess_extension(self, source: str) -> str:
        path = urlparse(source).path
        suffix = Path(path).suffix.lower()
        if suffix and 1 <= len(suffix) <= 6:
            return suffix
        guessed = mimetypes.guess_extension(mimetypes.guess_type(source)[0] or "")
        return guessed or ".img"

    def _resolve_source(self, src: str, *, source_url: str | None, source_file: Path | None) -> str | None:
        parsed = urlparse(src)
        if parsed.scheme in {"http", "https"}:
            return src

        if source_url:
            return urljoin(source_url, src)

        if source_file:
            maybe = (source_file.parent / src).resolve()
            return str(maybe)

        return None


def get_image_src(node: Tag) -> str:
    return (node.get("src") or node.get("data-src") or node.get("data-original") or "").strip()

