#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""输入源加载与输出路径处理工具。"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

import requests


class HtmlSourceLoaderTool:
    """从本地文件或远程 URL 加载 HTML 内容。"""

    def load(self, *, input_file: Path | None, url: str | None, timeout: int) -> tuple[str, str | None, Path | None]:
        if input_file:
            return input_file.read_text(encoding="utf-8"), None, input_file

        assert url is not None
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.text, url, None


def sanitize_filename(name: str) -> str:
    sanitized = re.sub(r"[^\w\-.]+", "_", name.strip(), flags=re.UNICODE)
    return sanitized.strip("._") or "output"


def resolve_output_markdown_path(*, input_file: Path | None, url: str | None, output: Path | None) -> Path:
    if output:
        return output.resolve()

    if input_file:
        return (input_file.parent / "md" / f"{input_file.stem}.md").resolve()

    parsed = urlparse(url or "")
    candidate = Path(parsed.path).stem or parsed.netloc or "output"
    filename = sanitize_filename(candidate)
    return (Path.cwd() / "md" / f"{filename}.md").resolve()


def load_html(*, input_file: Path | None, url: str | None, timeout: int) -> tuple[str, str | None, Path | None]:
    return HtmlSourceLoaderTool().load(input_file=input_file, url=url, timeout=timeout)

