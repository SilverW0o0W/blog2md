#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""博客园定制版：URL 转 Markdown 脚本。

特性：
- 只处理 div.post 内的内容
- 标题来自 h1.postTitle
- 正文来自 div#cnblogs_post_body
- 首次抓取后缓存 HTML，后续直接读取本地缓存
- 复用通用 Markdown 渲染器
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from bs4 import BeautifulSoup, Tag

from .reader_tools.image import ImageDownloadTool
from .reader_tools.markdown import MarkdownRenderTool
from .site_common import PageMeta, SiteConvertResult, UrlHtmlCacheLoader, resolve_output_path_by_title


# 向后兼容旧命名。
CnblogsPageMeta = PageMeta
CnblogsConvertResult = SiteConvertResult


class CnblogsHtmlToMarkdownConverter:
    """博客园页面定制转换器。"""

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
        self.image_downloader = image_downloader or ImageDownloadTool(
            timeout=timeout,
            assets_dir_name=assets_dir_name,
        )

    def convert_html(self, html: str) -> tuple[str, str]:
        # 兼容旧接口：仅输出 Markdown，不下载图片。
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
        post_root = soup.select_one("div.post")
        if not isinstance(post_root, Tag):
            raise ValueError("未找到 div.post，无法定位文章内容")

        title_node = post_root.select_one("h1.postTitle")
        if not isinstance(title_node, Tag):
            raise ValueError("未找到 h1.postTitle，无法定位文章标题")

        body_node = post_root.select_one("div#cnblogs_post_body")
        if not isinstance(body_node, Tag):
            raise ValueError("未找到 div#cnblogs_post_body，无法定位文章正文")

        title = self._extract_title(title_node)
        self._normalize_code_blocks(body_node)

        image_files: list[Path] = []
        if self.download_images and output_markdown is not None:
            image_files = self.image_downloader.download(
                body_node,
                output_markdown=output_markdown,
                source_url=source_url,
                source_file=source_file,
            )

        markdown_body = self.renderer.render(body_node).strip()
        markdown = f"# {title}\n\n{markdown_body}\n"
        return title, markdown, image_files

    def extract_metadata(self, html: str, *, source_url: str) -> CnblogsPageMeta:
        """提取网页元信息，便于上层服务直接使用。"""
        soup = BeautifulSoup(html, "html.parser")
        post_root = soup.select_one("div.post")
        if not isinstance(post_root, Tag):
            raise ValueError("未找到 div.post，无法提取元信息")

        title_node = post_root.select_one("h1.postTitle")
        if not isinstance(title_node, Tag):
            raise ValueError("未找到 h1.postTitle，无法提取元信息")

        title = self._extract_title(title_node)

        post_desc = post_root.select_one("div.postDesc")
        author: str | None = None
        published_at: str | None = None
        updated_at: str | None = None

        if isinstance(post_desc, Tag):
            date_node = post_desc.select_one("span#post-date")
            if isinstance(date_node, Tag):
                published_at = date_node.get_text(strip=True) or None
                updated_at = (date_node.get("data-date-updated") or "").strip() or None

            author_link = post_desc.find("a", href=True)
            if isinstance(author_link, Tag):
                author_text = author_link.get_text(strip=True)
                author = author_text or None

        canonical_url = source_url
        canonical_anchor = post_root.select_one("a#cb_post_title_url")
        if isinstance(canonical_anchor, Tag):
            href = (canonical_anchor.get("href") or "").strip()
            if href:
                canonical_url = href

        return CnblogsPageMeta(
            url=canonical_url,
            title=title,
            author=author,
            published_at=published_at,
            updated_at=updated_at,
            site_name="cnblogs",
        )

    def _extract_title(self, title_node: Tag) -> str:
        # 优先使用 h1.postTitle > a#cb_post_title_url > span 的文本。
        span_node = title_node.select_one("a#cb_post_title_url span") or title_node.select_one("a span")
        if isinstance(span_node, Tag):
            title = span_node.get_text(" ", strip=True)
            title = re.sub(r"\s+", " ", title)
            if title:
                return title

        # 回退：使用标题链接文本。
        anchor = title_node.select_one("a#cb_post_title_url") or title_node.find("a")
        if isinstance(anchor, Tag):
            title = anchor.get_text(" ", strip=True)
            title = re.sub(r"\s+", " ", title)
            if title:
                return title

        # 兜底：清理按钮等噪声后再提取文本。
        title_clone = BeautifulSoup(str(title_node), "html.parser")
        h1_clone = title_clone.find("h1") or title_clone
        for noisy in h1_clone.select("button,script,style"):
            noisy.decompose()

        title = h1_clone.get_text(" ", strip=True)
        title = re.sub(r"\s+", " ", title)
        return title

    def _normalize_code_blocks(self, body_node: Tag) -> None:
        # 站点常见代码容器：内联样式中包含等宽字体；或 class 命中 code/cnblogs_code。
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
        class_hit = any(k in class_text for k in ["code", "cnblogs_code"])

        # 至少有若干换行特征，避免误伤普通布局 div。
        br_count = len(node.find_all("br"))
        return (font_hit or class_hit) and br_count >= 1

    def _extract_code_text(self, node: Tag) -> str:
        clone = BeautifulSoup(str(node), "html.parser")
        for br in clone.find_all("br"):
            br.replace_with("\n")

        text = clone.get_text()
        text = text.replace("\xa0", " ")
        lines = [line.rstrip() for line in text.splitlines()]

        # 去掉首尾空行，保留中间代码结构。
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert a cnblogs URL to Markdown with local HTML cache.")
    parser.add_argument("--url", required=True, help="博客文章 URL")
    parser.add_argument("-o", "--output", type=Path, help="输出 Markdown 路径")
    parser.add_argument("--cache-dir", type=Path, default=Path("cache") / "html", help="HTML 缓存目录")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP 请求超时时间（秒）")
    return parser


def resolve_cnblogs_output_path(*, title: str, output: Path | None) -> Path:
    """根据文章标题生成默认输出路径，或使用显式输出路径。"""
    return resolve_output_path_by_title(title=title, output=output)


def convert_cnblogs_url(
    *,
    url: str,
    output: Path | None = None,
    cache_dir: Path = Path("cache") / "html",
    timeout: int = 20,
) -> CnblogsConvertResult:
    """给 Web 服务使用的统一转换函数。

    输入：博客园 URL
    输出：md 路径、图片路径列表、缓存文件路径、缓存命中状态、网页元信息
    """
    loader = UrlHtmlCacheLoader(cache_dir=cache_dir, timeout=timeout)
    html, cache_file, from_cache = loader.load(url)

    converter = CnblogsHtmlToMarkdownConverter(timeout=timeout)
    metadata = converter.extract_metadata(html, source_url=url)

    output_path = resolve_cnblogs_output_path(title=metadata.title, output=output)
    _, markdown, image_files = converter.convert_html_with_assets(
        html,
        output_markdown=output_path,
        source_url=url,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")

    return CnblogsConvertResult(
        markdown_path=output_path,
        image_paths=image_files,
        cache_html_path=cache_file,
        from_cache=from_cache,
        metadata=metadata,
    )


def main() -> int:
    args = build_parser().parse_args()
    result = convert_cnblogs_url(
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

