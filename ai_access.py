# -*- coding: utf-8 -*-
"""
ai_access.py — 花友居论坛「AI 资料获取」接口蓝图（Flask Blueprint）

让 AI 代理 / RAG 管道 / 爬虫能高效获取本站内容，新增端点：

    GET /llms.txt             站点 AI 接入说明（动态生成，含版块表与接口文档）
    GET /llms-full.txt        全量主题 + 回复的 Markdown 文本（供 RAG 一次性摄取）
    GET /topic/<id>.md        单个主题的纯 Markdown 导出
    GET /forum/<id>/rss       按版块 RSS（RFC 822 标准时间格式）
    GET /api/forums           版块列表 JSON（含主题数）
    GET /openapi.json         接口文档（OpenAPI 3.0，含 web_app.py 中已有端点）

注意：主题列表/搜索/详情请使用 web_app.py 中已有的端点
（GET /api/topics、GET /api/topics?q=、GET /api/topic/<id>），
本模块不重复实现，避免行为不一致。

接入方式（在 web_app.py 底部加两行即可，不影响现有路由）：

    from ai_access import ai_bp
    app.register_blueprint(ai_bp)

可用环境变量：
    HUA_DB_PATH    SQLite 数据库路径（默认 forum.db，相对 Flask 工作目录）
    HUA_BASE_URL   站点外网地址（默认 https://hua.moome.eu.org）
    HUA_TZ_OFFSET  RSS 时间偏移（默认 +0800，按服务器时区调整）
"""

import os
import re
import sqlite3
from datetime import datetime
from xml.sax.saxutils import escape, quoteattr

from flask import Blueprint, Response, jsonify, request

ai_bp = Blueprint('ai', __name__)

BASE_URL = os.environ.get('HUA_BASE_URL', 'https://hua.moome.eu.org')
DB_PATH = os.environ.get('HUA_DB_PATH', 'forum.db')
TZ_OFFSET = os.environ.get('HUA_TZ_OFFSET', '+0800')

SITE_INTRO = (
    '花友居是一个专注花卉种植、养护和交流的中文社区论坛。'
    '内容涵盖园艺经验、植物辨识、病虫害防治、各类植物专版'
    '（月季、绣球、铁线莲、兰科、球根、苦苣苔科等）、交换/转让交易、DIY 与 AI 软硬件等板块。'
    '本文件供 AI 代理、RAG 管道与自动化工具了解如何获取本站内容。'
)


# ─────────────────────────── 基础工具 ───────────────────────────

def _db():
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    return conn


def _ts(value):
    """时间戳统一为字符串（兼容 datetime 对象与 TEXT 存储）。"""
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    if value is None:
        return ''
    s = str(value).strip()
    # 去掉微秒，保持输出整洁
    return re.sub(r'\.\d{1,6}$', '', s)


def _parse_dt(value):
    if isinstance(value, datetime):
        return value
    s = str(value or '').strip()
    for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _rss_date(value):
    """转为 RSS 2.0 要求的 RFC 822 格式，如 Wed, 16 Sep 2026 11:47:22 +0800。"""
    dt = _parse_dt(value)
    if dt is None:
        return _ts(value)
    return dt.strftime('%a, %d %b %Y %H:%M:%S') + ' ' + TZ_OFFSET


def _topic_row(row):
    """与现有 /api/topics 保持一致的字段结构。"""
    return {
        'id': row['id'],
        'title': row['title'],
        'author': row['author_name'],
        'forum_id': row['forum_id'],
        'forum_name': row['forum_name'],
        'created_at': _ts(row['created_at']),
        'updated_at': _ts(row['updated_at']),
        'replies': row['replies'],
        'views': row['views'],
    }


def _list_topic_sql():
    return '''
        SELECT t.*, f.name as forum_name, u.username as author_name
        FROM topics t
        LEFT JOIN forums f ON t.forum_id = f.id
        LEFT JOIN users u ON t.user_id = u.id
    '''


def _xml_header():
    return '<?xml version="1.0" encoding="UTF-8"?>'


# ─────────────────────────── llms.txt ───────────────────────────

