import importlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

# Ensure project root is importable when this file is run directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

formatter = importlib.import_module("src.web.tools.markdown_formatter")


class MarkdownFormatterValidationTests(unittest.TestCase):
    def test_unwrap_outer_markdown_fence(self) -> None:
        wrapped = "```markdown\n# Title\ncontent\n```"
        self.assertEqual(formatter.unwrap_markdown_response(wrapped), "# Title\ncontent")

    def test_normalize_semantic_text_ignores_heading_and_fences(self) -> None:
        original = "Title\nprint('hello')"
        candidate = "# Title\n```python\nprint('hello')\n```"
        self.assertEqual(formatter.normalize_semantic_text(original), formatter.normalize_semantic_text(candidate))

    def test_extract_protected_elements_keeps_links_images_and_urls(self) -> None:
        text = (
            "![img](https://example.com/a.png)\n"
            "[link](https://example.com)\n"
            "<img src=\"https://example.com/b.png\">\n"
            "https://example.com/raw"
        )
        protected = formatter.extract_protected_elements(text)
        self.assertEqual(protected["markdown_images"], ["![img](https://example.com/a.png)"])
        self.assertEqual(protected["markdown_links"], ["[link](https://example.com)"])
        self.assertEqual(protected["html_media"], ['<img src="https://example.com/b.png">'])
        self.assertEqual(
            protected["raw_urls"],
            [
                "https://example.com/a.png",
                "https://example.com",
                'https://example.com/b.png\"',
                "https://example.com/raw",
            ],
        )

    def test_validate_accepts_format_only_changes(self) -> None:
        original = "Title\nParagraph line\nprint('hello')"
        candidate = "# Title\n\nParagraph line\n\n```python\nprint('hello')\n```"
        formatter.validate_format_result(original, candidate)

    def test_validate_rejects_changed_text(self) -> None:
        original = "Title\nParagraph line"
        candidate = "# Title\n\nParagraph line updated"
        with self.assertRaises(formatter.MarkdownFormatValidationError):
            formatter.validate_format_result(original, candidate)

    def test_validate_rejects_changed_link(self) -> None:
        original = "[link](https://example.com)"
        candidate = "[link](https://changed.example.com)"
        with self.assertRaises(formatter.MarkdownFormatValidationError) as context:
            formatter.validate_format_result(original, candidate)

        error = context.exception
        self.assertTrue(error.protected_diffs)
        self.assertEqual(error.protected_diffs[0].category, "markdown_links")
        self.assertEqual(error.protected_diffs[0].original, "[link](https://example.com)")
        self.assertEqual(error.protected_diffs[0].candidate, "[link](https://changed.example.com)")

    def test_restore_protected_elements_fixes_ssh_link_text_spacing(self) -> None:
        original = "[ssh免密码登录](http://www.cnblogs.com/likui360/p/6012035.html)"
        candidate = "[ssh 免密码登录](http://www.cnblogs.com/likui360/p/6012035.html)"
        restored, categories = formatter.restore_protected_elements(original, candidate)
        self.assertEqual(restored, original)
        self.assertIn("markdown_links", categories)

    def test_validate_accepts_cjk_boundary_spacing_changes(self) -> None:
        original = "这是Python3教程"
        candidate = "这是 Python3 教程"
        formatter.validate_format_result(original, candidate)

    def test_build_optimized_markdown_output_path_uses_original_name_plus_suffix(self) -> None:
        source = "/tmp/blog-post.markdown"
        target = formatter.build_optimized_markdown_output_path(source)
        self.assertEqual(target, Path(source).resolve().with_name("blog-post_llm优化.md"))

    def test_build_optimized_markdown_output_path_does_not_duplicate_suffix(self) -> None:
        source = "/tmp/blog-post_llm优化.md"
        target = formatter.build_optimized_markdown_output_path(source)
        self.assertEqual(target, Path(source).resolve().with_name("blog-post_llm优化.md"))

    def test_build_attempt_output_path_appends_attempt_suffix(self) -> None:
        source = "/tmp/blog-post.md"
        target = formatter.build_attempt_output_path(source, attempt_no=2)
        self.assertEqual(target, Path(source).resolve().with_name("blog-post_llm优化_第2次生成.md"))

    def test_format_validation_report_contains_diff_details(self) -> None:
        error = formatter.MarkdownFormatValidationError(
            "受保护元素被修改：markdown_links",
            issues=["受保护元素被修改：markdown_links"],
            protected_diffs=[
                formatter.ProtectedElementDiff(
                    category="markdown_links",
                    index=0,
                    original="[link](https://example.com)",
                    candidate="[link](https://changed.example.com)",
                )
            ],
            attempt_no=1,
            exported_path="/tmp/blog_llm优化_第1次生成.md",
        )

        report = formatter.format_validation_report(error)
        self.assertIn("第1次生成", report)
        self.assertIn("受保护元素差异", report)
        self.assertIn("原始值='[link](https://example.com)'", report)
        self.assertIn("生成值='[link](https://changed.example.com)'", report)

    def test_build_unified_diff_from_files_contains_expected_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            original = Path(tmp_dir) / "origin.md"
            optimized = Path(tmp_dir) / "origin_llm优化.md"
            original.write_text("line1\nline2\n", encoding="utf-8")
            optimized.write_text("line1\nline2 changed\n", encoding="utf-8")

            diff_text = formatter.build_unified_diff_from_files(original, optimized)
            self.assertIn(str(original.resolve()), diff_text)
            self.assertIn(str(optimized.resolve()), diff_text)
            self.assertIn("-line2", diff_text)
            self.assertIn("+line2 changed", diff_text)

    def test_build_unified_diff_from_files_returns_empty_when_no_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            original = Path(tmp_dir) / "origin.md"
            optimized = Path(tmp_dir) / "origin_llm优化.md"
            original.write_text("same\n", encoding="utf-8")
            optimized.write_text("same\n", encoding="utf-8")

            diff_text = formatter.build_unified_diff_from_files(original, optimized)
            self.assertEqual(diff_text, "")

    def test_build_unified_diff_from_texts_contains_expected_changes(self) -> None:
        diff_text = formatter.build_unified_diff_from_texts(
            "line1\nline2\n",
            "line1\nline2 changed\n",
            fromfile="before.md",
            tofile="after.md",
        )
        self.assertIn("before.md", diff_text)
        self.assertIn("after.md", diff_text)
        self.assertIn("-line2", diff_text)
        self.assertIn("+line2 changed", diff_text)

    def test_argument_parser_accepts_diff_options(self) -> None:
        parser = formatter.build_argument_parser()
        args = parser.parse_args(["/tmp/a.md", "--print-diff", "--diff-output", "/tmp/change"])
        self.assertTrue(args.print_diff)
        self.assertEqual(args.diff_output, "/tmp/change")

    def test_build_formatter_config_loads_model_and_key_from_toml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.toml"
            config_path.write_text(
                """
[llm]
model_name = "qwen-test"
base_url = "https://example.test/v1"
api_key = "toml-key"
max_retries = 3
enable_thinking = true
""".strip(),
                encoding="utf-8",
            )

            config = formatter.build_formatter_config(config_path=config_path)

            self.assertEqual(config.model_name, "qwen-test")
            self.assertEqual(config.base_url, "https://example.test/v1")
            self.assertEqual(config.api_key, "toml-key")
            self.assertEqual(config.max_retries, 3)
            self.assertTrue(config.enable_thinking)

    def test_build_formatter_config_allows_cli_override_over_toml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.toml"
            config_path.write_text(
                """
[llm]
model_name = "qwen-from-toml"
base_url = "https://toml.example/v1"
api_key = "toml-key"
max_retries = 5
""".strip(),
                encoding="utf-8",
            )

            config = formatter.build_formatter_config(
                config_path=config_path,
                model_name="qwen-from-arg",
                max_retries=1,
            )

            self.assertEqual(config.model_name, "qwen-from-arg")
            self.assertEqual(config.max_retries, 1)
            self.assertEqual(config.base_url, "https://toml.example/v1")
            self.assertEqual(config.api_key, "toml-key")

    def test_format_markdown_file_to_path_writes_optimized_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "article.md"
            source.write_text("original content", encoding="utf-8")

            service = formatter.MarkdownFormatterService(
                config=formatter.MarkdownFormatterConfig(max_retries=0)
            )
            with mock.patch.object(service, "_invoke_model", return_value="# original content"):
                output_path = service.format_markdown_file_to_path(source)

            self.assertEqual(output_path, source.resolve().with_name("article_llm优化.md"))
            self.assertTrue(output_path.exists())
            self.assertEqual(output_path.read_text(encoding="utf-8"), "# original content")
            self.assertTrue(source.resolve().with_name("article_llm优化_第1次生成.md").exists())

    def test_format_markdown_file_to_path_respects_custom_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "article.md"
            source.write_text("original content", encoding="utf-8")
            custom_output = Path(tmp_dir) / "nested" / "result"

            service = formatter.MarkdownFormatterService(
                config=formatter.MarkdownFormatterConfig(max_retries=0)
            )
            with mock.patch.object(service, "_invoke_model", return_value="# original content"):
                output_path = service.format_markdown_file_to_path(source, output_path=custom_output)

            self.assertEqual(output_path, custom_output.resolve().with_suffix(".md"))
            self.assertTrue(output_path.exists())
            self.assertTrue(custom_output.resolve().with_name("result_第1次生成.md").with_suffix(".md").exists())

    def test_format_markdown_file_to_path_accepts_non_severe_issue_without_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "article.md"
            source.write_text("[link](https://example.com)", encoding="utf-8")
            service = formatter.MarkdownFormatterService(
                config=formatter.MarkdownFormatterConfig(max_retries=0)
            )

            with mock.patch.object(service, "_invoke_model", return_value="[link](https://changed.example.com)"), \
                    mock.patch("builtins.print") as mock_print:
                output_path = service.format_markdown_file_to_path(source)

            failed_attempt = source.resolve().with_name("article_llm优化_第1次生成.md")
            self.assertTrue(failed_attempt.exists())
            self.assertEqual(failed_attempt.read_text(encoding="utf-8"), "[link](https://changed.example.com)")
            self.assertEqual(output_path.read_text(encoding="utf-8"), "[link](https://changed.example.com)")

            printed_output = "\n".join(" ".join(map(str, call.args)) for call in mock_print.call_args_list)
            self.assertIn("非严重问题", printed_output)
            self.assertIn("将直接接受本次结果", printed_output)

    def test_format_markdown_file_to_path_restores_link_text_spacing_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "article.md"
            source.write_text(
                "[ssh免密码登录](http://www.cnblogs.com/likui360/p/6012035.html)",
                encoding="utf-8",
            )
            service = formatter.MarkdownFormatterService(
                config=formatter.MarkdownFormatterConfig(max_retries=0)
            )

            with mock.patch.object(
                service,
                "_invoke_model",
                return_value="[ssh 免密码登录](http://www.cnblogs.com/likui360/p/6012035.html)",
            ), mock.patch("builtins.print") as mock_print:
                output_path = service.format_markdown_file_to_path(source)

            self.assertEqual(
                output_path.read_text(encoding="utf-8"),
                "[ssh免密码登录](http://www.cnblogs.com/likui360/p/6012035.html)",
            )
            printed_output = "\n".join(" ".join(map(str, call.args)) for call in mock_print.call_args_list)
            self.assertIn("已自动回填受保护元素: markdown_links", printed_output)

    def test_format_markdown_file_to_path_non_severe_issue_keeps_first_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "article.md"
            source.write_text("Title\ncontent", encoding="utf-8")
            service = formatter.MarkdownFormatterService(
                config=formatter.MarkdownFormatterConfig(max_retries=1)
            )

            with mock.patch.object(
                service,
                "_invoke_model",
                side_effect=["Title changed", "# Title\n\ncontent"],
            ), mock.patch("builtins.print"):
                output_path = service.format_markdown_file_to_path(source)

            first_attempt = source.resolve().with_name("article_llm优化_第1次生成.md")
            second_attempt = source.resolve().with_name("article_llm优化_第2次生成.md")
            self.assertTrue(first_attempt.exists())
            self.assertFalse(second_attempt.exists())
            self.assertEqual(first_attempt.read_text(encoding="utf-8"), "Title changed")
            self.assertEqual(output_path.read_text(encoding="utf-8"), "Title changed")

    def test_format_markdown_file_to_path_retry_on_severe_issue_then_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "article.md"
            source.write_text("Title\ncontent", encoding="utf-8")
            service = formatter.MarkdownFormatterService(
                config=formatter.MarkdownFormatterConfig(max_retries=1)
            )

            with mock.patch.object(
                service,
                "_invoke_model",
                side_effect=["```python\nprint('oops')", "# Title\n\ncontent"],
            ), mock.patch("builtins.print"):
                output_path = service.format_markdown_file_to_path(source)

            first_attempt = source.resolve().with_name("article_llm优化_第1次生成.md")
            second_attempt = source.resolve().with_name("article_llm优化_第2次生成.md")
            self.assertTrue(first_attempt.exists())
            self.assertTrue(second_attempt.exists())
            self.assertEqual(second_attempt.read_text(encoding="utf-8"), "# Title\n\ncontent")
            self.assertEqual(output_path.read_text(encoding="utf-8"), "# Title\n\ncontent")

    def test_stream_format_markdown_content_yields_chunk_and_complete_events(self) -> None:
        service = formatter.MarkdownFormatterService(
            config=formatter.MarkdownFormatterConfig(max_retries=0)
        )

        with mock.patch.object(service, "_stream_model", return_value=iter(["# Title\n\n", "content"])):
            events = list(service.stream_format_markdown_content("Title\ncontent"))

        self.assertEqual(events[0]["type"], "attempt_start")
        self.assertEqual(events[1]["type"], "chunk")
        self.assertEqual(events[2]["type"], "chunk")
        self.assertEqual(events[-1]["type"], "complete")
        self.assertEqual(events[-1]["markdown"], "# Title\n\ncontent")

    def test_stream_format_markdown_content_emits_warning_for_non_severe_issue(self) -> None:
        service = formatter.MarkdownFormatterService(
            config=formatter.MarkdownFormatterConfig(max_retries=0)
        )

        with mock.patch.object(service, "_stream_model", return_value=iter(["Title changed"])):
            events = list(service.stream_format_markdown_content("Title\ncontent"))

        self.assertTrue(any(event["type"] == "attempt_warning" for event in events))
        self.assertEqual(events[-1]["type"], "complete")


if __name__ == "__main__":
    unittest.main()

