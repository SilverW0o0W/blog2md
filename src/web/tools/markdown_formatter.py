from __future__ import annotations

import argparse
import difflib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, cast

try:
    import tomllib  # py>=3.11
except ModuleNotFoundError:  # pragma: no cover - py3.10 fallback
    import tomli as tomllib

DEFAULT_MODEL_NAME = "qwen3.5-plus"
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
ALLOWED_SUFFIXES = {".md", ".markdown"}
OPTIMIZED_SUFFIX = "_llm优化"
ATTEMPT_SUFFIX_TEMPLATE = "_第{attempt_no}次生成"

SYSTEM_PROMPT = (
    "你是一个 Markdown 文档格式优化助手。\n"
    "你的唯一目标是修复 Markdown 文档的结构与排版，让标题、段落、列表和代码块更清晰。\n"
    "你必须严格遵守以下硬性规则：\n"
    "1. 不允许改写、删减、补充、翻译、总结任何原文文字内容。\n"
    "2. 不允许改变原文中各段文字、代码、链接、图片、多媒体元素的先后顺序。\n"
    "3. 只允许添加或调整 Markdown 结构标记，例如：标题 #、空行、列表标记、引用 >、代码块围栏 ```。\n"
    "4. 不允许修改任何图片、超链接、HTML 标签、多媒体标签、URL 或其文本内容。\n"
    "5. 如果代码块因导出损坏而缺少围栏、换行或缩进，可以谨慎修复，但不得改变代码 token 的相对顺序。\n"
    "6. 如果无法确定某一段是否应当是标题或代码块，宁可保持原样，不要猜测性改写。\n"
    "7. 只输出优化后的 Markdown 正文，不要添加解释、前言、后记或外层代码围栏。"
)

FORMAT_PROMPT = """请优化下面 Markdown 文档的格式，并严格遵守系统规则。

<markdown_document>
{content}
</markdown_document>
"""

REPAIR_PROMPT = """你上一次输出没有通过程序校验，原因如下：
{errors}

请重新输出一个合法版本，并严格遵守系统规则。
你只能返回优化后的 Markdown 正文，不要输出解释。

<original_markdown>
{original}
</original_markdown>

<invalid_candidate>
{candidate}
</invalid_candidate>
"""

MARKDOWN_IMAGE_RE = re.compile(r"!\[[^]]*]\([^)]+\)")
MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^]]+]\([^)]+\)")
HTML_MEDIA_RE = re.compile(r"<(?:img|a|video|audio|source)\b[^>]*>", re.IGNORECASE)
RAW_URL_RE = re.compile(r"https?://[^\s<>)]+")
FENCE_LINE_RE = re.compile(r"^\s*```.*$")
CJK_TO_LATIN_SPACE_RE = re.compile(r"([\u4e00-\u9fff])\s+([A-Za-z0-9])")
LATIN_TO_CJK_SPACE_RE = re.compile(r"([A-Za-z0-9])\s+([\u4e00-\u9fff])")
@dataclass(slots=True)
class MarkdownFormatterConfig:
    model_name: str = DEFAULT_MODEL_NAME
    api_key: str | None = None
    base_url: str = DEFAULT_BASE_URL
    enable_thinking: bool = False
    max_retries: int = 1


def _load_toml_file(path: Path) -> dict[str, Any]:
    with path.open("rb") as f:
        data = tomllib.load(f)
    if isinstance(data, dict):
        return data
    return {}


