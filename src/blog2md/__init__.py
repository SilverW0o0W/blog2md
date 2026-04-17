#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""`html_reader` 对外导出入口。

聚合常用的转换器与工具类，方便在外部按需复用。
"""

from .converter import HtmlToMarkdownConverter
from .cnblogs_url_to_md import convert_cnblogs_url
from .reader_tools.extractor import ContentExtractorTool
from .reader_tools.image import ImageDownloadTool
from .reader_tools.markdown import MarkdownRenderTool
from .models import ConvertResult
from .reader_tools.pathing import HtmlSourceLoaderTool, load_html, resolve_output_markdown_path
from .site_common import PageMeta, SiteConvertResult
from .reader_tools.cache import UrlHtmlCacheLoader
from .site_router import convert_url_to_md, select_site
from .wechat_url_to_md import convert_wechat_url

__all__ = [
    "ContentExtractorTool",
    "ConvertResult",
    "HtmlSourceLoaderTool",
    "HtmlToMarkdownConverter",
    "ImageDownloadTool",
    "MarkdownRenderTool",
    "PageMeta",
    "SiteConvertResult",
    "UrlHtmlCacheLoader",
    "convert_cnblogs_url",
    "convert_url_to_md",
    "convert_wechat_url",
    "load_html",
    "resolve_output_markdown_path",
    "select_site",
]
