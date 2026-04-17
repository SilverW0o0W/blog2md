#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""高层转换编排器。

把提取、图片处理、Markdown 渲染等工具按流程串联起来。
"""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

from .reader_tools.extractor import ContentExtractorTool
from .reader_tools.image import ImageDownloadTool
from .reader_tools.markdown import MarkdownRenderTool
from .models import ConvertResult


class HtmlToMarkdownConverter:
    """组合可复用工具，实现 HTML 到 Markdown 的完整转换。"""

    def __init__(
        self,
        *,
        selector: str | None = None,
        download_images: bool = True,
        assets_dir_name: str | None = None,
        timeout: int = 20,
        extractor: ContentExtractorTool | None = None,
        image_downloader: ImageDownloadTool | None = None,
        renderer: MarkdownRenderTool | None = None,
    ) -> None:
        # 支持外部注入自定义工具，便于扩展或测试替身替换。
        self.download_images = download_images
        self.extractor = extractor or ContentExtractorTool(selector=selector)
        self.image_downloader = image_downloader or ImageDownloadTool(
            timeout=timeout,
            assets_dir_name=assets_dir_name,
        )
        self.renderer = renderer or MarkdownRenderTool()

    def convert(
        self,
        html: str,
        *,
        output_markdown: Path,
        source_url: str | None = None,
        source_file: Path | None = None,
    ) -> ConvertResult:
        # 1) 解析 HTML 2) 提取正文 3) 下载图片并重写路径 4) 渲染 Markdown
        soup = BeautifulSoup(html, "html.parser")
        root = self.extractor.extract(soup)

        image_files: list[Path] = []
        if self.download_images:
            image_files = self.image_downloader.download(
                root,
                output_markdown=output_markdown,
                source_url=source_url,
                source_file=source_file,
            )

        markdown = self.renderer.render(root)
        return ConvertResult(markdown=markdown, image_files=image_files)

