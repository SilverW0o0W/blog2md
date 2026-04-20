# tools 目录说明

## Markdown 格式优化

`markdown_formatter.py` 用于读取 Markdown 文档并通过 LangChain 调用大模型，对文档做**仅限格式层面的修复与增强**。

### 能力边界

- 允许：
  - 调整标题层级（`#`）
  - 增加空行、列表标记、引用标记
  - 尝试补齐损坏的代码块围栏
  - 在不改变原文语义顺序的前提下提升 Markdown 可读性
- 不允许：
  - 改写、删减、补充、翻译原文
  - 修改图片、链接、HTML、多媒体元素
  - 改变文字与代码的原始顺序

### Python 调用

```python
from src.web.tools import build_unified_diff_from_files, format_markdown_file_to_path

output_path = format_markdown_file_to_path("/absolute/path/to/blog.md")
print(output_path)

diff_text = build_unified_diff_from_files("/absolute/path/to/blog.md", output_path)
print(diff_text)
```

### 命令行运行

在仓库根目录执行：

```bash
cd /Users/silver/Documents/GitHub/blog2md
python3 -m src.web.tools.markdown_formatter /absolute/path/to/blog.md
```

默认会在原文件同目录下生成：`原文件名_llm优化.md`

每一次模型生成也会单独保留为尝试文件，例如：

- `原文件名_llm优化_第1次生成.md`
- `原文件名_llm优化_第2次生成.md`

也可以显式指定输出路径：

```bash
cd /Users/silver/Documents/GitHub/blog2md
python3 -m src.web.tools.markdown_formatter /absolute/path/to/blog.md -o /absolute/path/to/output.md
```

比较原文件与优化结果：

```bash
cd /Users/silver/Documents/GitHub/blog2md
python3 -m src.web.tools.markdown_formatter /absolute/path/to/blog.md --print-diff
```

保存 diff 到文件：

```bash
cd /Users/silver/Documents/GitHub/blog2md
python3 -m src.web.tools.markdown_formatter /absolute/path/to/blog.md --diff-output /absolute/path/to/blog_changes.diff
```

### 依赖与环境变量

先安装 Web 子项目依赖（包含 LangChain）：

```bash
cd /Users/silver/Documents/GitHub/blog2md
python3 -m pip install -r src/web/requirements.txt
```

配置文件默认读取顺序：

1. `--config /path/to/config.toml`
2. 环境变量 `$BLOG2MD_WEB_CONFIG` 指向的 TOML
3. `src/web/config.toml`
4. `pyproject.toml` 的 `[tool.blog2md.llm]`

推荐先复制示例：

```bash
cd /Users/silver/Documents/GitHub/blog2md
cp src/web/config.example.toml src/web/config.toml
```

在 TOML 中设置：

```toml
[llm]
model_name = "qwen3.5-plus"
base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
api_key = "your_dashscope_api_key"
max_retries = 1
```

仍可用环境变量兜底：

```bash
export DASHSCOPE_API_KEY="your_api_key"
```

### 说明

- 模块会先让模型输出格式优化后的 Markdown。
- 默认会把结果写入原文件名加 `_llm优化` 的 `.md` 文件。
- 每次生成结果都会单独落盘，验证失败时不会丢弃失败版本。
- 在最终校验前，会先自动回填链接/图片中目标 URL 未变化但文本发生漂移的片段，避免无意义的空格变化。
- 然后做一次本地校验：
  - 原文语义文本是否保持一致
  - 图片、链接、多媒体、URL 是否被改动
  - 代码块围栏是否成对
- 如果输出未通过校验，会打印详细失败原因；当受保护元素被修改时，会输出对应元素的原始值与生成值。
- 如果首次输出未通过校验，会自动再请求模型修复一次。
