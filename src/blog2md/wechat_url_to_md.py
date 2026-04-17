#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""微信公众号定制版：URL 转 Markdown 脚本。"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from .tools.image import ImageDownloadTool
from .tools.markdown import MarkdownRenderTool
from .site_common import PageMeta, SiteConvertResult, UrlHtmlCacheLoader, resolve_output_path_by_title


WechatPageMeta = PageMeta
WechatConvertResult = SiteConvertResult


class WechatImageDownloadTool(ImageDownloadTool):
    """微信公众号图片下载器，附带反爬所需请求头。"""

    def __init__(self, *, timeout: int = 20, assets_dir_name: str | None = None) -> None:
        super().__init__(timeout=timeout, assets_dir_name=assets_dir_name)
        self._referer: str | None = None
        self._base_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    def download(
        self,
        root: Tag,
        *,
        output_markdown: Path,
        source_url: str | None,
        source_file: Path | None,
    ) -> list[Path]:
        self._referer = source_url
        return super().download(
            root,
            output_markdown=output_markdown,
            source_url=source_url,
            source_file=source_file,
        )

    def _fetch_to_path(self, source: str, target: Path) -> None:
        parsed = urlparse(source)
        if parsed.scheme in {"http", "https"}:
            headers = dict(self._base_headers)
            if self._referer:
                headers["Referer"] = self._referer

            response = requests.get(source, timeout=self.timeout, headers=headers)
            response.raise_for_status()

            content_type = (response.headers.get("Content-Type") or "").lower()
            if content_type.startswith("text/html"):
                raise ValueError(f"微信图片下载命中反爬页面: {source}")

            target.write_bytes(response.content)
            return

        super()._fetch_to_path(source, target)

    def _guess_extension(self, source: str) -> str:
        parsed = urlparse(source)
        query = parse_qs(parsed.query)
        wx_fmt = (query.get("wx_fmt") or [""])[0].lower()
        wx_fmt_map = {
            "jpeg": ".jpg",
            "jpg": ".jpg",
            "png": ".png",
            "gif": ".gif",
            "webp": ".webp",
        }
        if wx_fmt in wx_fmt_map:
            return wx_fmt_map[wx_fmt]

        return super()._guess_extension(source)


