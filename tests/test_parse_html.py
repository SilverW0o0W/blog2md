import tempfile
import unittest
from pathlib import Path

from blog2md.converter import HtmlToMarkdownConverter as ModularConverter
from blog2md.tools.extractor import ContentExtractorTool
from blog2md.tools.markdown import MarkdownRenderTool
from blog2md.parse_html import HtmlToMarkdownConverter, resolve_output_markdown_path


class HtmlToMarkdownTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base_dir = Path(__file__).resolve().parent.parent
        self.html_file = self.base_dir / "test.html"
        self.html = self.html_file.read_text(encoding="utf-8")

    def test_convert_preserves_headings(self) -> None:
        converter = HtmlToMarkdownConverter(download_images=False)
        result = converter.convert(
            self.html,
            output_markdown=self.base_dir / "_tmp.md",
            source_file=self.html_file,
        )

        self.assertIn("## python中基于descriptor的一些概念（上）", result.markdown)
        self.assertIn("### 1. 前言", result.markdown)
        self.assertIn("#### 2.1 内置的object对象", result.markdown)

    def test_convert_contains_markdown_image_links(self) -> None:
        converter = HtmlToMarkdownConverter(download_images=False)
        result = converter.convert(
            self.html,
            output_markdown=self.base_dir / "_tmp.md",
            source_file=self.html_file,
        )

        self.assertIn("![](http://images.cnblogs.com", result.markdown)
        self.assertNotIn("<div", result.markdown)

    def test_default_output_path_uses_md_directory_and_source_name(self) -> None:
        output_path = resolve_output_markdown_path(
            input_file=self.html_file,
            url=None,
            output=None,
        )

        self.assertEqual(output_path, self.base_dir / "md" / "test.md")

    def test_default_download_directory_uses_markdown_stem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source_html = tmp_path / "article.html"
            source_image = tmp_path / "image.png"
            output_markdown = tmp_path / "md" / "article.md"

            source_html.write_text("<div><h1>Title</h1><img src='image.png'></div>", encoding="utf-8")
            source_image.write_bytes(b"fake-image-content")

            converter = HtmlToMarkdownConverter(download_images=True)
            result = converter.convert(
                source_html.read_text(encoding="utf-8"),
                output_markdown=output_markdown,
                source_file=source_html,
            )

            expected_dir = output_markdown.parent / "article_images"
            expected_image = expected_dir / "image_001.png"

            self.assertTrue(expected_image.exists())
            self.assertEqual(result.image_files, [expected_image])
            self.assertIn("![](article_images/image_001.png)", result.markdown)

    def test_modular_tools_are_reusable(self) -> None:
        converter = ModularConverter(
            download_images=False,
            extractor=ContentExtractorTool(),
            renderer=MarkdownRenderTool(),
        )
        result = converter.convert(
            self.html,
            output_markdown=self.base_dir / "_tmp.md",
            source_file=self.html_file,
        )

        self.assertTrue(result.markdown.startswith("## python中基于descriptor的一些概念（上）"))


if __name__ == "__main__":
    unittest.main()

