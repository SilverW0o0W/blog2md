import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from blog2md.cnblogs_url_to_md import (
    CnblogsHtmlToMarkdownConverter,
    UrlHtmlCacheLoader,
    convert_cnblogs_url,
    resolve_cnblogs_output_path,
)


class CnblogsCustomConverterTests(unittest.TestCase):
    def test_convert_uses_required_selectors_and_generates_title(self) -> None:
        html = """
        <html><body>
          <div class="post">
            <h1 class="postTitle"><a href="#">示例标题</a></h1>
            <div id="cnblogs_post_body"><p>第一段</p></div>
          </div>
          <div id="cnblogs_post_body"><p>不应解析</p></div>
        </body></html>
        """
        converter = CnblogsHtmlToMarkdownConverter()
        title, markdown = converter.convert_html(html)

        self.assertEqual(title, "示例标题")
        self.assertTrue(markdown.startswith("# 示例标题\n\n"))
        self.assertIn("第一段", markdown)
        self.assertNotIn("不应解析", markdown)

    def test_convert_normalizes_cnblogs_style_code_div_to_fenced_block(self) -> None:
        html = """
        <div class="post">
          <h1 class="postTitle">代码示例</h1>
          <div id="cnblogs_post_body">
            <div style="font-family: Courier New; border: 1px solid #000;">
              <span>print('hello')</span><br>
              <span>print('world')</span>
            </div>
          </div>
        </div>
        """
        converter = CnblogsHtmlToMarkdownConverter()
        _, markdown = converter.convert_html(html)

        self.assertIn("```", markdown)
        self.assertIn("print('hello')", markdown)
        self.assertIn("print('world')", markdown)

    def test_title_extraction_ignores_button_text(self) -> None:
        html = """
        <div class="post">
          <h1 class="postTitle">
            <a id="cb_post_title_url" href="#">scp命令详解</a>
            <button class="cnblogs-toc-button">显示目录导航</button>
          </h1>
          <div id="cnblogs_post_body"><p>body</p></div>
        </div>
        """
        converter = CnblogsHtmlToMarkdownConverter()
        title, markdown = converter.convert_html(html)

        self.assertEqual(title, "scp命令详解")
        self.assertTrue(markdown.startswith("# scp命令详解\n\n"))

    def test_title_extraction_prefers_span_inside_title_anchor(self) -> None:
        html = """
        <div class="post">
          <h1 class="postTitle">
            <a id="cb_post_title_url" href="#">prefix <span role="heading">scp命令详解</span> suffix</a>
          </h1>
          <div id="cnblogs_post_body"><p>body</p></div>
        </div>
        """
        converter = CnblogsHtmlToMarkdownConverter()
        title, markdown = converter.convert_html(html)

        self.assertEqual(title, "scp命令详解")
        self.assertTrue(markdown.startswith("# scp命令详解\n\n"))

    def test_convert_html_with_assets_downloads_images_and_rewrites_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source_img = tmp_path / "img.png"
            source_img.write_bytes(b"fake-image")

            html = f"""
            <div class=\"post\">
              <h1 class=\"postTitle\"><a id=\"cb_post_title_url\"><span>标题A</span></a></h1>
              <div id=\"cnblogs_post_body\">
                <p>图示：</p>
                <img src=\"{source_img.as_posix()}\" alt=\"demo\" />
              </div>
            </div>
            """

            output_markdown = tmp_path / "md" / "标题A.md"
            converter = CnblogsHtmlToMarkdownConverter(download_images=True)
            _, markdown, image_files = converter.convert_html_with_assets(
                html,
                output_markdown=output_markdown,
                source_file=tmp_path / "dummy.html",
            )

            self.assertEqual(len(image_files), 1)
            self.assertTrue(image_files[0].exists())
            self.assertIn("![demo](标题A_images/image_001.png)", markdown)


class UrlHtmlCacheLoaderTests(unittest.TestCase):
    def test_loader_uses_cache_after_first_download(self) -> None:
        url = "https://www.cnblogs.com/likui360/p/6011769.html"
        fake_html = "<html>cached page</html>"

        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_dir = Path(tmp_dir)
            loader = UrlHtmlCacheLoader(cache_dir=cache_dir, timeout=5)

            with patch("blog2md.reader_tools.cache.requests.get") as mocked_get:
                response = Mock()
                response.text = fake_html
                response.raise_for_status = Mock()
                mocked_get.return_value = response

                html1, cache_file1, from_cache1 = loader.load(url)
                html2, cache_file2, from_cache2 = loader.load(url)

            self.assertEqual(html1, fake_html)
            self.assertEqual(html2, fake_html)
            self.assertEqual(cache_file1, cache_file2)
            self.assertEqual(cache_file1.parent.name, "html")
            self.assertEqual(cache_file1.parent.parent.name, "www.cnblogs.com")
            self.assertFalse(from_cache1)
            self.assertTrue(from_cache2)
            self.assertEqual(mocked_get.call_count, 1)


class OutputPathTests(unittest.TestCase):
    def test_default_output_path_uses_title_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with patch("blog2md.cnblogs_url_to_md.Path.cwd", return_value=tmp_path):
                output = resolve_cnblogs_output_path(title="scp命令详解", output=None)

            self.assertEqual(output, (tmp_path / "md" / "scp命令详解.md").resolve())

    def test_output_path_respects_explicit_output_argument(self) -> None:
        explicit = Path("custom") / "manual.md"
        output = resolve_cnblogs_output_path(title="任意标题", output=explicit)
        self.assertEqual(output, explicit.resolve())


class ServiceFunctionTests(unittest.TestCase):
    def test_convert_cnblogs_url_returns_paths_and_metadata(self) -> None:
        url = "https://www.cnblogs.com/demo/p/123456.html"
        html = """
        <html><body>
          <div class="post">
            <h1 class="postTitle">
              <a id="cb_post_title_url" href="https://www.cnblogs.com/demo/p/123456.html">
                <span role="heading">测试标题</span>
              </a>
            </h1>
            <div id="cnblogs_post_body"><p>正文内容</p></div>
            <div class="postDesc">posted @
              <span id="post-date" data-date-updated="2024-01-01 12:00">2024-01-01 11:00</span>
              <a href="https://www.cnblogs.com/demo">demo_author</a>
            </div>
          </div>
        </body></html>
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            cache_dir = tmp_path / "cache"
            output_md = tmp_path / "output.md"

            with patch("blog2md.reader_tools.cache.requests.get") as mocked_get:
                response = Mock()
                response.text = html
                response.raise_for_status = Mock()
                mocked_get.return_value = response

                result = convert_cnblogs_url(
                    url=url,
                    output=output_md,
                    cache_dir=cache_dir,
                    timeout=5,
                )

            self.assertEqual(result.markdown_path, output_md.resolve())
            self.assertTrue(result.markdown_path.exists())
            self.assertEqual(result.image_paths, [])
            self.assertEqual(result.metadata.title, "测试标题")
            self.assertEqual(result.metadata.author, "demo_author")
            self.assertEqual(result.metadata.published_at, "2024-01-01 11:00")
            self.assertEqual(result.metadata.updated_at, "2024-01-01 12:00")
            self.assertEqual(result.metadata.url, url)


if __name__ == "__main__":
    unittest.main()


