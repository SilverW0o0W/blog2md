# blog2md

`blog2md` 是一个从 `html_reader` 拆分出来的独立项目，用来把博客页面转换成 Markdown，并在需要时把图片下载到本地、自动改写 Markdown 中的图片链接。

当前项目同时支持：

- 通用 HTML -> Markdown 转换
- 站点定制解析（目前支持 `cnblogs`、`mp.weixin.qq.com`）
- 图片下载到本地并自动改写 Markdown 链接
- URL 抓取缓存（按域名隔离）
- CLI 与函数式调用（便于接入 Web 服务）

---

## 1. 文档索引

- `README.md`：项目事实总览、安装、使用、架构、测试
- `AI_PROMPT_GUIDE.md`：AI/协作者的维护边界、提示词模板、交付格式
- `SESSION_HANDOFF.md`：当前状态快照、验证记录、后续接手建议

如果你是第一次接触这个项目，推荐阅读顺序：

1. `README.md`
2. `AI_PROMPT_GUIDE.md`
3. `SESSION_HANDOFF.md`

---

## 2. 当前能力范围

### 2.1 通用转换能力

- 支持本地 HTML 文件输入
- 支持 URL 输入
- 支持关闭图片下载
- 支持指定正文容器 CSS selector

### 2.2 已支持站点

- `*.cnblogs.com`
- `mp.weixin.qq.com`

### 2.3 统一返回模型（Web 服务友好）

核心返回结构：`SiteConvertResult`

- `markdown_path`：Markdown 文件路径
- `image_paths`：本地图片路径列表
- `cache_html_path`：缓存 HTML 路径
- `from_cache`：是否命中缓存
- `metadata`：`PageMeta`
  - `url`
  - `title`
  - `author`
  - `published_at`
  - `updated_at`
  - `site_name`

---

## 3. 项目结构

当前项目采用标准 `src` 布局：

```text
blog2md/
├── src/blog2md/
│   ├── tools/
│   │   ├── cache.py
│   │   ├── extractor.py
│   │   ├── image.py
│   │   ├── markdown.py
│   │   └── pathing.py
│   ├── cnblogs_url_to_md.py
│   ├── constants.py
│   ├── converter.py
│   ├── models.py
│   ├── parse_html.py
│   ├── site_common.py
│   ├── site_router.py
│   └── wechat_url_to_md.py
├── tests/
├── README.md
├── AI_PROMPT_GUIDE.md
├── SESSION_HANDOFF.md
├── requirements.txt
├── pyproject.toml
└── test.html
```

按职责可以理解为四层：

1. **工具层**：`src/blog2md/tools/`
   - `extractor.py`：正文提取
   - `image.py`：图片下载与路径改写
   - `markdown.py`：Markdown 渲染
   - `pathing.py`：输入加载与输出路径处理
   - `cache.py`：URL 缓存
2. **通用层**：`src/blog2md/parse_html.py` + `src/blog2md/converter.py`
3. **站点层**：
   - `src/blog2md/cnblogs_url_to_md.py`
   - `src/blog2md/wechat_url_to_md.py`
4. **路由层**：`src/blog2md/site_router.py`

共享能力集中在：`src/blog2md/site_common.py`

- `PageMeta`
- `SiteConvertResult`
- `resolve_output_path_by_title`

---

## 4. 安装

推荐使用可编辑安装，这样可以直接运行 `src/` 布局下的包模块：

```bash
python3 -m pip install -r requirements.txt
python3 -m pip install -e .
```

如果你只是临时运行测试，当前项目也提供了一个过渡方案：`tests/__init__.py` 会在测试启动时自动把 `src/` 加入导入路径。

---

## 5. CLI 用法

### 5.1 通用 HTML 转 Markdown

模块：`blog2md.parse_html`

#### 1) 本地 HTML 文件

```bash
python3 -m blog2md.parse_html -i test.html
```

默认输出：

- `md/test.md`
- `md/test_images/`

#### 2) 不下载图片

```bash
python3 -m blog2md.parse_html -i test.html --no-download-images
```

#### 3) URL 输入

```bash
python3 -m blog2md.parse_html --url "https://example.com/post" -o output.md
```

#### 4) 指定正文容器选择器

```bash
python3 -m blog2md.parse_html -i test.html -o output.md --selector "#content"
```

### 5.2 博客园定制转换

模块：`blog2md.cnblogs_url_to_md`

定制规则：

