# blog2md 协作提示词指南

这份文档面向 AI/协作者，主要用于：

1. 快速理解当前项目的维护边界
2. 提供可以直接复用的提示词模板
3. 约束后续改造，避免偏离现有架构

关于安装、CLI 用法、目录结构和测试命令的完整说明，以 `README.md` 为主；本文件更关注“怎么改”和“改的时候不能破坏什么”。

## 0. 一分钟用法（先看这个）

建议每次提需求时，至少写清楚 5 件事：

1. **目标**：要解决什么问题（例如“修复 cnblogs 代码块被拆碎”）
2. **范围**：允许修改哪些文件/目录
3. **约束**：哪些行为不能变（接口、缓存路径、错误处理）
4. **验收**：如何判断完成（测试命令、实测 URL、预期输出）
5. **交付**：你希望看到什么（改动文件、风险、后续建议）

可直接套用：

```text
任务目标：
[一句话描述目标]

允许修改范围：
- [目录/文件]

必须保持不变：
- [接口/行为]

验收标准：
- [测试命令]
- [实测 URL 与预期]

交付格式：
- 改动文件
- 关键行为变化
- 风险与回滚点
```

---

## 1. 项目速记

`blog2md` 由 `html_reader` 拆分而来，当前是一个采用 `src/blog2md/` 布局的 Python 项目。

核心分层：

- 工具层：`src/blog2md/tools/`
- 通用层：`src/blog2md/parse_html.py` + `src/blog2md/converter.py`
- 站点层：
  - `src/blog2md/cnblogs_url_to_md.py`
  - `src/blog2md/wechat_url_to_md.py`
- 路由层：`src/blog2md/site_router.py`
- 共享层：`src/blog2md/site_common.py`

当前支持站点：

- `*.cnblogs.com`
- `mp.weixin.qq.com`

统一输出模型：`SiteConvertResult`

- `markdown_path`
- `image_paths`
- `cache_html_path`
- `from_cache`
- `metadata`（`PageMeta`）
  - `url`
  - `title`
  - `author`
  - `published_at`
  - `updated_at`
  - `site_name`

关键规则：

- 缓存路径：`cache/{domain}/html/{slug}_{hash}.html`
- 默认输出：`md/{标题}.md`
- 默认图片目录：`md/{标题}_images/`
- 微信图片下载保留 `Referer`、浏览器 UA、`wx_fmt` 优先策略，并清理历史 `image_*.img`

---

## 2. 维护边界（必须遵守）

1. **只改当前仓库目录（blog2md）**
2. 尽量保持现有 CLI 和函数接口兼容
3. 保持现有多层结构，不要把站点定制逻辑塞回通用层
4. 新增站点优先走“新文件 + 路由注册”模式，不破坏已有站点逻辑
5. 图片下载失败不应导致整篇转换失败
6. 缓存策略必须继续保持“域名隔离”
7. 提交前必须跑测试

推荐测试命令：

```bash
python3 -m unittest -v tests.test_parse_html tests.test_cnblogs_url_to_md tests.test_wechat_url_to_md tests.test_site_router
```

---

## 3. 任务实施 checklist（建议）

处理改造任务时，建议按下面顺序执行：

1. 先给出 checklist
2. 指出将修改的文件与原因
3. 阅读相关实现和测试，确认调用链
4. 保持最小改动完成改造
5. 运行测试并汇报结果
6. 输出改动文件、关键行为变化、兼容性影响、测试结果

---

## 4. 通用提示词模板（增强版，可直接复制）

```text
你是一个 Python 维护助手。请只处理当前仓库目录（blog2md），并遵守现有分层架构。

任务目标：
[写明具体需求]

任务背景：
[补充上下文，例如：用户反馈、报错堆栈、目标 URL]

允许修改范围：
- [例如 src/blog2md/*, tests/*]

禁止事项：
- 不要重构无关模块
- 不要改变已公开函数签名（除非明确要求）
- 不要破坏缓存目录结构和图片失败降级策略

必须遵守：
1) 只能修改当前仓库内文件。
2) 保持已有 CLI 与函数接口兼容。
3) 保持多站点架构分层：
   - 工具层：src/blog2md/tools/*
   - 通用层：src/blog2md/site_common.py / src/blog2md/converter.py
   - 站点层：src/blog2md/*_url_to_md.py
   - 路由层：src/blog2md/site_router.py
4) 若新增站点，采用“新增站点脚本 + site_router 注册”模式。
5) 图片下载失败不应导致整篇转换失败。
6) 修改后必须运行并汇报 unittest 结果。

验收标准：
1) 功能按预期生效，并给出最小复现/实测说明。
2) 测试命令可直接复制执行。
3) 汇报里必须包含兼容性影响与潜在风险。

实施步骤：
1) 先给出 checklist。
2) 指出将修改的文件与原因。
3) 完成改造并保持最小改动。
4) 运行测试：
   python3 -m unittest -v tests.test_parse_html tests.test_cnblogs_url_to_md tests.test_wechat_url_to_md tests.test_site_router
5) 输出：改动文件、关键行为变化、兼容性影响、测试结果。
```