@ai_bp.route('/llms.txt')
def llms_txt():
    conn = _db()
    cur = conn.cursor()
    forums = cur.execute(
        'SELECT f.id, f.name, (SELECT COUNT(*) FROM topics t WHERE t.forum_id = f.id) AS topic_count '
        'FROM forums f ORDER BY f.order_num, f.id'
    ).fetchall()
    total_topics = cur.execute('SELECT COUNT(*) FROM topics').fetchone()[0]
    total_replies = cur.execute('SELECT COUNT(*) FROM replies').fetchone()[0]
    conn.close()

    lines = [
        f'# 花友居论坛（{BASE_URL.split("://", 1)[1].rstrip("/") if "://" in BASE_URL else BASE_URL}）',
        '',
        f'> {SITE_INTRO}',
        '',
        f'> 数据规模：{total_topics} 个主题，{total_replies} 条回复，{len(forums)} 个版块。',
        '',
        '## 推荐入口',
        '',
        f'- 全量 Markdown（主题+回复，适合 RAG 一次性摄取）：{BASE_URL}/llms-full.txt',
        f'- 单主题 Markdown 导出：{BASE_URL}/topic/<id>.md（示例：{BASE_URL}/topic/1.md）',
        f'- RSS 订阅（最新主题）：{BASE_URL}/rss',
        f'- 按版块 RSS：{BASE_URL}/forum/<id>/rss（示例：{BASE_URL}/forum/5/rss）',
        f'- JSON API（主题列表，支持搜索与版块过滤）：{BASE_URL}/api/topics',
        f'- JSON API（主题详情，含正文与全部回复）：{BASE_URL}/api/topic/<id>',
        f'- JSON API（版块列表）：{BASE_URL}/api/forums',
        f'- 接口文档（OpenAPI 3.0）：{BASE_URL}/openapi.json',
        f'- 站点地图：{BASE_URL}/sitemap.xml',
        '',
        '## JSON API 说明',
        '',
        '- `GET /api/topics` — 主题列表（按创建时间倒序）',
        '  - 参数：`page`（默认 1）、`per_page`（默认 20）、`q`（标题/正文关键词搜索）、`forum_id`（按版块过滤）',
        '  - 返回：`{"total":N,"page":1,"per_page":20,"topics":[{"id","title","forum_id","forum_name","user_id","author","views","replies","created_at","updated_at"}]}`',
        '- `GET /api/topics?q=关键词` — 搜索（与列表同一端点）',
        '- `GET /api/topic/<id>` — 主题详情',
        '  - 返回：`{"id","title","forum_id","forum_name","user_id","author","content"(Markdown 原文),"views","replies","created_at","updated_at","replies":[{"id","user_id","author","content","created_at"}]}`',
        '- `GET /api/forums` — 版块列表',
        '  - 返回：`[{"id","name","description","url","rss","topic_count"}]`',
        '- 主题页面 HTML：`GET /topic/<id>`（服务端渲染，正文与回复均含在初始响应中，无需 JavaScript）',
        '',
        '## 版块列表',
        '',
        '| 版块 | 主题数 | 链接 | 版块RSS |',
        '|---|---|---|---|',
    ]
    for f in forums:
        name = f['name'].replace('|', '\\|')
        lines.append(
            f"| {name} | {f['topic_count']} | {BASE_URL}/forum/{f['id']} | {BASE_URL}/forum/{f['id']}/rss |"
        )
    lines += [
        '',
        '## 抓取建议',
        '',
        '- 版块页（/forum/<id>）与主题页（/topic/<id>）均为服务端渲染 HTML，',
        '  正文与回复直接包含在初始响应中，**无需执行 JavaScript** 即可完整解析。',
        '- 版块页与列表页支持 `?page=N` 分页。',
        '- 增量同步请优先使用 RSS 或 /api/topics（按 created_at/updated_at 过滤），无需全站爬取。',
        '- 时间戳格式为 `YYYY-MM-DD HH:MM:SS`（服务器本地时间）。',
        '- 请遵守 robots.txt 并保持温和的抓取频率。',
    ]
    return Response('\n'.join(lines) + '\n', mimetype='text/plain; charset=utf-8')


# ─────────────────────────── llms-full.txt ───────────────────────────