class WechatHtmlToMarkdownConverter:
    """微信公众号页面定制转换器。"""

    def __init__(
        self,
        *,
        renderer: MarkdownRenderTool | None = None,
        image_downloader: ImageDownloadTool | None = None,
        download_images: bool = True,
        assets_dir_name: str | None = None,
        timeout: int = 20,
    ) -> None:
        self.renderer = renderer or MarkdownRenderTool()
        self.download_images = download_images
        self.image_downloader = image_downloader or WechatImageDownloadTool(
            timeout=timeout,
            assets_dir_name=assets_dir_name,
        )

    def convert_html(self, html: str) -> tuple[str, str]:
        title, markdown, _ = self.convert_html_with_assets(html)
        return title, markdown

    def convert_html_with_assets(
        self,
        html: str,
        *,
        output_markdown: Path | None = None,
        source_url: str | None = None,
        source_file: Path | None = None,
    ) -> tuple[str, str, list[Path]]:
        soup = BeautifulSoup(html, "html.parser")
        root = soup.select_one("div#img-content")
        if not isinstance(root, Tag):
            raise ValueError("未找到 div#img-content，无法定位文章内容")

        title_node = root.select_one("h1#activity-name")
        if not isinstance(title_node, Tag):
            raise ValueError("未找到 h1#activity-name，无法定位文章标题")

        body_node = root.select_one("div#js_content")
        if not isinstance(body_node, Tag):
            raise ValueError("未找到 div#js_content，无法定位文章正文")

        title = self._extract_title(title_node)
        self._normalize_code_blocks(body_node)

        image_files: list[Path] = []
        if self.download_images and output_markdown is not None:
            self._cleanup_legacy_image_files(output_markdown)
            image_files = self.image_downloader.download(
                body_node,
                output_markdown=output_markdown,
                source_url=source_url,
                source_file=source_file,
            )

        markdown_body = self.renderer.render(body_node).strip()
        markdown = f"# {title}\n\n{markdown_body}\n"
        return title, markdown, image_files

    def extract_metadata(self, html: str, *, source_url: str) -> WechatPageMeta:
        """提取公众号网页元信息。"""
        soup = BeautifulSoup(html, "html.parser")
        root = soup.select_one("div#img-content")
        if not isinstance(root, Tag):
            raise ValueError("未找到 div#img-content，无法提取元信息")

        title_node = root.select_one("h1#activity-name")
        if not isinstance(title_node, Tag):
            raise ValueError("未找到 h1#activity-name，无法提取元信息")

        title = self._extract_title(title_node)

        author_node = root.select_one("#js_name")
        publish_node = root.select_one("#publish_time")

        author = None
        if isinstance(author_node, Tag):
            author = author_node.get_text(strip=True) or None

        published_at = None
        if isinstance(publish_node, Tag):
            published_at = publish_node.get_text(strip=True) or None

        return WechatPageMeta(
            url=source_url,
            title=title,
            author=author,
            published_at=published_at,
            updated_at=None,
            site_name="wechat",
        )

    def _extract_title(self, title_node: Tag) -> str:
        text = title_node.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        return text

    def _cleanup_legacy_image_files(self, output_markdown: Path) -> None:
        """清理历史遗留的 .img 伪图片文件，避免目录中真假图片混杂。"""
        assets_dir_name = self.image_downloader.assets_dir_name or f"{output_markdown.stem}_images"
        assets_dir = output_markdown.parent / assets_dir_name
        if not assets_dir.exists():
            return

        for stale in assets_dir.glob("image_*.img"):
            stale.unlink(missing_ok=True)

    def _normalize_code_blocks(self, body_node: Tag) -> None:
        # 微信文章常见代码容器：等宽字体样式或类名包含 code，且含换行标签。
        for div in list(body_node.find_all("div")):
            if not isinstance(div, Tag):
                continue
            if not self._is_code_div(div):
                continue

            code_text = self._extract_code_text(div)
            if not code_text.strip():
                continue

            pre_soup = BeautifulSoup("<pre></pre>", "html.parser")
            pre = pre_soup.find("pre")
            if not isinstance(pre, Tag):
                continue
            pre.string = code_text.rstrip()
            div.replace_with(pre)

    def _is_code_div(self, node: Tag) -> bool:
        style = (node.get("style") or "").lower()
        class_attr = node.get("class")
        if isinstance(class_attr, list):
            classes = [str(cls).lower() for cls in class_attr]
        elif isinstance(class_attr, str):
            classes = class_attr.lower().split()
        else:
            classes = []
        class_text = " ".join(classes)

        font_hit = any(k in style for k in ["courier", "consolas", "monaco", "font-family"])
        class_hit = "code" in class_text
        br_count = len(node.find_all("br"))
        return (font_hit or class_hit) and br_count >= 1

    def _extract_code_text(self, node: Tag) -> str:
        clone = BeautifulSoup(str(node), "html.parser")
        for br in clone.find_all("br"):
            br.replace_with("\n")

        text = clone.get_text()
        text = text.replace("\xa0", " ")
        lines = [line.rstrip() for line in text.splitlines()]
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        return "\n".join(lines)


def resolve_wechat_output_path(*, title: str, output: Path | None) -> Path:
    return resolve_output_path_by_title(title=title, output=output)


def convert_wechat_url(
    *,
    url: str,
    output: Path | None = None,
    cache_dir: Path = Path("cache") / "html",
    timeout: int = 20,
) -> WechatConvertResult:
    loader = UrlHtmlCacheLoader(cache_dir=cache_dir, timeout=timeout)
    html, cache_file, from_cache = loader.load(url)

    converter = WechatHtmlToMarkdownConverter(timeout=timeout)
    metadata = converter.extract_metadata(html, source_url=url)

    output_path = resolve_wechat_output_path(title=metadata.title, output=output)
    _, markdown, image_files = converter.convert_html_with_assets(
        html,
        output_markdown=output_path,
        source_url=url,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")

    return WechatConvertResult(
        markdown_path=output_path,
        image_paths=image_files,
        cache_html_path=cache_file,
        from_cache=from_cache,
        metadata=metadata,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert a WeChat article URL to Markdown with local HTML cache.")
    parser.add_argument("--url", required=True, help="微信公众号文章 URL")
    parser.add_argument("-o", "--output", type=Path, help="输出 Markdown 路径")
    parser.add_argument("--cache-dir", type=Path, default=Path("cache") / "html", help="HTML 缓存目录")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP 请求超时时间（秒）")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = convert_wechat_url(
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
    print(f"Markdown written to: {result.markdown_path}")
    if result.image_paths:
        print(f"Downloaded images: {len(result.image_paths)}")
    print(f"HTML source: {source_desc}")
    print(f"Meta: title={result.metadata.title}, author={result.metadata.author}, updated_at={result.metadata.updated_at}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