def _extract_llm_section(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    return _extract_named_section(path, data, "llm")


def _extract_named_section(path: Path, data: dict[str, Any], section_name: str) -> dict[str, Any]:
    if path.name == "pyproject.toml":
        tool = data.get("tool")
        if isinstance(tool, dict):
            blog2md = tool.get("blog2md")
            if isinstance(blog2md, dict):
                section = blog2md.get(section_name)
                if isinstance(section, dict):
                    return section
    section = data.get(section_name)
    if isinstance(section, dict):
        return section
    return {}


def resolve_toml_config_path(config_path: str | os.PathLike[str] | None = None) -> Path | None:
    if config_path:
        path = Path(config_path).expanduser().resolve()
        return path if path.exists() else None

    web_config = Path(__file__).resolve().parents[1] / "config.toml"
    if web_config.exists():
        return web_config

    pyproject = Path(__file__).resolve().parents[3] / "pyproject.toml"
    if pyproject.exists():
        return pyproject

    return None


def load_llm_settings_from_toml(config_path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    resolved = resolve_toml_config_path(config_path)
    if resolved is None:
        return {}

    try:
        data = _load_toml_file(resolved)
    except Exception:
        return {}

    return _extract_llm_section(resolved, data)


def load_web_settings_from_toml(config_path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    resolved = resolve_toml_config_path(config_path)
    if resolved is None:
        return {}

    try:
        data = _load_toml_file(resolved)
    except Exception:
        return {}

    return _extract_named_section(resolved, data, "web")


def build_formatter_config(
        *,
        config_path: str | os.PathLike[str] | None = None,
        model_name: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        enable_thinking: bool | None = None,
        max_retries: int | None = None,
) -> MarkdownFormatterConfig:
    settings = load_llm_settings_from_toml(config_path)

    resolved_model = model_name or str(settings.get("model_name") or settings.get("model") or DEFAULT_MODEL_NAME)
    resolved_base_url = base_url or str(settings.get("base_url") or DEFAULT_BASE_URL)

    raw_enable_thinking = settings.get("enable_thinking")
    resolved_enable_thinking = (
        enable_thinking
        if enable_thinking is not None
        else bool(raw_enable_thinking) if isinstance(raw_enable_thinking, bool) else False
    )

    raw_max_retries = settings.get("max_retries")
    if max_retries is not None:
        resolved_max_retries = max_retries
    elif isinstance(raw_max_retries, int):
        resolved_max_retries = raw_max_retries
    else:
        resolved_max_retries = 1

    resolved_api_key = api_key
    if resolved_api_key is None:
        raw_key = settings.get("api_key")
        resolved_api_key = str(raw_key) if isinstance(raw_key, str) and raw_key.strip() else None

    return MarkdownFormatterConfig(
        model_name=resolved_model,
        api_key=resolved_api_key,
        base_url=resolved_base_url,
        enable_thinking=resolved_enable_thinking,
        max_retries=resolved_max_retries,
    )


@dataclass(slots=True)
class ProtectedElementDiff:
    category: str
    index: int
    original: str | None
    candidate: str | None

    def describe(self) -> str:
        return (
            f"类别={self.category}, 索引={self.index}, "
            f"原始值={self.original!r}, 生成值={self.candidate!r}"
        )


class MarkdownFormatValidationError(ValueError):
    """优化结果违反硬性约束时抛出的异常。"""

    def __init__(
            self,
            message: str,
            *,
            issues: list[str] | None = None,
            protected_diffs: list[ProtectedElementDiff] | None = None,
            severe_issues: list[str] | None = None,
            non_severe_issues: list[str] | None = None,
            attempt_no: int | None = None,
            exported_path: str | None = None,
    ) -> None:
        super().__init__(message)
        self.issues = issues or []
        self.protected_diffs = protected_diffs or []
        self.severe_issues = severe_issues or []
        self.non_severe_issues = non_severe_issues or []
        self.attempt_no = attempt_no
        self.exported_path = exported_path

    def with_attempt_context(self, *, attempt_no: int, exported_path: Path) -> "MarkdownFormatValidationError":
        return MarkdownFormatValidationError(
            str(self),
            issues=list(self.issues),
            protected_diffs=list(self.protected_diffs),
            severe_issues=list(self.severe_issues),
            non_severe_issues=list(self.non_severe_issues),
            attempt_no=attempt_no,
            exported_path=str(exported_path),
        )


@dataclass(slots=True)
class ValidationAssessment:
    severe_issues: list[str]
    non_severe_issues: list[str]
    protected_diffs: list[ProtectedElementDiff]


class MarkdownFormatterService:
    """读取 Markdown 并调用大模型做纯格式优化。"""

    def __init__(self, config: MarkdownFormatterConfig | None = None) -> None:
        self.config = config or MarkdownFormatterConfig()
        self._chain = None

    def format_markdown_file(self, md_path: str | os.PathLike[str]) -> str:
        path = Path(md_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Markdown file not found: {path}")
        if path.suffix.lower() not in ALLOWED_SUFFIXES:
            raise ValueError(f"Only Markdown files are supported: {path}")

        content = path.read_text(encoding="utf-8")
        return self.format_markdown_content(content)

    def format_markdown_file_to_path(
            self,
            md_path: str | os.PathLike[str],
            output_path: str | os.PathLike[str] | None = None,
    ) -> Path:
        source_path = Path(md_path).expanduser().resolve()
        if not source_path.exists():
            raise FileNotFoundError(f"Markdown file not found: {source_path}")
        if source_path.suffix.lower() not in ALLOWED_SUFFIXES:
            raise ValueError(f"Only Markdown files are supported: {source_path}")

        original_content = source_path.read_text(encoding="utf-8")
        target_path = build_optimized_markdown_output_path(source_path, output_path=output_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        latest_error: MarkdownFormatValidationError | None = None
        prompt = FORMAT_PROMPT.format(content=original_content)

        for attempt_no in range(1, self.config.max_retries + 2):
            raw_candidate_text = unwrap_markdown_response(self._invoke_model(prompt))
            attempt_path = write_attempt_output(source_path, raw_candidate_text, attempt_no, output_path=target_path)
            print(f"第{attempt_no}次生成已导出到: {attempt_path}")

            candidate_text, restored_categories = restore_protected_elements(original_content, raw_candidate_text)
            if restored_categories:
                print(f"第{attempt_no}次生成已自动回填受保护元素: {', '.join(restored_categories)}")

            try:
                assessment = validate_format_result(original_content, candidate_text, severe_only=True)
            except MarkdownFormatValidationError as error:
                current_error = error.with_attempt_context(attempt_no=attempt_no, exported_path=attempt_path)
                latest_error = current_error
                print(format_validation_report(current_error))
                if attempt_no > self.config.max_retries:
                    raise current_error

                prompt = REPAIR_PROMPT.format(
                    errors=format_validation_report(current_error),
                    original=original_content,
                    candidate=candidate_text,
                )
                continue

            if assessment.non_severe_issues:
                print(format_non_severe_report(assessment, attempt_no=attempt_no))

            target_path.write_text(candidate_text, encoding="utf-8")
            return target_path

        if latest_error is not None:
            raise latest_error

        raise RuntimeError("Markdown formatting failed before any output was produced.")

    def format_markdown_content(self, content: str) -> str:
        candidate = self._invoke_model(FORMAT_PROMPT.format(content=content))
        candidate = unwrap_markdown_response(candidate)
        candidate, _ = restore_protected_elements(content, candidate)

        try:
            assessment = validate_format_result(content, candidate, severe_only=True)
            if assessment.non_severe_issues:
                print(format_non_severe_report(assessment))
            return candidate
        except MarkdownFormatValidationError as error:
            if self.config.max_retries <= 0:
                raise

            repaired = self._invoke_model(
                REPAIR_PROMPT.format(
                    errors=str(error),
                    original=content,
                    candidate=candidate,
                )
            )
            repaired = unwrap_markdown_response(repaired)
            repaired, _ = restore_protected_elements(content, repaired)
            repaired_assessment = validate_format_result(content, repaired, severe_only=True)
            if repaired_assessment.non_severe_issues:
                print(format_non_severe_report(repaired_assessment))
            return repaired

    def stream_format_markdown_content(self, content: str) -> Iterator[dict[str, Any]]:
        prompt = FORMAT_PROMPT.format(content=content)

        for attempt_no in range(1, self.config.max_retries + 2):
            yield {"type": "attempt_start", "attempt_no": attempt_no}

            raw_chunks: list[str] = []
            for chunk in self._stream_model(prompt):
                raw_chunks.append(chunk)
                yield {
                    "type": "chunk",
                    "attempt_no": attempt_no,
                    "text": chunk,
                }

            raw_candidate_text = unwrap_markdown_response("".join(raw_chunks))
            candidate_text, restored_categories = restore_protected_elements(content, raw_candidate_text)
            if restored_categories:
                yield {
                    "type": "restored",
                    "attempt_no": attempt_no,
                    "categories": restored_categories,
                }

            try:
                assessment = validate_format_result(content, candidate_text, severe_only=True)
            except MarkdownFormatValidationError as error:
                current_error = MarkdownFormatValidationError(
                    str(error),
                    issues=list(error.issues),
                    protected_diffs=list(error.protected_diffs),
                    severe_issues=list(error.severe_issues),
                    non_severe_issues=list(error.non_severe_issues),
                    attempt_no=attempt_no,
                )
                yield {
                    "type": "attempt_failed",
                    "attempt_no": attempt_no,
                    "report": format_validation_report(current_error),
                }
                if attempt_no > self.config.max_retries:
                    raise current_error

                prompt = REPAIR_PROMPT.format(
                    errors=format_validation_report(current_error),
                    original=content,
                    candidate=candidate_text,
                )
                continue

            if assessment.non_severe_issues:
                yield {
                    "type": "attempt_warning",
                    "attempt_no": attempt_no,
                    "issues": assessment.non_severe_issues,
                }

            yield {
                "type": "complete",
                "attempt_no": attempt_no,
                "markdown": candidate_text,
                "restored_categories": restored_categories,
                "non_severe_issues": assessment.non_severe_issues,
            }
            return

        raise RuntimeError("Markdown streaming formatting failed before any output was produced.")

    def _invoke_model(self, instruction: str) -> str:
        return self.chain.invoke({"instruction": instruction}).strip()

    def _stream_model(self, instruction: str) -> Iterator[str]:
        for chunk in self.chain.stream({"instruction": instruction}):
            text = str(chunk)
            if text:
                yield text

    @property
    def chain(self):
        if self._chain is None:
            self._chain = self._build_chain()
        return self._chain

    def _build_chain(self):
        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=self.config.model_name,
            api_key=cast(Any, self.config.api_key),
            base_url=self.config.base_url,
            extra_body={"enable_thinking": self.config.enable_thinking},
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM_PROMPT),
                ("human", "{instruction}"),
            ]
        )
        return prompt | llm | StrOutputParser()


def unwrap_markdown_response(text: str) -> str:
    stripped = text.strip()
    wrapped = re.fullmatch(r"```(?:markdown|md)?\s*\n([\s\S]*)\n```", stripped, re.IGNORECASE)
    if wrapped:
        return wrapped.group(1).strip()
    return stripped


def normalize_semantic_text(text: str) -> str:
    normalized_lines: list[str] = []
    for raw_line in text.replace("\r\n", "\n").split("\n"):
        line = raw_line.rstrip()
        if FENCE_LINE_RE.fullmatch(line):
            continue

        line = re.sub(r"^\s{0,3}#{1,6}\s+", "", line)
        line = re.sub(r"^\s{0,3}>\s+", "", line)
        line = re.sub(r"^\s{0,3}[-*+]\s+", "", line)
        line = re.sub(r"^\s{0,3}\d+\.\s+", "", line)

        if line.strip():
            normalized_lines.append(line.strip())

    normalized = "\n".join(normalized_lines)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def normalize_cjk_boundary_spaces(text: str) -> str:
    normalized = CJK_TO_LATIN_SPACE_RE.sub(r"\1\2", text)
    normalized = LATIN_TO_CJK_SPACE_RE.sub(r"\1\2", normalized)
    return normalized


def extract_protected_elements(text: str) -> dict[str, list[str]]:
    return {
        "markdown_images": MARKDOWN_IMAGE_RE.findall(text),
        "markdown_links": MARKDOWN_LINK_RE.findall(text),
        "html_media": HTML_MEDIA_RE.findall(text),
        "raw_urls": RAW_URL_RE.findall(text),
    }


def diff_protected_elements(original: str, candidate: str) -> list[ProtectedElementDiff]:
    original_protected = extract_protected_elements(original)
    candidate_protected = extract_protected_elements(candidate)
    diffs: list[ProtectedElementDiff] = []

    for category, original_values in original_protected.items():
        candidate_values = candidate_protected[category]
        max_len = max(len(original_values), len(candidate_values))
        for index in range(max_len):
            original_value = original_values[index] if index < len(original_values) else None
            candidate_value = candidate_values[index] if index < len(candidate_values) else None
            if original_value != candidate_value:
                diffs.append(
                    ProtectedElementDiff(
                        category=category,
                        index=index,
                        original=original_value,
                        candidate=candidate_value,
                    )
                )

    return diffs


def restore_protected_elements(original: str, candidate: str) -> tuple[str, list[str]]:
    restored_text = candidate
    restored_categories: list[str] = []

    for category, pattern in (
            ("markdown_images", MARKDOWN_IMAGE_RE),
            ("markdown_links", MARKDOWN_LINK_RE),
    ):
        original_items = pattern.findall(original)
        candidate_items = pattern.findall(restored_text)
        if len(original_items) != len(candidate_items):
            continue

        replacement_items: list[str] = []
        has_replacement = False
        for original_item, candidate_item in zip(original_items, candidate_items):
            original_target = _extract_markdown_target(original_item)
            candidate_target = _extract_markdown_target(candidate_item)
            if (
                    original_item != candidate_item
                    and original_target is not None
                    and original_target == candidate_target
            ):
                replacement_items.append(original_item)
                has_replacement = True
            else:
                replacement_items.append(candidate_item)

        if not has_replacement:
            continue

        index = 0

        def _replace(match: re.Match[str]) -> str:
            nonlocal index
            replacement = replacement_items[index]
            index += 1
            return replacement

        updated_text = pattern.sub(_replace, restored_text)
        if updated_text != restored_text:
            restored_categories.append(category)
            restored_text = updated_text

    return restored_text, restored_categories


def _extract_markdown_target(token: str) -> str | None:
    if "](" not in token or not token.endswith(")"):
        return None
    return token.split("](", 1)[1][:-1]


def assess_format_result(original: str, candidate: str) -> ValidationAssessment:
    severe_issues: list[str] = []
    non_severe_issues: list[str] = []
    protected_diffs = diff_protected_elements(original, candidate)

    if not candidate.strip():
        severe_issues.append("模型返回了空结果。")

    if candidate.count("```") % 2 != 0:
        severe_issues.append("代码块围栏数量不是偶数，疑似仍然损坏。")

    if protected_diffs:
        categories = ", ".join(dict.fromkeys(diff.category for diff in protected_diffs))
        non_severe_issues.append(f"受保护元素被修改：{categories}")

    original_semantic = normalize_cjk_boundary_spaces(normalize_semantic_text(original))
    candidate_semantic = normalize_cjk_boundary_spaces(normalize_semantic_text(candidate))
    if original_semantic != candidate_semantic:
        non_severe_issues.append("原文文字内容或顺序发生变化。")

    return ValidationAssessment(
        severe_issues=severe_issues,
        non_severe_issues=non_severe_issues,
        protected_diffs=protected_diffs,
    )


def validate_format_result(original: str, candidate: str, *, severe_only: bool = False) -> ValidationAssessment:
    assessment = assess_format_result(original, candidate)
    errors = list(assessment.severe_issues)
    if not severe_only:
        errors.extend(assessment.non_severe_issues)

    if errors:
        raise MarkdownFormatValidationError(
            "；".join(errors),
            issues=errors,
            protected_diffs=assessment.protected_diffs,
            severe_issues=list(assessment.severe_issues),
            non_severe_issues=list(assessment.non_severe_issues),
        )

    return assessment


def build_optimized_markdown_output_path(
        md_path: str | os.PathLike[str],
        output_path: str | os.PathLike[str] | None = None,
) -> Path:
    source_path = Path(md_path).expanduser().resolve()
    if output_path is not None:
        target_path = Path(output_path).expanduser().resolve()
        if target_path.suffix.lower() != ".md":
            target_path = target_path.with_suffix(".md")
        return target_path

    stem = source_path.stem
    if not stem.endswith(OPTIMIZED_SUFFIX):
        stem = f"{stem}{OPTIMIZED_SUFFIX}"
    return source_path.with_name(f"{stem}.md")


def build_attempt_output_path(
        md_path: str | os.PathLike[str],
        attempt_no: int,
        output_path: str | os.PathLike[str] | None = None,
) -> Path:
    base_output_path = build_optimized_markdown_output_path(md_path, output_path=output_path)
    attempt_suffix = ATTEMPT_SUFFIX_TEMPLATE.format(attempt_no=attempt_no)
    stem = base_output_path.stem
    if not stem.endswith(attempt_suffix):
        stem = f"{stem}{attempt_suffix}"
    return base_output_path.with_name(f"{stem}.md")


def write_attempt_output(
        md_path: str | os.PathLike[str],
        content: str,
        attempt_no: int,
        output_path: str | os.PathLike[str] | None = None,
) -> Path:
    attempt_path = build_attempt_output_path(md_path, attempt_no, output_path=output_path)
    attempt_path.parent.mkdir(parents=True, exist_ok=True)
    attempt_path.write_text(content, encoding="utf-8")
    return attempt_path


def format_validation_report(error: MarkdownFormatValidationError) -> str:
    lines: list[str] = ["Markdown 验证未通过。"]

    if error.attempt_no is not None:
        lines.append(f"尝试次数: 第{error.attempt_no}次生成")
    if error.exported_path is not None:
        lines.append(f"已导出文件: {error.exported_path}")

    if error.issues:
        lines.append("失败原因:")
        lines.extend(f"- {issue}" for issue in error.issues)

    if error.severe_issues:
        lines.append("严重问题:")
        lines.extend(f"- {issue}" for issue in error.severe_issues)

    if error.non_severe_issues:
        lines.append("非严重问题:")
        lines.extend(f"- {issue}" for issue in error.non_severe_issues)

    if error.protected_diffs:
        lines.append("受保护元素差异:")
        lines.extend(f"- {diff.describe()}" for diff in error.protected_diffs)

    return "\n".join(lines)


def format_non_severe_report(assessment: ValidationAssessment, *, attempt_no: int | None = None) -> str:
    if not assessment.non_severe_issues:
        return ""

    lines = ["Markdown 检测到非严重问题，将直接接受本次结果（不重试）。"]
    if attempt_no is not None:
        lines.append(f"尝试次数: 第{attempt_no}次生成")
    lines.append("问题列表:")
    lines.extend(f"- {issue}" for issue in assessment.non_severe_issues)
    return "\n".join(lines)


def build_unified_diff_from_files(
        original_path: str | os.PathLike[str],
        optimized_path: str | os.PathLike[str],
) -> str:
    original = Path(original_path).expanduser().resolve()
    optimized = Path(optimized_path).expanduser().resolve()
    return build_unified_diff_from_texts(
        original.read_text(encoding="utf-8"),
        optimized.read_text(encoding="utf-8"),
        fromfile=str(original),
        tofile=str(optimized),
    )


def build_unified_diff_from_texts(
        original_text: str,
        optimized_text: str,
        *,
        fromfile: str = "original.md",
        tofile: str = "optimized.md",
) -> str:
    original_lines = original_text.splitlines(keepends=True)
    optimized_lines = optimized_text.splitlines(keepends=True)

    diff_lines = difflib.unified_diff(
        original_lines,
        optimized_lines,
        fromfile=fromfile,
        tofile=tofile,
        lineterm="",
    )
    return "\n".join(diff_lines)


def format_markdown_file(
        md_path: str | os.PathLike[str],
        config: MarkdownFormatterConfig | None = None,
        *,
        config_path: str | os.PathLike[str] | None = None,
) -> str:
    service = MarkdownFormatterService(config=config or build_formatter_config(config_path=config_path))
    return service.format_markdown_file(md_path)


def format_markdown_file_to_path(
        md_path: str | os.PathLike[str],
        config: MarkdownFormatterConfig | None = None,
        output_path: str | os.PathLike[str] | None = None,
        *,
        config_path: str | os.PathLike[str] | None = None,
) -> Path:
    service = MarkdownFormatterService(config=config or build_formatter_config(config_path=config_path))
    return service.format_markdown_file_to_path(md_path, output_path=output_path)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Optimize Markdown formatting with LangChain.")
    parser.add_argument("md_path", help="Path to the markdown document.")
    parser.add_argument("-o", "--output", help="Output markdown path. Defaults to original filename + _llm优化.md")
    parser.add_argument("--print-diff", action="store_true",
                        help="Print unified diff of original vs optimized markdown.")
    parser.add_argument("--diff-output", help="Path to save unified diff text.")
    parser.add_argument("--config",
                        help="TOML config path. Defaults: $BLOG2MD_WEB_CONFIG, src/web/config.toml, pyproject.toml")
    parser.add_argument("--model", help="Model name override.")
    parser.add_argument("--base-url", help="OpenAI-compatible API base URL override.")
    parser.add_argument("--max-retries", type=int, help="Validation repair retries override.")
    return parser


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    config = build_formatter_config(
        config_path=args.config,
        model_name=args.model,
        base_url=args.base_url,
        max_retries=args.max_retries,
    )
    output_path = format_markdown_file_to_path(args.md_path, config=config, output_path=args.output)

    if args.print_diff or args.diff_output:
        diff_text = build_unified_diff_from_files(args.md_path, output_path)
        if args.print_diff:
            print(diff_text if diff_text else "(no diff)")
        if args.diff_output:
            diff_path = Path(args.diff_output).expanduser().resolve()
            if diff_path.suffix.lower() != ".diff":
                diff_path = diff_path.with_suffix(".diff")
            diff_path.parent.mkdir(parents=True, exist_ok=True)
            diff_path.write_text(diff_text, encoding="utf-8")
            print(f"diff saved to: {diff_path}")

    print(output_path)


if __name__ == "__main__":
    main()
