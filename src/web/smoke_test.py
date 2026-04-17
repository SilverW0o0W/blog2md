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

WEB_DIR = Path(__file__).resolve().parent
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from main import RECENT_CONVERSIONS, RECENT_CONVERSIONS_LOCK, app


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
        with patch("main.convert_url_to_md", return_value=fake_result):
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


if __name__ == "__main__":
    run_smoke_test()
    print("web smoke test passed")

