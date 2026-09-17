# 花友居论坛克隆项目

这是一个基于Flask的论坛系统，克隆自花友居论坛。

## 功能特点

- 用户系统（注册、登录、个人中心）
- 版块管理
- 主题发布和回复
- 附件上传
- 响应式设计

## 技术栈

- 后端：Python + Flask
- 数据库：SQLite
- 前端：HTML + TailwindCSS
- 爬虫：requests + BeautifulSoup4

## 安装说明

1. 克隆项目到本地：
```bash
git clone [项目地址]
cd huayouju-ta
```

2. 创建并激活虚拟环境：
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. 安装依赖：
```bash
pip install -r requirements.txt
```

4. 设置环境变量：
创建 `.env` 文件并添加以下内容：
```
FIRECRAWL_API_KEY=你的API密钥
```

5. 初始化数据库：
```bash
python site_clone.py
```

6. 运行应用：
```bash
python web_app.py
```

7. 访问网站：
打开浏览器访问 http://localhost:5000

## 项目结构

```
huayouju-ta/
├── templates/           # HTML模板
├── static/             # 静态文件
├── basic_test.py       # 基础测试脚本
├── site_analysis.py    # 网站分析脚本
├── site_clone.py       # 网站克隆脚本
├── web_app.py          # Web应用主程序
├── forum.db            # SQLite数据库
├── requirements.txt    # 项目依赖
└── README.md          # 项目说明
```

## 使用说明

1. 注册新用户
2. 浏览版块
3. 发布主题
4. 回复主题
5. 上传附件

## 注意事项

- 请确保有足够的磁盘空间用于存储数据库和附件
- 建议定期备份数据库文件
- 遵守网站的使用条款和版权规定

## 贡献指南

1. Fork 项目
2. 创建特性分支
3. 提交更改
4. 推送到分支
5. 创建 Pull Request

## AI 资料获取接口（hua.moome.eu.org）

本仓库提供 `ai_access.py`（Flask Blueprint），为 AI 代理 / RAG 管道 / 爬虫
增加一套面向机器阅读的数据接口：

| 端点 | 说明 |
|---|---|
| `GET /llms.txt` | 站点 AI 接入说明（动态生成，含版块表与接口文档） |
| `GET /llms-full.txt` | 全量主题 + 回复的 Markdown 文本 |
| `GET /topic/<id>.md` | 单个主题的纯 Markdown 导出 |
| `GET /forum/<id>/rss` | 按版块 RSS（RFC 822 时间格式） |
| `GET /api/topics/<id>` | 主题详情 JSON（正文 + 全部回复） |
| `GET /api/search` | 搜索 JSON（q / forum_id / page / per_page） |
| `GET /api/forums` | 版块列表 JSON（含主题数） |
| `GET /openapi.json` | 接口文档（OpenAPI 3.0） |

### 接入步骤

1. 把 `ai_access.py` 上传到服务器，与 `web_app.py` 放在同一目录。
2. 在 `web_app.py` 底部（`if __name__ == '__main__'` 之前）加两行：

   ```python
   from ai_access import ai_bp
   app.register_blueprint(ai_bp)
   ```

3. 重启 gunicorn（如 `systemctl restart huayouju`）。
4. 用 `robots.txt`（本仓库根目录，已移除 `Disallow: /api/`）替换服务器上现有的。

可用环境变量（可选）：`HUA_DB_PATH`（SQLite 路径，默认 `forum.db`）、
`HUA_BASE_URL`（默认 `https://hua.moome.eu.org`）、
`HUA_TZ_OFFSET`（RSS 时区偏移，默认 `+0800`）。

### 还需在 web_app.py 中手动修正的小问题

1. **`/rss` 的 pubDate 格式**：当前输出 `2026-09-16 11:47:22.040046`，
   不是 RSS 2.0 要求的 RFC 822 格式。找到生成 `/rss` 的函数，把 pubDate
   改成类似 `dt.strftime('%a, %d %b %Y %H:%M:%S') + ' +0800'`
   （可参考 `ai_access.py` 中的 `_rss_date()`）。
2. **JSON-LD 的 `datePublished`**：当前不是 ISO 8601，改成
   `dt.strftime('%Y-%m-%dT%H:%M:%S') + '+08:00'`。
3. **sitemap.xml 补 `lastmod`**：给每个 `<url>` 加上真实的
   `<lastmod>YYYY-MM-DD</lastmod>`（取主题的 updated_at 日期），
   让爬虫优先抓更新内容。
4. 建议给 `DiscussionForumPosting` 补上 `commentCount` 与 `discussionUrl` 字段。

## 许可证

MIT License 