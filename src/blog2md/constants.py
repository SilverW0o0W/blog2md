#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""HTML 转 Markdown 过程中共享的常量定义。"""

# 视为块级元素的标签集合，用于控制渲染递归策略。
BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "div",
    "dl",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "ul",
}

# 常见博客正文容器选择器，按优先顺序尝试。
COMMON_CONTENT_SELECTORS = [
    "article",
    "main",
    "[role='main']",
    "#cnblogs_post_body",
    ".post-body",
    ".postBody",
    ".entry-content",
    ".article-content",
    ".content",
]

# 常见页面噪声区域关键词（评论区、页脚、侧边栏等）。
NOISE_KEYWORDS = {
    "comment",
    "footer",
    "header",
    "meta",
    "sidebar",
    "share",
    "advert",
    "subscribe",
    "toc",
    "outline",
    "signature",
    "profile",
    "copyright",
    "disclaimer",
}

# 即使命中噪声关键词，也应优先保留的语义内容标签。
SEMANTIC_CONTENT_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "img", "pre", "code"}

# 直接删除的无关标签。
REMOVABLE_TAGS = ["script", "style", "noscript", "button", "svg", "canvas", "iframe"]