@ai_bp.route('/llms-full.txt')
def llms_full():
    conn = _db()
    cur = conn.cursor()
    rows = cur.execute(
        _list_topic_sql() + ' ORDER BY t.created_at ASC, t.id ASC'
    ).fetchall()
    out = [
        f'# 花友居论坛 全量内容（Markdown）',
        '',
        f'> 生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}（{TZ_OFFSET}）',
        f'> 共 {len(rows)} 个主题。本文件由程序自动重新生成，每次抓取即为最新全量。',
        '',
    ]
    for row in rows:
        cur2 = conn.cursor()
        replies = cur2.execute(
            'SELECT r.id, r.content, r.created_at, u.username as author_name '
            'FROM replies r LEFT JOIN users u ON r.user_id = u.id '
            'WHERE r.topic_id = ? AND (r.status IS NULL OR r.status = 1) ORDER BY r.created_at ASC, r.id ASC',
            (row['id'],),
        ).fetchall()
        out.append(f'## [{row["title"]}]({BASE_URL}/topic/{row["id"]})')
        out.append('')
        out.append(f'- 版块：{row["forum_name"]}')
        out.append(f'- 作者：{row["author_name"]}')
        out.append(f'- 发布时间：{_ts(row["created_at"])}')
        out.append('')
        out.append(row['content'] or '')
        if replies:
            out.append('')
            out.append('---')
            out.append('')
            out.append(f'### 回复（{len(replies)}）')
            out.append('')
            for i, r in enumerate(replies, 1):
                out.append(f'#### {i}. {r["author_name"]}（{_ts(r["created_at"])}）')
                out.append('')
                out.append(r['content'] or '')
                out.append('')
        out.append('')
    conn.close()
    return Response('\n'.join(out), mimetype='text/plain; charset=utf-8')


# ─────────────────────────── 单主题 Markdown ───────────────────────────

@ai_bp.route('/topic/<int:topic_id>.md')
def topic_markdown(topic_id):
    conn = _db()
    cur = conn.cursor()
    row = cur.execute(_list_topic_sql() + ' WHERE t.id = ?', (topic_id,)).fetchone()
    if row is None:
        conn.close()
        return Response('主题不存在', status=404)
    replies = cur.execute(
        'SELECT r.id, r.content, r.created_at, u.username as author_name '
        'FROM replies r LEFT JOIN users u ON r.user_id = u.id '
        'WHERE r.topic_id = ? AND (r.status IS NULL OR r.status = 1) ORDER BY r.created_at ASC, r.id ASC',
        (topic_id,),
    ).fetchall()
    conn.close()

    url = f'{BASE_URL}/topic/{topic_id}'
    parts = [
        f'# {row["title"]}',
        '',
        f'- 版块：{row["forum_name"]}',
        f'- 作者：{row["author_name"]}',
        f'- 发布时间：{_ts(row["created_at"])}',
        f'- 链接：{url}',
        '',
        row['content'] or '',
    ]
    if replies:
        parts += ['', '---', '', f'## 回复（{len(replies)}）', '']
        for i, r in enumerate(replies, 1):
            parts += [f'### {i}. {r["author_name"]}（{_ts(r["created_at"])}）', '', r['content'] or '', '']
    body = '\n'.join(parts) + '\n'
    return Response(
        body,
        mimetype='text/markdown; charset=utf-8',
        headers={'Content-Disposition': f'inline; filename="topic-{topic_id}.md"'},
    )


# ─────────────────────────── 按版块 RSS ───────────────────────────

@ai_bp.route('/forum/<int:forum_id>/rss')
def forum_rss(forum_id):
    conn = _db()
    cur = conn.cursor()
    forum = cur.execute('SELECT * FROM forums WHERE id = ?', (forum_id,)).fetchone()
    if forum is None:
        conn.close()
        return Response('版块不存在', status=404)
    rows = cur.execute(
        _list_topic_sql() + ' WHERE t.forum_id = ? ORDER BY t.created_at DESC, t.id DESC LIMIT 50',
        (forum_id,),
    ).fetchall()
    conn.close()

    def xml_escape(s):
        return escape(str(s or ''))

    items = []
    for row in rows:
        desc = (row['content'] or '')[:2000]
        items.append(
            '    <item>\n'
            f'    <title>{xml_escape(row["title"])}</title>\n'
            f'    <link>{BASE_URL}/topic/{row["id"]}</link>\n'
            f'    <guid>{BASE_URL}/topic/{row["id"]}</guid>\n'
            f'    <pubDate>{_rss_date(row["created_at"])}</pubDate>\n'
            f'    <author>{xml_escape(row["author_name"])}</author>\n'
            f'    <category>{xml_escape(forum["name"])}</category>\n'
            f'    <description>{xml_escape(desc)}</description>\n'
            '    </item>'
        )
    xml = (
        _xml_header() + '\n'
        '<rss version="2.0">\n'
        '<channel>\n'
        f'    <title>花友居论坛 - {xml_escape(forum["name"])}</title>\n'
        f'    <link>{BASE_URL}/forum/{forum_id}</link>\n'
        f'    <description>花友居论坛 - 版块「{xml_escape(forum["name"])}」最新主题</description>\n'
        '    <language>zh-cn</language>\n'
        + '\n'.join(items) + '\n'
        '</channel>\n'
        '</rss>\n'
    )
    return Response(xml, mimetype='application/rss+xml; charset=utf-8')


