#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""Markdown 渲染工具。"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, NavigableString, Tag

from ..constants import BLOCK_TAGS
from .image import get_image_src


class MarkdownRenderTool:
    """把提取后的 HTML 节点渲染成 Markdown。"""

    def render(self, root: Tag) -> str:
        markdown = self._render_container(root).strip()
        return self._normalize_blank_lines(markdown) + "\n"

    def _render_container(self, root: Tag) -> str:
        parts: list[str] = []
        for child in root.children:
            if isinstance(child, (NavigableString, Tag)):
                rendered = self._render_block(child, level=0)
                if rendered:
                    parts.append(rendered)
        return "".join(parts)

    def _render_block(self, node: NavigableString | Tag, *, level: int) -> str:
        if isinstance(node, NavigableString):
            text = normalize_text(str(node))
            return f"{text}\n\n" if text else ""

        if not isinstance(node, Tag):
            return ""

        name = node.name.lower()

        if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            heading_level = int(name[1])
            text = self._render_inline(node).strip()
            return f"{'#' * heading_level} {text}\n\n" if text else ""

        if name == "p":
            text = self._render_inline(node).strip()
            return f"{text}\n\n" if text else ""

        if name == "div":
            block_children = [c for c in node.children if isinstance(c, Tag) and c.name in BLOCK_TAGS]
            if block_children:
                return "".join(
                    self._render_block(child, level=level)
                    for child in node.children
                    if isinstance(child, (NavigableString, Tag))
                )
            text = self._render_inline(node).strip()
            return f"{text}\n\n" if text else ""

        if name in {"ul", "ol"}:
            return self._render_list(node, level=level, ordered=(name == "ol")) + "\n"

        if name == "blockquote":
            content = self._render_container(node).strip()
            if not content:
                return ""
            quoted = "\n".join(f"> {line}" if line else ">" for line in content.splitlines())
            return f"{quoted}\n\n"

        if name == "pre":
            # Some rich editors keep code line breaks as <br> inside <pre><code>.
            clone = BeautifulSoup(str(node), "html.parser")
            for br in clone.find_all("br"):
                br.replace_with("\n")

            pre_node = clone.find("pre")
            source_node = pre_node if isinstance(pre_node, Tag) else clone
            code = source_node.get_text(separator="", strip=False).replace("\xa0", " ").rstrip()
            if not code:
                return ""
            return f"```\n{code}\n```\n\n"

        if name == "hr":
            return "---\n\n"

        if name == "img":
            return f"{self._render_image(node)}\n\n"

        if name in BLOCK_TAGS:
            return "".join(
                self._render_block(child, level=level)
                for child in node.children
                if isinstance(child, (NavigableString, Tag))
            )

        return self._render_inline(node)

    def _render_list(self, node: Tag, *, level: int, ordered: bool) -> str:
        lines: list[str] = []
        idx = 1
        for li in node.find_all("li", recursive=False):
            if not isinstance(li, Tag):
                continue

            prefix = f"{idx}. " if ordered else "- "
            indent = "  " * level
            text_parts: list[str] = []
            nested_parts: list[str] = []

            for child in li.children:
                if isinstance(child, Tag) and child.name in {"ul", "ol"}:
                    nested_parts.append(self._render_list(child, level=level + 1, ordered=(child.name == "ol")))
                    continue

                if not isinstance(child, (NavigableString, Tag)):
                    continue

                if isinstance(child, Tag) and child.name in BLOCK_TAGS:
                    chunk = self._render_block(child, level=level + 1).strip()
                else:
                    chunk = self._render_inline(child).strip()

                if chunk:
                    text_parts.append(chunk)

            item_text = " ".join(text_parts).strip()
            lines.append(f"{indent}{prefix}{item_text}".rstrip())
            for nested in nested_parts:
                lines.append(nested.rstrip())
            idx += 1

        return "\n".join(line for line in lines if line.strip())

    def _render_inline(self, node: NavigableString | Tag) -> str:
        if isinstance(node, NavigableString):
            return normalize_text(str(node))

        if not isinstance(node, Tag):
            return ""

        name = node.name.lower()

        if name == "br":
            return "  \n"
        if name == "img":
            return self._render_image(node)
        if name == "a":
            text = "".join(self._render_inline(child) for child in node.children if isinstance(child, (NavigableString, Tag))).strip()
            href = (node.get("href") or "").strip()
            if not href or href.startswith("#"):
                return text
            return f"[{text or href}]({href})"
        if name in {"strong", "b"}:
            content = "".join(self._render_inline(child) for child in node.children if isinstance(child, (NavigableString, Tag))).strip()
            return f"**{content}**" if content else ""
        if name in {"em", "i"}:
            content = "".join(self._render_inline(child) for child in node.children if isinstance(child, (NavigableString, Tag))).strip()
            return f"*{content}*" if content else ""
        if name == "code":
            content = node.get_text(separator=" ", strip=True)
            return f"`{content}`" if content else ""

        return "".join(
            self._render_inline(child)
            for child in node.children
            if isinstance(child, (NavigableString, Tag))
        )

    def _render_image(self, node: Tag) -> str:
        src = (node.get("data-local-src") or get_image_src(node) or "").strip()
        alt = (node.get("alt") or "").strip().replace("\n", " ")
        return f"![{alt}]({src})" if src else ""

    def _normalize_blank_lines(self, markdown: str) -> str:
        lines = [line.rstrip() for line in markdown.splitlines()]
        compact: list[str] = []
        empty_count = 0
        for line in lines:
            if not line:
                empty_count += 1
                if empty_count <= 1:
                    compact.append("")
                continue
            empty_count = 0
            compact.append(line)
        return "\n".join(compact).strip()


def normalize_text(text: str) -> str:
    cleaned = text.replace("\xa0", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()