- 主容器：`div.post`
- 标题：`h1.postTitle`
- 正文：`div#cnblogs_post_body`
- 代码块：识别博客园常见代码 `div` 并转 fenced code block

示例：

```bash
python3 -m blog2md.cnblogs_url_to_md --url "https://www.cnblogs.com/likui360/p/6011769.html"
```

自定义输出与缓存目录：

```bash
python3 -m blog2md.cnblogs_url_to_md --url "https://www.cnblogs.com/likui360/p/6011769.html" -o md/likui360.md --cache-dir cache/html
```

### 5.3 微信公众号定制转换

模块：`blog2md.wechat_url_to_md`

定制规则：

- 主容器：`div#img-content`
- 标题：`h1#activity-name`
- 正文：`div#js_content`

图片反爬处理：

- 下载图片时附带 `Referer` 与浏览器 UA 请求头
- 优先根据 `wx_fmt` 识别图片后缀（如 `.png/.jpg`）
- 若返回 `Content-Type: text/html`，视为命中反爬
- 自动清理历史遗留 `.img` 假图文件

示例：

```bash
python3 -m blog2md.wechat_url_to_md --url "https://mp.weixin.qq.com/s/Xs4UFMLs0VsaMrzk0iXoMw"
```

### 5.4 域名路由统一入口（推荐）

模块：`blog2md.site_router`

支持按 URL 域名自动选择解析器：

- `*.cnblogs.com` -> 博客园解析器
- `mp.weixin.qq.com` -> 微信解析器

示例：

```bash
python3 -m blog2md.site_router --url "https://www.cnblogs.com/likui360/p/6011769.html"
python3 -m blog2md.site_router --url "https://mp.weixin.qq.com/s/Xs4UFMLs0VsaMrzk0iXoMw"
```

---

## 6. 函数调用入口

可直接调用：

- `convert_cnblogs_url(...)`
- `convert_wechat_url(...)`
- `convert_url_to_md(...)`（推荐，统一入口）

这三个入口都适合后续接入 Web 服务、批处理脚本或其他应用层逻辑。

---

## 7. 缓存与输出规则

### 7.1 缓存规则（域名隔离）

所有 URL 页面统一缓存到：

- `cache/{domain}/html/{slug}_{hash}.html`

例如：

- `cache/www.cnblogs.com/html/6011769_xxxxxxxx.html`
- `cache/mp.weixin.qq.com/html/Xs4UFMLs0VsaMrzk0iXoMw_xxxxxxxx.html`

### 7.2 输出规则

- 默认 Markdown：`md/{标题}.md`（站点定制脚本）
- 默认图片目录：`md/{标题}_images/`
- `-o/--output` 可覆盖 Markdown 输出路径

---

## 8. 当前站点解析规则

### 8.1 cnblogs

- 容器：`div.post`
- 标题：`h1.postTitle`
- 标题提取优先：`a#cb_post_title_url span`
- 正文：`div#cnblogs_post_body`

### 8.2 wechat

- 容器：`div#img-content`
- 标题：`h1#activity-name`
- 正文：`div#js_content`

---

## 9. 测试

当前测试文件：

- `tests/test_parse_html.py`
- `tests/test_cnblogs_url_to_md.py`
- `tests/test_wechat_url_to_md.py`
- `tests/test_site_router.py`

推荐单独运行：

```bash
python3 -m unittest -v tests.test_parse_html
python3 -m unittest -v tests.test_cnblogs_url_to_md
python3 -m unittest -v tests.test_wechat_url_to_md
python3 -m unittest -v tests.test_site_router
```

推荐一次性全量运行：

```bash
python3 -m unittest -v tests.test_parse_html tests.test_cnblogs_url_to_md tests.test_wechat_url_to_md tests.test_site_router
```

---

## 10. 常用验证命令

```bash
python3 -m blog2md.site_router --url "https://www.cnblogs.com/likui360/p/6011769.html"
python3 -m blog2md.site_router --url "https://www.cnblogs.com/aifrontiers/p/19868963"
python3 -m blog2md.site_router --url "https://mp.weixin.qq.com/s/Xs4UFMLs0VsaMrzk0iXoMw"
```

---

## 11. 维护与扩展建议

- 新增站点时，优先采用“新增 `*_url_to_md.py` + `site_router.py` 注册 + `tests/test_*.py`”模式
- 尽量保持现有 CLI 与函数接口兼容
- 图片下载失败不应导致整篇转换失败
- 缓存策略应继续保持“域名隔离”
- 提交前务必运行测试

