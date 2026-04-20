from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.web.main import app


class WebMainApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_index_contains_preview_and_apply_optimized_actions(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("获取 Markdown 与预览", response.text)
        self.assertIn("apply-optimized-btn", response.text)
        self.assertIn("optimize-add-toc", response.text)

    def test_preview_returns_markdown_metadata_and_inline_asset_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            markdown_path = tmp_path / "article.md"
            image_dir = tmp_path / "article_images"
            image_dir.mkdir(parents=True, exist_ok=True)
            image_path = image_dir / "image_001.png"

            markdown_path.write_text("# Title\n\n![img](article_images/image_001.png)\n", encoding="utf-8")
            image_path.write_bytes(b"fake-image")

            fake_result = SimpleNamespace(
                markdown_path=markdown_path,
                image_paths=[image_path],
                cache_html_path=Path("cache/example.html"),
                from_cache=False,
                metadata=SimpleNamespace(
                    site_name="cnblogs",
                    title="测试标题",
                    author="tester",
                    published_at="2026-04-21",
                    updated_at=None,
                ),
            )

            with patch("src.web.main.convert_url_to_md", return_value=fake_result):
                response = self.client.post("/api/preview", json={"url": "https://www.cnblogs.com/a/p/1.html"})

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["metadata"]["title"], "测试标题")
        self.assertIn("article_images/image_001.png", payload["asset_map"])
        self.assertTrue(payload["asset_map"]["article_images/image_001.png"].startswith("data:image/png;base64,"))
        self.assertIn('<img alt="img"', payload["preview_html"])

    def test_render_markdown_renders_preview_and_strips_unsafe_html(self) -> None:
        response = self.client.post(
            "/api/render-markdown",
            json={
                "markdown": "# Title\n\n![img](article_images/image_001.png)\n\n<script>alert(1)</script>",
                "asset_map": {"article_images/image_001.png": "data:image/png;base64,ZmFrZQ=="},
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        html = response.json()["html"]
        self.assertIn("<h1>Title</h1>", html)
        self.assertIn("data:image/png;base64,ZmFrZQ==", html)
        self.assertNotIn("<script>", html)

    def test_optimize_stream_returns_chunk_and_done_events(self) -> None:
        stream_events = [
            {"type": "attempt_start", "attempt_no": 1},
            {"type": "chunk", "attempt_no": 1, "text": "# Title\n\n"},
            {"type": "chunk", "attempt_no": 1, "text": "content"},
            {
                "type": "complete",
                "attempt_no": 1,
                "markdown": "# Title\n\ncontent",
                "restored_categories": [],
            },
        ]

        with patch("src.web.main.MarkdownFormatterService.stream_format_markdown_content", return_value=iter(stream_events)):
            with self.client.stream(
                "POST",
                "/api/optimize/stream",
                json={
                    "markdown": "Title\ncontent",
                    "asset_map": {},
                    "max_retries": 1,
                },
            ) as response:
                body = "".join(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk for chunk in response.iter_text())

        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in body.splitlines() if line.strip()]
        self.assertTrue(any(event["type"] == "chunk" for event in events))
        done_event = next(event for event in events if event["type"] == "done")
        self.assertEqual(done_event["markdown"], "# Title\n\ncontent")
        self.assertIn("before.md", done_event["diff_text"])
        self.assertIn("<h1>Title</h1>", done_event["preview_html"])

    def test_optimize_stream_can_prepend_toc_when_enabled(self) -> None:
        stream_events = [
            {"type": "attempt_start", "attempt_no": 1},
            {
                "type": "complete",
                "attempt_no": 1,
                "markdown": "# 主标题\n\n## 第一节\n\n内容",
                "restored_categories": [],
            },
        ]

        with patch("src.web.main.MarkdownFormatterService.stream_format_markdown_content", return_value=iter(stream_events)):
            with self.client.stream(
                "POST",
                "/api/optimize/stream",
                json={
                    "markdown": "# 主标题\n\n## 第一节\n\n内容",
                    "asset_map": {},
                    "add_toc": True,
                },
            ) as response:
                body = "".join(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk for chunk in response.iter_text())

        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in body.splitlines() if line.strip()]
        done_event = next(event for event in events if event["type"] == "done")
        self.assertTrue(done_event["toc_applied"])
        self.assertTrue(done_event["markdown"].startswith("## 目录\n- [第一节](#第一节)"))

    def test_optimize_stream_uses_config_builder_defaults(self) -> None:
        stream_events = [
            {"type": "attempt_start", "attempt_no": 1},
            {
                "type": "complete",
                "attempt_no": 1,
                "markdown": "# Title\n\ncontent",
                "restored_categories": [],
            },
        ]

        built_config = SimpleNamespace(model_name="from-toml", base_url="https://example/v1", max_retries=2, api_key="k")
        with patch("src.web.main.build_formatter_config", return_value=built_config) as mock_build:
            with patch("src.web.main.MarkdownFormatterService.stream_format_markdown_content", return_value=iter(stream_events)):
                response = self.client.post(
                    "/api/optimize/stream",
                    json={
                        "markdown": "Title\ncontent",
                        "asset_map": {},
                    },
                )

        self.assertEqual(response.status_code, 200, response.text)
        mock_build.assert_called_once_with(model_name=None, base_url=None, max_retries=None)


if __name__ == "__main__":
    unittest.main()

