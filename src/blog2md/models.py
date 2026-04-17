#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""转换结果数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ConvertResult:
    """一次 HTML 转换产物。"""

    # 渲染后的 Markdown 文本。
    markdown: str
    # 成功下载到本地的图片文件路径列表。
    image_files: list[Path]

