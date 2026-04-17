# web (FastAPI)

这个目录是一个独立可拆分的 Web 子项目。

目标：在网页输入博客园/微信公众号 URL，调用 `blog2md` 转换，并下载包含 Markdown + 图片资源的 ZIP。

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

启动：

```bash
uvicorn src.web.main:app --reload --host 0.0.0.0 --port 8000
```

浏览器访问：`http://127.0.0.1:8000`

## API

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