---

## 5. 常见任务专用提示词

### 5.1 新增站点支持

```text
请在 blog2md 内新增 [domain] 的 URL 转 Markdown 支持。
要求：
1) 新建 [site]_url_to_md.py，不改现有站点脚本核心逻辑。
2) 复用 site_common.py（缓存、结果模型、输出路径）。
3) 复用 tools 中的 markdown/image/pathing/cache 能力，必要时做站点专用图片下载器。
4) 在 site_router.py 注册域名分发。
5) 增加 tests/test_[site]_url_to_md.py，并更新 tests/test_site_router.py。
6) 跑全量测试并汇报。
```

### 5.2 调整缓存策略

```text
请在 blog2md 内调整缓存策略，但必须保持“域名隔离”。
要求：
1) 修改集中在 site_common.py 或 tools/cache.py。
2) 兼容已存在 cache 目录结构，不破坏已有转换逻辑。
3) 补充/更新相关测试断言。
4) 跑全量测试并给出变更前后路径示例。
```

### 5.3 优化微信反爬图片下载

```text
请在 blog2md 内优化 wechat_url_to_md.py 的图片下载可靠性。
要求：
1) 保留 Referer + 浏览器头机制。
2) 保留 wx_fmt 后缀优先策略。
3) 下载失败时不中断整篇转换。
4) 增加失败场景测试（如 Content-Type=html）。
5) 跑全量测试并给出真实链接验证结果。
```

### 5.4 Web 子项目（`src/web`）改造

```text
请只在 src/web 目录内完成以下需求：[写需求]。

约束：
1) blog2md 作为第三方库使用：通过 import blog2md 调用，不把核心转换逻辑复制到 web。
2) API 行为兼容：POST /api/convert 返回 ZIP（md + 图片 + meta.json），GET /api/history 保持可用。
3) 不引入与需求无关的复杂依赖。
4) 对失败场景给出可读错误信息（HTTP 状态码 + message）。

交付：
1) 改动文件清单（仅 src/web 下）。
2) 运行命令与最小验证步骤。
3) smoke 测试或等价验证结果。
```

---

## 6. 结果汇报模板（建议）

```text
【改动文件】
- fileA
- fileB

【行为变化】
- 变化1
- 变化2

【兼容性】
- CLI: 未变/变化点
- 函数接口: 未变/变化点
- 缓存路径: 未变/变化点

【测试】
- 命令: python3 -m unittest -v ...
- 结果: 通过 X / 失败 Y

【实测】
- URL1 -> 输出路径 / 图片数量 / 缓存命中
- URL2 -> ...

【风险与后续】
- 风险
- 建议
```

---

## 7. 快速命令

```bash
cd <your-blog2md-repo>
python3 -m pip install -r requirements.txt
python3 -m pip install -e .
python3 -m unittest -v tests.test_parse_html tests.test_cnblogs_url_to_md tests.test_wechat_url_to_md tests.test_site_router
python3 -m blog2md.site_router --url "https://www.cnblogs.com/likui360/p/6011769.html"
python3 -m blog2md.site_router --url "https://mp.weixin.qq.com/s/Xs4UFMLs0VsaMrzk0iXoMw"
```

---

## 8. 文档职责说明

- `README.md`：项目事实总览和使用说明
- `AI_PROMPT_GUIDE.md`：协作边界、模板、交付格式
- `SESSION_HANDOFF.md`：当前状态、最近验证结果、下一步建议

---

## 9. 提示词质量自检（提交前 30 秒）

发给 AI 前，快速检查：

- 是否写明了“范围”（改哪里 / 不改哪里）
- 是否写明了“验收”（跑什么测试 / 看什么输出）
- 是否要求了“最小改动”与“兼容性说明”
- 是否要求保留失败降级策略（图片下载失败不影响正文）
- 是否要求最终给出风险与后续建议

