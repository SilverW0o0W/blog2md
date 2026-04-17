#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""正文提取与噪声清理工具。"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from ..constants import COMMON_CONTENT_SELECTORS, NOISE_KEYWORDS, REMOVABLE_TAGS, SEMANTIC_CONTENT_TAGS


class ContentExtractorTool:
    """从复杂页面中提取最可能的正文区域。"""

    def __init__(self, *, selector: str | None = None) -> None:
        self.selector = selector

    def extract(self, soup: BeautifulSoup) -> Tag:
        root = self._extract_main_content(soup)
        self._remove_noise_nodes(root)
        return root

    def _extract_main_content(self, soup: BeautifulSoup) -> Tag:
        if self.selector:
            selected = soup.select_one(self.selector)
            if isinstance(selected, Tag):
                return selected

        candidates = [node for sel in COMMON_CONTENT_SELECTORS for node in soup.select(sel) if isinstance(node, Tag)]
        if candidates:
            return max(candidates, key=self._score_node)

        body = soup.body or soup
        all_candidates = [node for node in body.find_all(["article", "section", "div", "main"]) if isinstance(node, Tag)]
        if all_candidates:
            best = max(all_candidates, key=self._score_node)
            if self._score_node(best) > 0:
                return best

        return body

    def _score_node(self, node: Tag) -> float:
        text = node.get_text(separator=" ", strip=True)
        text_len = len(text)
        p_count = len(node.find_all("p"))
        heading_count = len(node.find_all(re.compile(r"^h[1-6]$")))
        img_count = len(node.find_all("img"))

        links = node.find_all("a")
        link_text_len = sum(len(a.get_text(separator=" ", strip=True)) for a in links)
        link_density = (link_text_len / text_len) if text_len else 1.0

        return text_len + p_count * 80 + heading_count * 140 + img_count * 30 - link_density * 600

    def _remove_noise_nodes(self, root: Tag) -> None:
        for tag_name in REMOVABLE_TAGS:
            for node in root.find_all(tag_name):
                node.decompose()

        for node in list(root.find_all(True)):
            if getattr(node, "attrs", None) is None:
                continue

            if node.name in SEMANTIC_CONTENT_TAGS:
                continue

            classes = node.get("class")
            class_names = " ".join(classes) if isinstance(classes, list) else (classes or "")
            attrs = " ".join([str(node.get("id", "")), class_names, str(node.get("role", ""))]).lower()
            if any(keyword in attrs for keyword in NOISE_KEYWORDS):
                node.decompose()

