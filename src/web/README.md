# web (FastAPI)

这个目录是一个独立可拆分的 Web 子项目。

目标：在网页输入博客园/微信公众号 URL，调用 `blog2md` 转换，并支持：

- 下载包含 Markdown + 图片资源的 ZIP
- 先预览原始 Markdown
- 再调用大模型对 Markdown 做流式格式优化
- 在优化前后都查看 Markdown 渲染预览

当前 UI 还提供最近转换记录面板（进程内内存，最多保留 20 条）。

## 目录

- `main.py`: FastAPI 应用入口
- `templates/index.html`: 简易 UI 页面
- `requirements.txt`: Web 子项目依赖

## 运行

先在仓库根目录安装 `blog2md` 本体（如果还没安装）：

```bash
python3 -m pip install -e .
```

再安装 web 依赖：

```bash
python3 -m pip install -r src/web/requirements.txt
```

配置 LLM（模型、base_url、api_key）：

```bash
cp src/web/config.example.toml src/web/config.toml
```

编辑 `src/web/config.toml`，填写 `llm.api_key` 等字段。

启动：

```bash
uvicorn src.web.main:app --reload --host 0.0.0.0 --port 8000
```


浏览器访问：`http://127.0.0.1:8000`

### 推荐交互流程

1. 在首页输入文章 URL
2. 点击“获取 Markdown 与预览”
3. 在左侧查看原始 Markdown 源码 / 预览
4. 如有需要，可直接修改原始 Markdown
5. 点击“开始 LLM 优化”，右侧以流式方式显示模型输出
6. 若中途停止，页面会保留已生成的部分结果，可继续预览 / 下载
7. 优化完成后查看优化稿预览和 diff
8. 可选勾选“将标题整理为目录并放到优化稿最前方”
9. 如结果满意，可点击“将优化稿应用为原稿”，再基于新原稿继续优化
10. 按需下载 ZIP、原稿 `.md` 或优化稿 `.md`

## API

### `POST /api/preview`

根据 URL 生成原始 Markdown，并返回可直接用于前端预览的数据。

请求体（JSON）：

```json
{
  "url": "https://www.cnblogs.com/likui360/p/6011769.html"
}
```

响应字段：

- `markdown`: 原始 Markdown 文本
- `asset_map`: 本地图片路径到 data URI 的映射，用于预览
- `preview_html`: 原始 Markdown 的渲染结果
- `metadata`: 文章元信息

### `POST /api/render-markdown`

把任意 Markdown 渲染成预览 HTML。适合前端在“源码/预览”切换时调用。

请求体（JSON）：

```json
{
  "markdown": "# Title\n\ncontent",
  "asset_map": {
    "article_images/image_001.png": "data:image/png;base64,..."
  }
}
```

### `POST /api/optimize/stream`

流式调用 LLM 优化 Markdown。返回 `application/x-ndjson`，每行一个 JSON 事件。

常见事件类型：

- `status`: 状态提示（开始生成、回填保护元素等）
- `chunk`: 模型流式输出片段
- `warning`: 某次生成未通过校验，准备重试
- `done`: 最终优化完成，包含 `markdown`、`preview_html`、`diff_text`
- `error`: 优化失败

前端会把 `diff_text` 渲染为带颜色的 unified diff，便于快速查看格式调整位置。

请求体（JSON）：

```json
{
  "markdown": "Title\ncontent",
  "asset_map": {},
  "model": null,
  "base_url": null,
  "max_retries": null,
  "add_toc": false
}
```

- `add_toc=true` 时，会根据优化稿中的标题自动生成目录并插入到最前方。
- `model/base_url/max_retries` 为空时，默认使用 TOML 配置值。

### `POST /api/convert`

请求体（JSON）：

```json
{
  "url": "https://www.cnblogs.com/likui360/p/6011769.html"
}
```

响应：`application/zip`

- 包含转换后的 `.md`
- 包含 markdown 里引用的本地图片文件
- 包含 `meta.json`（来源 URL、标题、作者、站点、图片数量、缓存信息等）
- `meta.json` 为 best-effort：元信息提取失败时会降级为可用的空字段，不影响 ZIP 下载

### `GET /api/history`

返回最近转换记录（最新优先）。

查询参数：

- `limit`（可选，默认 10，最大 20）

响应示例：

```json
{
  "items": [
    {
      "converted_at": "2026-04-17T11:22:33.000000+00:00",
      "source_url": "https://www.cnblogs.com/likui360/p/6011769.html",
      "site_name": "cnblogs",
      "title": "scp命令详解",
      "author": "扫地猿",
      "published_at": "2016-10-29 20:51",
      "updated_at": "2016-10-29 23:16",
      "cache_html_path": "cache/www.cnblogs.com/html/6011769_xxxxx.html",
      "from_cache": true,
      "markdown_filename": "scp命令详解.md",
      "image_count": 0,
      "zip_name": "scp命令详解.zip"
    }
  ]
}
```

## 说明

- 当前仅支持 `*.cnblogs.com`、`mp.weixin.qq.com`
- Web 程序仅在 `src/web` 内实现，`blog2md` 通过 `import blog2md` 当作第三方库调用
- 最近记录是进程内数据，服务重启后会清空
- 元信息提取失败时会在 `meta.json` 中写入 `metadata_degraded=true` 和 `metadata_error`
- 预览渲染会把本地图片资源内联成 data URI，避免浏览器访问不到临时文件
- LLM 优化仍然遵守 `src/web/tools/markdown_formatter.py` 中的受保护元素与语义校验规则
- 用户可把优化稿一键应用回左侧原稿，再基于最新结果继续优化
- 用户手动停止流式优化后，已生成的部分结果不会丢失
- LLM 配置优先级：请求参数（若提供） > `$BLOG2MD_WEB_CONFIG` 指向 TOML > `src/web/config.toml` > `pyproject.toml`（`[tool.blog2md.llm]`） > 环境变量 `DASHSCOPE_API_KEY`

