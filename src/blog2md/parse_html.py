#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""HTML 转 Markdown 的命令行入口。

本模块保持原有的公开入口不变，
内部把实际转换工作委托给可复用的工具模块。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .converter import HtmlToMarkdownConverter
from .tools.pathing import load_html, resolve_output_markdown_path


__all__ = ["HtmlToMarkdownConverter", "build_parser", "load_html", "main", "resolve_output_markdown_path"]


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(description="Convert HTML to Markdown and download images.")
    parser.add_argument("-i", "--input", type=Path, help="Path to local HTML file")
    parser.add_argument("--url", help="Input HTML URL")
    parser.add_argument("-o", "--output", type=Path, help="Output Markdown file path")
    parser.add_argument("--selector", help="Optional CSS selector for the main content container")
    parser.add_argument(
        "--assets-dir",
        help="Image directory name relative to the Markdown file directory (default: <md_file_name>_images)",
    )
    parser.add_argument("--timeout", type=int, default=20, help="HTTP request timeout in seconds")
    parser.add_argument(
        "--no-download-images",
        action="store_true",
        help="Do not download images, keep original src URLs",
    )
    return parser


def main() -> int:
    """命令行主流程。

    返回值:
        int: 成功时返回 0。
    """
    parser = build_parser()
    args = parser.parse_args()

    # 至少要提供本地文件或 URL 其中之一。
    if not args.input and not args.url:
        parser.error("One of --input or --url is required.")

    # 解析输入源与输出路径。
    input_file = args.input.resolve() if args.input else None
    output_file = resolve_output_markdown_path(
        input_file=input_file,
        url=args.url,
        output=args.output,
    )

    # 加载 HTML 文本（本地文件或远程 URL）。
    html, source_url, source_file = load_html(
        input_file=input_file,
        url=args.url,
        timeout=args.timeout,
    )

    # 组装转换器并执行转换。
    converter = HtmlToMarkdownConverter(
        selector=args.selector,
        download_images=not args.no_download_images,
        assets_dir_name=args.assets_dir,
        timeout=args.timeout,
    )
    result = converter.convert(
        html,
        output_markdown=output_file,
        source_url=source_url,
        source_file=source_file,
    )

    # 写出 Markdown 文件。
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(result.markdown, encoding="utf-8")

    # 输出简要处理结果。
    print(f"Markdown written to: {output_file}")
    if result.image_files:
        print(f"Downloaded images: {len(result.image_files)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
