# blog2md 会话交接摘要

这份文档用于在新会话或新维护者接手时，快速恢复当前上下文。

它不是完整使用手册；完整说明请看 `README.md`。本文件更偏向“当前项目已经是什么状态、最近验证到哪里、后面接着做什么”。

---

## 1. 当前项目快照

- 项目已从 `html_reader` 拆分为独立仓库：`blog2md`
- 当前已采用标准 `src/blog2md/` 布局
- 已完成多站点 URL -> Markdown 能力：
  - `cnblogs`
  - `wechat (mp.weixin.qq.com)`
- 已实现统一域名路由入口：`blog2md.site_router`
- 已实现统一 Web 友好返回结构：`SiteConvertResult` + `PageMeta`
- 已实现缓存域名隔离：`cache/{domain}/html/{slug}_{hash}.html`

---

## 2. 关键架构

按职责分层如下：

1. **工具层**：`src/blog2md/tools/`
   - `extractor.py`
   - `image.py`
   - `markdown.py`
   - `pathing.py`
   - `cache.py`
2. **通用层**：`src/blog2md/parse_html.py`、`src/blog2md/converter.py`
3. **站点层**：`src/blog2md/cnblogs_url_to_md.py`、`src/blog2md/wechat_url_to_md.py`
4. **路由层**：`src/blog2md/site_router.py`
5. **共享层**：`src/blog2md/site_common.py`

共享模型与能力：

- `PageMeta`
- `SiteConvertResult`
- `resolve_output_path_by_title`

---

## 3. 已确认规则

### 3.1 缓存

- 路径：`cache/{domain}/html/{slug}_{hash}.html`
- 示例：
  - `cache/www.cnblogs.com/html/...`
  - `cache/mp.weixin.qq.com/html/...`

### 3.2 输出

- 默认 Markdown：`md/{标题}.md`
- 默认图片目录：`md/{标题}_images/`
- `-o/--output` 可覆盖输出路径

### 3.3 微信反爬图片处理

- 请求图片时附带浏览器 UA + `Referer`
- 优先按 `wx_fmt` 推断真实后缀
- 若返回 `Content-Type: text/html`，视为反爬命中
- 运行前清理历史 `image_*.img` 假图

---

## 4. 当前站点解析规则

### cnblogs

- 容器：`div.post`
- 标题：`h1.postTitle`（优先取 `a#cb_post_title_url span`）
- 正文：`div#cnblogs_post_body`

### wechat

- 容器：`div#img-content`
- 标题：`h1#activity-name`
- 正文：`div#js_content`

---

## 5. 对外入口

### 5.1 CLI 入口

- `python3 -m blog2md.parse_html`
- `python3 -m blog2md.cnblogs_url_to_md`
- `python3 -m blog2md.wechat_url_to_md`
- `python3 -m blog2md.site_router`

### 5.2 函数入口

- `convert_cnblogs_url(...)`
- `convert_wechat_url(...)`
- `convert_url_to_md(...)`（推荐）

统一返回：`SiteConvertResult`

- `markdown_path`
- `image_paths`
- `cache_html_path`
- `from_cache`
- `metadata`（`url/title/author/published_at/updated_at/site_name`）

---

## 6. 当前测试状态

测试位置：`tests/`

- `tests/test_parse_html.py`
- `tests/test_cnblogs_url_to_md.py`
- `tests/test_wechat_url_to_md.py`
- `tests/test_site_router.py`

推荐全量测试命令：

```bash
python3 -m unittest -v tests.test_parse_html tests.test_cnblogs_url_to_md tests.test_wechat_url_to_md tests.test_site_router
```

最近一次记录：全量通过（23 tests）。

---

## 7. 常用验证命令

```bash
python3 -m pip install -r requirements.txt
python3 -m pip install -e .
python3 -m unittest -v tests.test_parse_html tests.test_cnblogs_url_to_md tests.test_wechat_url_to_md tests.test_site_router
python3 -m blog2md.site_router --url "https://www.cnblogs.com/likui360/p/6011769.html"
python3 -m blog2md.site_router --url "https://www.cnblogs.com/aifrontiers/p/19868963"
python3 -m blog2md.site_router --url "https://mp.weixin.qq.com/s/Xs4UFMLs0VsaMrzk0iXoMw"
```

---

## 8. 接手建议

新会话建议按以下顺序开始：

1. 优先阅读：
   - `README.md`
   - `AI_PROMPT_GUIDE.md`
   - `SESSION_HANDOFF.md`
2. 执行全量测试
3. 如需验证真实转换，再执行 2~3 条代表性 URL
4. 若要扩展新站点，采用“新增 `*_url_to_md.py` + `site_router.py` 注册 + `tests/test_*.py`”模式

---

## 9. 后续改造建议

- 继续保持现有分层，不把站点逻辑回灌到通用层
- 新增站点时优先复用 `tools` 与 `site_common`
- 对外 CLI 和函数接口尽量保持兼容
- 所有结构性改动都要先更新测试，再更新文档

