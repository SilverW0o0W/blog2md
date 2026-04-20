from __future__ import annotations

import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.web.main import RECENT_CONVERSIONS, RECENT_CONVERSIONS_LOCK, app


def run_smoke_test() -> None:
    with RECENT_CONVERSIONS_LOCK:
        RECENT_CONVERSIONS.clear()

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
                published_at="2026-04-17",
                updated_at=None,
            ),
        )

        client = TestClient(app)
        with patch("src.web.main.convert_url_to_md", return_value=fake_result):
            response = client.post("/api/convert", json={"url": "https://www.cnblogs.com/a/p/1.html"})

        assert response.status_code == 200, response.text
        assert response.headers.get("content-type", "").startswith("application/zip")
        disposition = response.headers.get("content-disposition", "")
        assert "filename*=UTF-8''" in disposition

        with zipfile.ZipFile(io.BytesIO(response.content), "r") as zf:
            names = set(zf.namelist())
            assert "article.md" in names
            assert "article_images/image_001.png" in names
            assert "meta.json" in names
            meta = json.loads(zf.read("meta.json").decode("utf-8"))
            assert meta["title"] == "测试标题"
            assert meta["source_url"] == "https://www.cnblogs.com/a/p/1.html"

        history_response = client.get("/api/history?limit=5")
        assert history_response.status_code == 200
        items = history_response.json()["items"]
        assert len(items) == 1
        assert items[0]["title"] == "测试标题"

    with RECENT_CONVERSIONS_LOCK:
        RECENT_CONVERSIONS.clear()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        markdown_path = tmp_path / "article.md"
        markdown_path.write_text("# Fallback title\n\nbody\n", encoding="utf-8")

        fallback_result = {
            "markdown_path": markdown_path,
            "image_paths": [],
            "cache_html_path": Path("cache/example_fallback.html"),
            "from_cache": True,
            "site_name": "wechat",
            "title": "Fallback title",
        }

        client = TestClient(app)
        with patch("src.web.main.convert_url_to_md", side_effect=ValueError("未找到元信息")):
            with patch("src.web.main._convert_without_metadata", return_value=fallback_result):
                response = client.post("/api/convert", json={"url": "https://mp.weixin.qq.com/s/demo"})

        assert response.status_code == 200, response.text
        with zipfile.ZipFile(io.BytesIO(response.content), "r") as zf:
            names = set(zf.namelist())
            assert "article.md" in names
            assert "meta.json" in names
            meta = json.loads(zf.read("meta.json").decode("utf-8"))
            assert meta["title"] == "Fallback title"
            assert meta["site_name"] == "wechat"
            assert meta["metadata_degraded"] is True
            assert meta["author"] is None

        history_response = client.get("/api/history?limit=5")
        assert history_response.status_code == 200
        items = history_response.json()["items"]
        assert len(items) == 1
        assert items[0]["metadata_degraded"] is True

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
            from_cache=True,
            metadata=SimpleNamespace(
                site_name="cnblogs",
                title="预览测试",
                author="tester",
                published_at="2026-04-21",
                updated_at=None,
            ),
        )

        client = TestClient(app)
        with patch("src.web.main.convert_url_to_md", return_value=fake_result):
            preview_response = client.post("/api/preview", json={"url": "https://www.cnblogs.com/a/p/2.html"})

        assert preview_response.status_code == 200, preview_response.text
        preview_payload = preview_response.json()
        assert preview_payload["metadata"]["title"] == "预览测试"
        assert "article_images/image_001.png" in preview_payload["asset_map"]
        assert "<img" in preview_payload["preview_html"]

        render_response = client.post(
            "/api/render-markdown",
            json={
                "markdown": "# Preview\n\n![img](article_images/image_001.png)",
                "asset_map": preview_payload["asset_map"],
            },
        )
        assert render_response.status_code == 200, render_response.text
        assert "<h1>Preview</h1>" in render_response.json()["html"]

        stream_events = [
            {"type": "attempt_start", "attempt_no": 1},
            {"type": "chunk", "attempt_no": 1, "text": "# Preview\n\n"},
            {"type": "chunk", "attempt_no": 1, "text": "content"},
            {"type": "complete", "attempt_no": 1, "markdown": "# Preview\n\ncontent", "restored_categories": []},
        ]
        with patch("src.web.main.MarkdownFormatterService.stream_format_markdown_content", return_value=iter(stream_events)):
            with client.stream(
                "POST",
                "/api/optimize/stream",
                json={"markdown": "Preview\ncontent", "asset_map": preview_payload["asset_map"]},
            ) as response:
                body = "".join(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk for chunk in response.iter_text())

        assert response.status_code == 200
        parsed_events = [json.loads(line) for line in body.splitlines() if line.strip()]
        done_event = next(event for event in parsed_events if event["type"] == "done")
        assert done_event["markdown"] == "# Preview\n\ncontent"
        assert "before.md" in done_event["diff_text"]


if __name__ == "__main__":
    run_smoke_test()
    print("web smoke test passed")

