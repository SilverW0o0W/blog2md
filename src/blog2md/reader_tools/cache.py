#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""URL 缓存工具。"""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlparse

import requests

from .pathing import sanitize_filename


class UrlHtmlCacheLoader:
    """URL HTML 缓存加载器。"""

    def __init__(self, *, cache_dir: Path, timeout: int = 20) -> None:
        self.cache_dir = cache_dir
        self.timeout = timeout
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    def load(self, url: str) -> tuple[str, Path, bool]:
        cache_file = self._cache_file_for_url(url)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        if cache_file.exists():
            return cache_file.read_text(encoding="utf-8"), cache_file, True

        response = requests.get(url, timeout=self.timeout, headers=self._headers)
        response.raise_for_status()
        html = response.text
        cache_file.write_text(html, encoding="utf-8")
        return html, cache_file, False

    def _cache_file_for_url(self, url: str) -> Path:
        parsed = urlparse(url)
        domain_tag = sanitize_filename(parsed.netloc or "unknown-host")
        cache_root = self.cache_dir.parent if self.cache_dir.name == "html" else self.cache_dir
        domain_cache_dir = cache_root / domain_tag / "html"
        stem = sanitize_filename(Path(parsed.path).stem or parsed.netloc or "page")
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
        return domain_cache_dir / f"{stem}_{digest}.html"

