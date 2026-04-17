import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from blog2md.wechat_url_to_md import WechatHtmlToMarkdownConverter, WechatImageDownloadTool, convert_wechat_url


class WechatConverterTests(unittest.TestCase):
    def test_convert_uses_required_selectors(self) -> None:
        html = """
        <div id="img-content" class="rich_media_wrp">
          <h1 id="activity-name">微信标题</h1>
          <div id="js_content"><p>正文段落</p></div>
        </div>
        """
        converter = WechatHtmlToMarkdownConverter()
        title, markdown = converter.convert_html(html)

        self.assertEqual(title, "微信标题")
        self.assertTrue(markdown.startswith("# 微信标题\n\n"))
        self.assertIn("正文段落", markdown)

    def test_convert_downloads_images_and_rewrites_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source_img = tmp_path / "img.png"
            source_img.write_bytes(b"fake")

            html = f"""
            <div id=\"img-content\" class=\"rich_media_wrp\">
              <h1 id=\"activity-name\">微信标题</h1>
              <div id=\"js_content\"><img src=\"{source_img.as_posix()}\" alt=\"w\" /></div>
            </div>
            """
            output_md = tmp_path / "md" / "微信标题.md"

            converter = WechatHtmlToMarkdownConverter()
            _, markdown, image_files = converter.convert_html_with_assets(
                html,
                output_markdown=output_md,
                source_file=tmp_path / "dummy.html",
            )

            self.assertEqual(len(image_files), 1)
            self.assertTrue(image_files[0].exists())
            self.assertIn("![w](微信标题_images/image_001.png)", markdown)

    def test_convert_wechat_url_returns_metadata(self) -> None:
        url = "https://mp.weixin.qq.com/s/Xs4UFMLs0VsaMrzk0iXoMw"
        html = """
        <div id="img-content" class="rich_media_wrp">
          <h1 id="activity-name">微信文章</h1>
          <div id="meta_content">
            <a id="js_name">公众号作者</a>
            <em id="publish_time">2026-04-17</em>
          </div>
          <div id="js_content"><p>内容</p></div>
        </div>
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with patch("blog2md.reader_tools.cache.requests.get") as mocked_get:
                response = Mock()
                response.text = html
                response.raise_for_status = Mock()
                mocked_get.return_value = response

                result = convert_wechat_url(
                    url=url,
                    output=tmp_path / "wechat.md",
                    cache_dir=tmp_path / "cache",
                    timeout=5,
                )

            self.assertEqual(result.metadata.site_name, "wechat")
            self.assertEqual(result.metadata.title, "微信文章")
            self.assertEqual(result.metadata.author, "公众号作者")
            self.assertEqual(result.metadata.published_at, "2026-04-17")
            self.assertIsNone(result.metadata.updated_at)
            self.assertEqual(result.metadata.url, url)
            self.assertTrue(result.markdown_path.exists())

    def test_wechat_image_download_uses_wx_fmt_extension_and_referer(self) -> None:
        html = """
        <div id="img-content" class="rich_media_wrp">
          <h1 id="activity-name">微信图文</h1>
          <div id="js_content">
            <img src="https://mmbiz.qpic.cn/mmbiz_png/demo/640?wx_fmt=png" alt="a" />
          </div>
        </div>
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            output_md = tmp_path / "md" / "微信图文.md"
            converter = WechatHtmlToMarkdownConverter()

            with patch("blog2md.wechat_url_to_md.requests.get") as mocked_get:
                response = Mock()
                response.raise_for_status = Mock()
                response.content = b"\x89PNG\r\n\x1a\n"
                response.headers = {"Content-Type": "image/png"}
                mocked_get.return_value = response

                _, markdown, image_files = converter.convert_html_with_assets(
                    html,
                    output_markdown=output_md,
                    source_url="https://mp.weixin.qq.com/s/demo",
                )

            self.assertEqual(len(image_files), 1)
            self.assertTrue(image_files[0].name.endswith(".png"))
            self.assertIn("![a](微信图文_images/image_001.png)", markdown)
            self.assertTrue(mocked_get.called)
            called_headers = mocked_get.call_args.kwargs.get("headers", {})
            self.assertEqual(called_headers.get("Referer"), "https://mp.weixin.qq.com/s/demo")

    def test_cleanup_removes_legacy_img_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            output_md = tmp_path / "md" / "微信图文.md"
            legacy_dir = output_md.parent / "微信图文_images"
            legacy_dir.mkdir(parents=True, exist_ok=True)
            legacy_file = legacy_dir / "image_001.img"
            legacy_file.write_bytes(b"not-real")

            converter = WechatHtmlToMarkdownConverter(download_images=True)
            converter._cleanup_legacy_image_files(output_md)

            self.assertFalse(legacy_file.exists())


class WechatImageDownloaderTests(unittest.TestCase):
    def test_guess_extension_prefers_wx_fmt(self) -> None:
        tool = WechatImageDownloadTool()
        ext = tool._guess_extension("https://mmbiz.qpic.cn/demo/0?wx_fmt=jpeg")
        self.assertEqual(ext, ".jpg")


if __name__ == "__main__":
    unittest.main()


