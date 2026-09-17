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

本仓库的 `web_app.py` 即线上当前版本（2026-09 已同步），并做了以下 AI 友好化改造：

**`web_app.py` 内的修复（已完成）：**
1. `/rss` 的 pubDate 改为 RFC 822 标准格式（如 `Wed, 16 Sep 2026 11:47:22 +0800`），
   兼容数据库里 TEXT 格式的时间戳（见 `parse_ts()` 辅助函数）。
2. `/sitemap.xml` 的 `<lastmod>` 修复：原来 TEXT 时间戳导致 lastmod 静默缺失，现在版块和主题都会输出。
3. `/robots.txt` 移除 `Disallow: /api/`，并附 AI 接入入口（llms.txt / openapi.json）。
4. 底部注册 `ai_access` Blueprint（`from ai_access import ai_bp`）。

**`ai_access.py` 新增端点（Flask Blueprint）：**

| 端点 | 说明 |
|---|---|
| `GET /llms.txt` | 站点 AI 接入说明（动态生成，含版块表与接口文档） |
| `GET /llms-full.txt` | 全量主题 + 回复的 Markdown 文本（供 RAG 一次性摄取） |
| `GET /topic/<id>.md` | 单个主题的纯 Markdown 导出 |
| `GET /forum/<id>/rss` | 按版块 RSS（RFC 822 时间格式） |
| `GET /api/forums` | 版块列表 JSON（含主题数与各版块 RSS 地址） |
| `GET /openapi.json` | 接口文档（OpenAPI 3.0，含已有端点与新增端点） |

**已有端点（web_app.py 原有，勿重复实现）：**
- `GET /api/topics` — 主题列表，支持 `q`（搜索）、`forum_id`、`page`、`per_page`
- `GET /api/topic/<id>` — 主题详情（正文 Markdown 原文 + 全部回复），注意是**单数** topic
- `POST /api/topic/<id>`、`POST /api/topics` — 发回复/新帖（需 API key）

### 部署步骤

1. 服务器上 `web_app.py` 与 `ai_access.py` 两个文件都替换为本仓库版本
   （`ai_access.py` 放到与 `web_app.py` 同目录）。
2. 重启服务（如 `systemctl restart huayouju`）。
3. 验证：`/llms.txt`、`/llms-full.txt`、`/api/forums`、`/openapi.json`、
   `/forum/1/rss`、`/topic/1.md` 均应返回 200；`/rss` 的 pubDate 应为 RFC 822 格式。

可用环境变量（可选）：`HUA_DB_PATH`（SQLite 路径，默认 `forum.db`）、
`HUA_BASE_URL`（默认 `https://hua.moome.eu.org`）、
`HUA_TZ_OFFSET`（RSS 时区偏移，默认 `+0800`）。

### 剩余待改（在模板里，非 web_app.py）

- **`topic.html` 中 JSON-LD 的 `datePublished`**：当前输出原始字符串
  （如 `2026-09-08 12:20:34.057546`），不是 ISO 8601。`web_app.py` 已提供
  `iso8601` 模板过滤器，把模板里 `"datePublished": "{{ topic.created_at }}"`
  改成 `"datePublished": "{{ topic.created_at|iso8601 }}"` 即可
  （输出 `2026-09-08T12:20:34+08:00`）。`dateModified` 同理。
- 建议给 `DiscussionForumPosting` 补上 `commentCount`（= 回复数）与
  `discussionUrl`（= 主题 URL）字段。

## 许可证

MIT License 