# ─────────────────────────── API：版块列表 ───────────────────────────

@ai_bp.route('/api/forums')
def api_forums():
    conn = _db()
    cur = conn.cursor()
    rows = cur.execute(
        'SELECT f.id, f.name, f.description, '
        '(SELECT COUNT(*) FROM topics t WHERE t.forum_id = f.id) AS topic_count '
        'FROM forums f ORDER BY f.order_num, f.id'
    ).fetchall()
    conn.close()
    return jsonify([
        {
            'id': r['id'],
            'name': r['name'],
            'description': r['description'],
            'url': f'{BASE_URL}/forum/{r["id"]}',
            'rss': f'{BASE_URL}/forum/{r["id"]}/rss',
            'topic_count': r['topic_count'],
        }
        for r in rows
    ])


# ─────────────────────────── OpenAPI 文档 ───────────────────────────

@ai_bp.route('/openapi.json')
def openapi():
    return jsonify({
        'openapi': '3.0.3',
        'info': {
            'title': '花友居论坛 API',
            'description': SITE_INTRO,
            'version': '1.0.0',
        },
        'servers': [{'url': BASE_URL}],
        'paths': {
            '/api/topics': {
                'get': {
                    'summary': '主题列表（加 ?q= 即为搜索）',
                    'parameters': [
                        {'name': 'page', 'in': 'query', 'schema': {'type': 'integer', 'default': 1}},
                        {'name': 'per_page', 'in': 'query', 'schema': {'type': 'integer', 'default': 20}},
                        {'name': 'q', 'in': 'query', 'schema': {'type': 'string'}, 'description': '标题/正文关键词'},
                        {'name': 'forum_id', 'in': 'query', 'schema': {'type': 'integer'}, 'description': '按版块过滤'},
                    ],
                },
                'post': {
                    'summary': '发布新主题（需 API key）',
                    'requestBody': {
                        'content': {'application/json': {'schema': {
                            'type': 'object',
                            'required': ['forum_id', 'title', 'content'],
                            'properties': {
                                'forum_id': {'type': 'integer'},
                                'title': {'type': 'string'},
                                'content': {'type': 'string'},
                            },
                        }}}
                    },
                },
            },
            '/api/topic/{id}': {
                'get': {
                    'summary': '主题详情（正文 Markdown 原文 + 全部回复）',
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'integer'}}
                    ],
                },
                'post': {
                    'summary': '回复主题（需 API key）',
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'integer'}}
                    ],
                    'requestBody': {
                        'content': {'application/json': {'schema': {
                            'type': 'object',
                            'required': ['content'],
                            'properties': {'content': {'type': 'string'}},
                        }}}
                    },
                },
            },
            '/api/forums': {'get': {'summary': '版块列表（含主题数与各版块 RSS 地址）'}},
            '/llms.txt': {'get': {'summary': '站点 AI 接入说明（llms.txt）'}},
            '/llms-full.txt': {'get': {'summary': '全量主题+回复 Markdown'}},
            '/topic/{id}.md': {
                'get': {
                    'summary': '单主题 Markdown 导出',
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'integer'}}
                    ],
                }
            },
            '/forum/{id}/rss': {
                'get': {
                    'summary': '按版块 RSS 2.0 订阅',
                    'parameters': [
                        {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'integer'}}
                    ],
                }
            },
        },
    })
