#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""按域名分发站点解析器。"""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urlparse

from .cnblogs_url_to_md import CnblogsConvertResult, convert_cnblogs_url
from .wechat_url_to_md import WechatConvertResult, convert_wechat_url


def _normalize_host(url: str) -> str:
    return urlparse(url).netloc.lower()


def select_site(url: str) -> str:
    host = _normalize_host(url)
    if host.endswith("cnblogs.com"):
        return "cnblogs"
    if host == "mp.weixin.qq.com":
        return "wechat"
    raise ValueError(f"暂不支持该站点: {host}")


def convert_url_to_md(
    *,
    url: str,
    output: Path | None = None,
    cache_dir: Path = Path("cache") / "html",
    timeout: int = 20,
) -> CnblogsConvertResult | WechatConvertResult:
    site = select_site(url)
    if site == "cnblogs":
        return convert_cnblogs_url(
            url=url,
            output=output,
            cache_dir=cache_dir,
            timeout=timeout,
        )
    if site == "wechat":
        return convert_wechat_url(
            url=url,
            output=output,
            cache_dir=cache_dir,
            timeout=timeout,
        )

    raise ValueError(f"未实现站点解析器: {site}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert supported site URLs to Markdown with domain-based routing.")
    parser.add_argument("--url", required=True, help="文章 URL")
    parser.add_argument("-o", "--output", type=Path, help="输出 Markdown 路径")
    parser.add_argument("--cache-dir", type=Path, default=Path("cache") / "html", help="HTML 缓存目录")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP 请求超时时间（秒）")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = convert_url_to_md(
        url=args.url,
        output=args.output,
        cache_dir=args.cache_dir,
        timeout=args.timeout,
    )

    source_desc = (
        f"cache: {result.cache_html_path}"
        if result.from_cache
        else f"fetched and cached: {result.cache_html_path}"
    )
    print(f"Site: {result.metadata.site_name}")
    print(f"Markdown written to: {result.markdown_path}")
    if result.image_paths:
        print(f"Downloaded images: {len(result.image_paths)}")
    print(f"HTML source: {source_desc}")
    print(
        "Meta: "
        f"title={result.metadata.title}, "
        f"author={result.metadata.author}, "
        f"published_at={result.metadata.published_at}, "
        f"updated_at={result.metadata.updated_at}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

