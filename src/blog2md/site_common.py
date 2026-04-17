#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""多站点 URL 转 Markdown 的通用能力。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from .reader_tools.cache import UrlHtmlCacheLoader
from .reader_tools.pathing import sanitize_filename


@dataclass
class PageMeta:
    url: str
    title: str
    author: str | None
    published_at: str | None
    updated_at: str | None
    site_name: str


@dataclass
class SiteConvertResult:
    markdown_path: Path
    image_paths: list[Path]
    cache_html_path: Path
    from_cache: bool
    metadata: PageMeta



def resolve_output_path_by_title(*, title: str, output: Path | None) -> Path:
    """默认输出路径：当前目录 md/{标题}.md；显式 output 优先。"""
    if output:
        return output.resolve()

    filename = f"{sanitize_filename(title)}.md"
    return (Path.cwd() / "md" / filename).resolve()

