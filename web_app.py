from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import sqlite3
from datetime import datetime
import os
import time
from werkzeug.utils import secure_filename
import requests
import re
from markupsafe import Markup
import markdown
from werkzeug.middleware.proxy_fix import ProxyFix

# 密码重置令牌存储（内存字典，重启失效）
reset_tokens = {}

def send_reset_email(username, to_email, reset_url):
    """发送密码重置邮件（SMTP，环境变量配置；未配置返回False）"""
    smtp_host = os.environ.get('SMTP_HOST', '')
    smtp_port = int(os.environ.get('SMTP_PORT', '465'))
    smtp_user = os.environ.get('SMTP_USER', '')
    smtp_pass = os.environ.get('SMTP_PASS', '')
    if not smtp_host or not smtp_user or not smtp_pass:
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.header import Header
        body = f"""你好，{username}：

你请求重置花友居论坛的密码。请在30分钟内点击以下链接完成重置：

{reset_url}

如果这不是你本人的操作，请忽略此邮件。

—— 花友居论坛"""
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = Header('花友居论坛 - 密码重置', 'utf-8')
        msg['From'] = smtp_user
        msg['To'] = to_email
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
            server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [to_email], msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"邮件发送失败: {e}")
        return False

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
# 固定密钥：避免重启后所有登录 session 失效（曾导致"传图后退出"问题）
app.secret_key = os.environ.get('SECRET_KEY', '43886a52b3f573b530a9ef3d62380a6d0bba4b73bdca2052ad04e2c7676320e2')

# ── CSRF 保护 ──
import secrets as _secrets

@app.before_request
def csrf_protect():
    """为所有 POST 请求校验 CSRF token（API 端点用 API key 豁免）"""
    if request.method != 'POST':
        return None
    # API 端点豁免（用 API key 认证）
    if request.path.startswith('/api/'):
        return None
    # 登录/注册/忘记密码（首次无session，放行；有session则校验）
    if request.path in ('/login', '/register', '/forgot_password', '/reset_password'):
        if 'csrf_token' in session:
            form_token = request.form.get('csrf_token', '')
            if form_token != session['csrf_token']:
                flash('会话已过期，请重试')
                return redirect(request.url)
        return None
    # 其他 POST 必须带 token
    token = session.get('csrf_token')
    form_token = request.form.get('csrf_token', '')
    if not token or form_token != token:
        flash('安全校验失败，请刷新页面重试')
        return redirect(request.url)
    return None

@app.context_processor
def inject_csrf():
    """向所有模板注入 CSRF token"""
    if 'csrf_token' not in session:
        session['csrf_token'] = _secrets.token_hex(16)
    return {'csrf_token': session['csrf_token']}

@app.context_processor
def inject_credit_helpers():
    """模板全局：信用分/头衔徽章"""
    def credit_badge(user_id):
        try:
            score = get_user_credit(user_id)
        except Exception:
            score = 0
        level, emoji = get_credit_level(score)
        return {'score': score, 'level': level, 'emoji': emoji}
    return {'credit_badge': credit_badge}

# 速率限制：防滥用/防爬虫（memory存储，gunicorn多worker下每worker独立计数，阈值按单worker设定）
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "60 per hour"],
    storage_uri="memory://",
)

def get_db():
    """获取SQLite数据库连接"""
    conn = sqlite3.connect('forum.db', detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    return conn

# ============ 交换区信用体系（2026-08） ============
CREDIT_RULES = {
    'trade':      1,   # 成功完成一次交换（双方各+1）
    'praise':     1,   # 收货方好评（卖家+1）
    'commend':    1,   # 发货快/包装好被点名表扬
    'fake':       -5,  # 虚假照片、以次充好（版主判罚）
    'vanish':     -5,  # 收货后玩消失、拒不确认（版主判罚）
}

def get_credit_level(score):
    if score is None or score < 0:
        score = 0
    if score <= 2:
        return ('破土', '🌱')
    elif score <= 9:
        return ('展叶', '🌿')
    elif score <= 19:
        return ('见花', '🌸')
    else:
        return ('成树', '🌳')

# 启动时建表（幂等）
def _init_credit_tables():
    c = sqlite3.connect('forum.db')
    c.executescript('''
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic_id INTEGER NOT NULL,
        user_a INTEGER NOT NULL,
        user_b INTEGER NOT NULL,
        status INTEGER DEFAULT 0,          -- 0=进行中 1=双方确认完成
        a_confirmed INTEGER DEFAULT 0,
        b_confirmed INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT (datetime('now','localtime'))
    );
    CREATE TABLE IF NOT EXISTS trade_reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trade_id INTEGER NOT NULL,
        reviewer_id INTEGER NOT NULL,
        reviewee_id INTEGER NOT NULL,
        rating TEXT NOT NULL,              -- good / bad / commend / fake / vanish
        comment TEXT,
        created_at DATETIME DEFAULT (datetime('now','localtime')),
        UNIQUE(trade_id, reviewer_id)
    );
    CREATE INDEX IF NOT EXISTS idx_trades_topic ON trades(topic_id);
    CREATE INDEX IF NOT EXISTS idx_reviews_reviewee ON trade_reviews(reviewee_id);
    CREATE TABLE IF NOT EXISTS credit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        points INTEGER NOT NULL,
        reason TEXT NOT NULL,              -- trade/praise/commend/fake/vanish/admin_adjust
        trade_id INTEGER,
        topic_id INTEGER,
        note TEXT,
        created_at DATETIME DEFAULT (datetime('now','localtime'))
    );
    CREATE INDEX IF NOT EXISTS idx_credit_log_user ON credit_log(user_id);
    ''')
    c.commit()
    c.close()

_init_credit_tables()

def get_user_credit(user_id):
    """返回该用户当前总信用分"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT COALESCE(SUM(points),0) FROM credit_log WHERE user_id = ?', (user_id,))
    total = cur.fetchone()[0]
    conn.close()
    return total

def get_sqlite_db():
    conn = sqlite3.connect('forum.db', detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    return conn

@app.template_filter('datetime')
def format_datetime(value, format='%Y-%m-%d %H:%M'):
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return value
    return value.strftime(format) if value else ''

def parse_ts(value):
    """数据库里的时间可能是 datetime 对象或 TEXT 字符串（如 '2026-09-16 11:47:22.040046'），
    统一解析为 datetime；解析失败返回 None。供 RSS/Sitemap 等需要标准时间格式的地方使用。"""
    if isinstance(value, datetime):
        return value
    s = str(value or '').strip()
    for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None

@app.route('/upload_image', methods=['POST'])
@limiter.limit("10 per minute")
def upload_image():
    """将图片上传到图床"""
    if 'file' not in request.files:
        return jsonify({'code': 400, 'message': '没有收到文件，请重新选择图片'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'code': 400, 'message': '未选择任何文件，请点击"选择图片"后再上传'}), 400

    # 文件大小检查（16MB）
    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)
    if file_size == 0:
        return jsonify({'code': 400, 'message': '文件是空的，请换一张图片'}), 400
    if file_size > 16 * 1024 * 1024:
        size_mb = round(file_size / 1024 / 1024, 1)
        return jsonify({'code': 400, 'message': f'图片太大（{size_mb}MB），最大支持 16MB，请压缩后重试'}), 400

    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    if not allowed_file(file.filename):
        return jsonify({'code': 400, 'message': f'不支持 .{ext} 格式，仅支持 JPG / PNG / GIF / WEBP 图片'}), 400

    try:
        # 使用图床API上传图片
        image_url = save_file(file)

        if image_url:
            print(f"Image uploaded to image bed: {image_url}")
            return jsonify({
                'code': 200,
                'data': {'url': image_url}
            })
        else:
            print("Failed to upload image to image bed")
            return jsonify({'code': 502, 'message': '图床服务暂时不可用，请稍等几秒再试一次；若连续失败请联系管理员'}), 502

    except Exception as e:
        print(f"Error uploading file to image bed: {str(e)}")
        return jsonify({'code': 500, 'message': f'上传出错：{str(e)[:80]}，请重试或联系管理员'}), 500

@app.route('/')
def index():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM forums ORDER BY order_num')
    forums = cursor.fetchall()
    cursor.execute('''
        SELECT t.*, f.name as forum_name, u.username as author_name
        FROM topics t
        JOIN forums f ON t.forum_id = f.id
        JOIN users u ON t.user_id = u.id
        ORDER BY t.created_at DESC
        LIMIT 10
    ''')
    latest_topics = cursor.fetchall()
    conn.close()
    return render_template('index.html', forums=forums, latest_topics=latest_topics)

def convert_markdown_to_html(content):
    """将Markdown内容转换为HTML（带XSS过滤）"""
    import bleach
    raw_html = markdown.markdown(content, extensions=['fenced_code', 'tables', 'extra'])
    # 白名单过滤：只允许安全的标签和属性
    allowed_tags = [
        'p', 'br', 'strong', 'em', 'b', 'i', 'u', 's', 'del', 'ins',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'ul', 'ol', 'li', 'blockquote', 'hr',
        'pre', 'code', 'a', 'img', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
        'span', 'div', 'sup', 'sub',
    ]
    allowed_attrs = {
        'a': ['href', 'title', 'target', 'rel'],
        'img': ['src', 'alt', 'title', 'width', 'height'],
        'code': ['class'],
        'pre': ['class'],
        'td': ['colspan', 'rowspan'],
        'th': ['colspan', 'rowspan'],
        'span': ['class'],
        'div': ['class'],
    }
    allowed_protocols = ['http', 'https', 'mailto', 'data']  # data允许但图片会额外校验
    cleaned = bleach.clean(
        raw_html,
        tags=allowed_tags,
        attributes=allowed_attrs,
        protocols=allowed_protocols,
        strip=True,
    )
    # 额外防护：移除 javascript: 协议和事件属性（bleach已处理，双保险）
    import re as re_xss
    cleaned = re_xss.sub(r'\son\w+\s*=\s*["\'][^"\']*["\']', '', cleaned)
    # 图片懒加载：给所有 <img> 加 loading="lazy"
    cleaned = re_xss.sub(r'<img ', '<img loading="lazy" ', cleaned)
    return Markup(cleaned)

def get_page_args():
    """获取分页参数，默认每页20条"""
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (ValueError, TypeError):
        page = 1
    per_page = 20
    return page, per_page

def make_summary(content, length=80):
    """生成帖子内容摘要（去Markdown标记）"""
    if not content:
        return ''
    import re as re_sum
    # 去掉图片语法和代码块
    text = re_sum.sub(r'!\[[^\]]*\]\([^)]*\)', '', content)
    text = re_sum.sub(r'```.*?```', '', text, flags=re_sum.DOTALL)
    # 去掉标题符号、加粗等标记
    text = re_sum.sub(r'[#>*`\-_~|]', '', text)
    text = re_sum.sub(r'\s+', ' ', text).strip()
    if len(text) > length:
        return text[:length] + '…'
    return text

@app.route('/search')
def search():
    """搜索帖子（标题+内容）"""
    q = request.args.get('q', '').strip()
    if not q:
        return render_template('search.html', query='', results=[], total=0, page=1, pages=1)
    
    page, per_page = get_page_args()
    conn = get_db()
    cursor = conn.cursor()
    
    # 按标题+内容搜索，相关性排序（标题命中优先）
    like = f'%{q}%'
    cursor.execute('''
        SELECT t.*, f.name as forum_name, u.username as author_name,
               (SELECT COUNT(*) FROM replies r WHERE r.topic_id = t.id) as reply_count,
               CASE WHEN t.title LIKE ? THEN 0 ELSE 1 END as rank
        FROM topics t
        JOIN forums f ON t.forum_id = f.id
        JOIN users u ON t.user_id = u.id
        WHERE t.title LIKE ? OR t.content LIKE ?
        ORDER BY rank, t.created_at DESC
        LIMIT ? OFFSET ?
    ''', (like, like, like, per_page, (page - 1) * per_page))
    results = cursor.fetchall()
    results = [dict(r) for r in results]
    for r in results:
        r['summary'] = make_summary(r['content'])
    
    # 总数
    cursor.execute('''
        SELECT COUNT(*) FROM topics WHERE title LIKE ? OR content LIKE ?
    ''', (like, like))
    total = cursor.fetchone()[0]
    conn.close()
    
    pages = max(1, (total + per_page - 1) // per_page)
    return render_template('search.html', query=q, results=results, total=total, page=page, pages=pages)

@app.route('/topic/<int:topic_id>')
def topic(topic_id):
    conn = get_db()
    cursor = conn.cursor()
    
    # 获取主题内容
    cursor.execute('SELECT t.*, u.username as author_name, f.name as forum_name FROM topics t LEFT JOIN users u ON t.user_id = u.id LEFT JOIN forums f ON t.forum_id = f.id WHERE t.id = ?', (topic_id,))
    topic = cursor.fetchone()
    
    if topic is None:
        conn.close()
        flash('主题不存在')
        return redirect(url_for('index'))
    
    # 转换Markdown为HTML
    topic = dict(topic)
    topic['content'] = convert_markdown_to_html(topic['content'])
    
    # 获取回复列表
    cursor.execute('SELECT r.*, u.username as author_name FROM replies r LEFT JOIN users u ON r.user_id = u.id WHERE r.topic_id = ? ORDER BY r.created_at', (topic_id,))
    replies = cursor.fetchall()
    
    # 转换回复中的Markdown为HTML
    replies = [dict(reply) for reply in replies]
    for reply in replies:
        reply['content'] = convert_markdown_to_html(reply['content'])
    
    # 更新浏览次数
    cursor.execute('UPDATE topics SET views = views + 1 WHERE id = ?', (topic_id,))
    
    # 点赞/收藏状态
    cursor.execute('SELECT COUNT(*) FROM topic_likes WHERE topic_id = ?', (topic_id,))
    like_count = cursor.fetchone()[0]
    user_liked = False
    user_favorited = False
    if 'user_id' in session:
        cursor.execute('SELECT id FROM topic_likes WHERE topic_id = ? AND user_id = ?', (topic_id, session['user_id']))
        user_liked = cursor.fetchone() is not None
        cursor.execute('SELECT id FROM favorites WHERE topic_id = ? AND user_id = ?', (topic_id, session['user_id']))
        user_favorited = cursor.fetchone() is not None

    # 交换区：本帖的交换记录（仅参与者可见详情，其他人只看到数量）
    trades_raw = [dict(r) for r in cursor.execute(
        'SELECT * FROM trades WHERE topic_id=? ORDER BY id DESC', (topic_id,)).fetchall()]
    me_id = session.get('user_id')
    for t in trades_raw:
        t['i_am_in'] = me_id in (t['user_a'], t['user_b']) if me_id else False
        t['my_confirmed'] = (t['a_confirmed'] if me_id == t['user_a'] else t['b_confirmed']) if t['i_am_in'] else 0
        t['other_confirmed'] = (t['b_confirmed'] if me_id == t['user_a'] else t['a_confirmed']) if t['i_am_in'] else 0
        t['i_reviewed'] = False
        if t['i_am_in']:
            cursor.execute('SELECT id FROM trade_reviews WHERE trade_id=? AND reviewer_id=?', (t['id'], me_id))
            t['i_reviewed'] = cursor.fetchone() is not None
        # 用户名
        names = {}
        for r in cursor.execute('SELECT id, username FROM users WHERE id IN (?,?)', (t['user_a'], t['user_b'])):
            names[r[0]] = r[1]
        t['name_a'] = names.get(t['user_a'], f"用户{t['user_a']}")
        t['name_b'] = names.get(t['user_b'], f"用户{t['user_b']}")

    conn.commit()
    conn.close()

    return render_template('topic.html', topic=topic, replies=replies,
                           like_count=like_count, user_liked=user_liked, user_favorited=user_favorited,
                           trades=trades_raw)

@app.route('/forum/<int:forum_id>')
def forum(forum_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM forums WHERE id = ?', (forum_id,))
    forum = cursor.fetchone()
    if not forum:
        conn.close()
        flash('版块不存在')
        return redirect(url_for('index'))
    
    page, per_page = get_page_args()
    cursor.execute('''
        SELECT t.*, u.username as author_name
        FROM topics t
        JOIN users u ON t.user_id = u.id
        WHERE t.forum_id = ?
        ORDER BY CASE t.status WHEN 2 THEN 0 WHEN 3 THEN 1 ELSE 2 END, t.created_at DESC
        LIMIT ? OFFSET ?
    ''', (forum_id, per_page, (page - 1) * per_page))
    topics = cursor.fetchall()
    # 生成摘要
    topics = [dict(t) for t in topics]
    for t in topics:
        t['summary'] = make_summary(t['content'])
    
    cursor.execute('SELECT COUNT(*) FROM topics WHERE forum_id = ?', (forum_id,))
    total = cursor.fetchone()[0]
    conn.close()
    
    pages = max(1, (total + per_page - 1) // per_page)
    return render_template('forum.html', forum=forum, topics=topics, page=page, pages=pages, total=total)

@app.route('/edit_topic/<int:topic_id>', methods=['GET', 'POST'])
def edit_topic(topic_id):
    """编辑自己的帖子"""
    if 'user_id' not in session:
        flash('请先登录')
        return redirect(url_for('login'))
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM topics WHERE id = ?', (topic_id,))
    topic = cursor.fetchone()
    
    if topic is None:
        conn.close()
        flash('主题不存在')
        return redirect(url_for('index'))
    
    # 校验作者
    if topic['user_id'] != session['user_id']:
        conn.close()
        flash('只能编辑自己的帖子')
        return redirect(url_for('topic', topic_id=topic_id))
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        if not title or not content:
            flash('标题和内容不能为空')
            conn.close()
            return redirect(url_for('edit_topic', topic_id=topic_id))
        cursor.execute('UPDATE topics SET title = ?, content = ?, updated_at = ? WHERE id = ?',
                       (title, content, datetime.now(), topic_id))
        conn.commit()
        conn.close()
        flash('帖子已更新')
        return redirect(url_for('topic', topic_id=topic_id))
    
    conn.close()
    return render_template('edit_topic.html', topic=topic)

@app.route('/delete_topic/<int:topic_id>', methods=['POST'])
def delete_topic(topic_id):
    """删除自己的帖子（连带删除回复）"""
    if 'user_id' not in session:
        flash('请先登录')
        return redirect(url_for('login'))
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM topics WHERE id = ?', (topic_id,))
    topic = cursor.fetchone()
    
    if topic is None:
        conn.close()
        flash('主题不存在')
        return redirect(url_for('index'))
    
    # 校验作者
    if topic['user_id'] != session['user_id']:
        conn.close()
        flash('只能删除自己的帖子')
        return redirect(url_for('topic', topic_id=topic_id))
    
    cursor.execute('DELETE FROM replies WHERE topic_id = ?', (topic_id,))
    cursor.execute('DELETE FROM topics WHERE id = ?', (topic_id,))
    conn.commit()
    conn.close()
    flash('帖子已删除')
    return redirect(url_for('index'))

@app.route('/edit_reply/<int:reply_id>', methods=['POST'])
def edit_reply(reply_id):
    """编辑自己的回复"""
    if 'user_id' not in session:
        return jsonify({'code': 401, 'message': '请先登录'}), 401
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM replies WHERE id = ?', (reply_id,))
    reply = cursor.fetchone()
    
    if reply is None:
        conn.close()
        return jsonify({'code': 404, 'message': '回复不存在'}), 404
    
    # 校验作者
    if reply['user_id'] != session['user_id']:
        conn.close()
        return jsonify({'code': 403, 'message': '只能编辑自己的回复'}), 403
    
    content = request.form.get('content', '').strip()
    if not content:
        conn.close()
        return jsonify({'code': 400, 'message': '内容不能为空'}), 400
    
    cursor.execute('UPDATE replies SET content = ?, updated_at = ? WHERE id = ?',
                   (content, datetime.now(), reply_id))
    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'message': '回复已更新'})

@app.route('/delete_reply/<int:reply_id>', methods=['POST'])
def delete_reply(reply_id):
    """删除自己的回复"""
    if 'user_id' not in session:
        return jsonify({'code': 401, 'message': '请先登录'}), 401
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM replies WHERE id = ?', (reply_id,))
    reply = cursor.fetchone()
    
    if reply is None:
        conn.close()
        return jsonify({'code': 404, 'message': '回复不存在'}), 404
    
    # 校验作者
    if reply['user_id'] != session['user_id']:
        conn.close()
        return jsonify({'code': 403, 'message': '只能删除自己的回复'}), 403
    
    cursor.execute('DELETE FROM replies WHERE id = ?', (reply_id,))
    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'message': '回复已删除'})

@app.route('/my_topics')
def my_topics():
    """我的帖子列表"""
    if 'user_id' not in session:
        flash('请先登录')
        return redirect(url_for('login'))
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT t.*, f.name as forum_name,
               (SELECT COUNT(*) FROM replies r WHERE r.topic_id = t.id) as reply_count
        FROM topics t
        LEFT JOIN forums f ON t.forum_id = f.id
        WHERE t.user_id = ?
        ORDER BY t.created_at DESC
    ''', (session['user_id'],))
    topics = cursor.fetchall()
    conn.close()
    return render_template('my_topics.html', topics=topics)

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

@app.route('/stats')
def stats():
    """论坛统计：版块热度、发帖排行"""
    conn = get_db()
    cursor = conn.cursor()
    
    # 版块热度
    cursor.execute('''
        SELECT f.id, f.name, COUNT(t.id) as topic_count,
               (SELECT COUNT(*) FROM replies r JOIN topics t2 ON r.topic_id = t2.id WHERE t2.forum_id = f.id) as reply_count
        FROM forums f LEFT JOIN topics t ON t.forum_id = f.id
        GROUP BY f.id ORDER BY topic_count DESC
    ''')
    forum_stats = cursor.fetchall()
    
    # 发帖排行
    cursor.execute('''
        SELECT u.id, u.username, u.avatar,
               (SELECT COUNT(*) FROM topics t WHERE t.user_id = u.id) as topic_count,
               (SELECT COUNT(*) FROM replies r WHERE r.user_id = u.id) as reply_count
        FROM users u
        ORDER BY topic_count DESC, reply_count DESC
        LIMIT 20
    ''')
    user_stats = cursor.fetchall()
    
    # 总体统计
    cursor.execute('SELECT COUNT(*) FROM users')
    user_total = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM topics')
    topic_total = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM replies')
    reply_total = cursor.fetchone()[0]
    conn.close()
    
    return render_template('stats.html', forum_stats=forum_stats, user_stats=user_stats,
                           user_total=user_total, topic_total=topic_total, reply_total=reply_total)

@app.route('/robots.txt')
def robots_txt():
    """搜索引擎爬虫规则"""
    base = request.host_url.rstrip('/')
    content = f"""User-agent: *
Allow: /
Disallow: /login
Disallow: /register
Disallow: /profile
Disallow: /edit_topic/
Disallow: /notifications

Sitemap: {base}/sitemap.xml

# AI / LLM 接入入口（AI agents & crawlers）
{base}/llms.txt
{base}/llms-full.txt
{base}/openapi.json
"""
    return content, 200, {'Content-Type': 'text/plain; charset=utf-8'}

@app.route('/sitemap.xml')
def sitemap_xml():
    """站点地图（供Google等搜索引擎抓取）"""
    from xml.sax.saxutils import escape
    base = request.host_url.rstrip('/')
    conn = get_db()
    cursor = conn.cursor()
    # 所有版块（forums表无updated_at，用created_at）
    cursor.execute('SELECT id, created_at FROM forums ORDER BY id')
    forums = cursor.fetchall()
    # 所有帖子
    cursor.execute('SELECT id, updated_at FROM topics ORDER BY updated_at DESC LIMIT 5000')
    topics = cursor.fetchall()
    conn.close()
    
    urls = [f'<url><loc>{base}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>']
    for f in forums:
        fts = ''
        fdt = parse_ts(f['created_at'])
        if fdt:
            fts = f"<lastmod>{fdt.strftime('%Y-%m-%d')}</lastmod>"
        urls.append(f'<url><loc>{base}/forum/{f["id"]}</loc>{fts}<changefreq>daily</changefreq><priority>0.8</priority></url>')
    for t in topics:
        ts = ''
        tdt = parse_ts(t['updated_at'])
        if tdt:
            ts = f"<lastmod>{tdt.strftime('%Y-%m-%d')}</lastmod>"
        urls.append(f'<url><loc>{base}/topic/{t["id"]}</loc>{ts}<changefreq>weekly</changefreq><priority>0.6</priority></url>')
    
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>'''
    return xml, 200, {'Content-Type': 'application/xml; charset=utf-8'}

@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        email = request.form['email'].strip()
        
        # 基础校验
        if not username or not password or not email:
            flash('用户名、密码、邮箱不能为空')
            return redirect(url_for('register'))
        if len(username) < 2 or len(username) > 20:
            flash('用户名长度需在2-20个字符之间')
            return redirect(url_for('register'))
        if len(password) < 6:
            flash('密码至少6位')
            return redirect(url_for('register'))
        if '@' not in email or '.' not in email:
            flash('邮箱格式不正确')
            return redirect(url_for('register'))
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
        if cursor.fetchone():
            conn.close()
            flash('用户名已存在')
            return redirect(url_for('register'))
        cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
        if cursor.fetchone():
            conn.close()
            flash('邮箱已被注册')
            return redirect(url_for('register'))
        # 密码哈希存储
        import hashlib
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        cursor.execute('INSERT INTO users (username, password, email, created_at) VALUES (?, ?, ?, ?)',
                       (username, password_hash, email, datetime.now()))
        conn.commit()
        conn.close()
        flash('注册成功，请登录')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        if user:
            import hashlib
            # 兼容两种存储：哈希密码 或 旧明文密码
            stored = user['password']
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            if stored == password_hash or stored == password:
                # 如果是明文存储的旧账号，自动升级为哈希
                if stored == password:
                    cursor.execute('UPDATE users SET password = ? WHERE id = ?', (password_hash, user['id']))
                    conn.commit()
                session['user_id'] = user['id']
                session['username'] = user['username']
                cursor.execute('UPDATE users SET last_login = ? WHERE id = ?', (datetime.now(), user['id']))
                conn.commit()
                conn.close()
                flash('登录成功')
                return redirect(url_for('index'))
        conn.close()
        flash('用户名或密码错误')
        return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('已登出')
    return redirect(url_for('index'))

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    """个人设置：上传头像、修改资料"""
    if 'user_id' not in session:
        flash('请先登录')
        return redirect(url_for('login'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        # 头像上传
        if 'avatar' in request.files and request.files['avatar'].filename:
            file = request.files['avatar']
            if file and allowed_file(file.filename):
                import uuid
                ext = file.filename.rsplit('.', 1)[1].lower()
                filename = f"avatar_{session['user_id']}_{uuid.uuid4().hex[:8]}.{ext}"
                avatar_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'avatars')
                os.makedirs(avatar_dir, exist_ok=True)
                file.save(os.path.join(avatar_dir, filename))
                cursor.execute('UPDATE users SET avatar = ? WHERE id = ?', (f"/static/avatars/{filename}", session['user_id']))
                conn.commit()
                flash('头像已更新')
        
        # 修改邮箱
        email = request.form.get('email', '').strip()
        if email:
            cursor.execute('SELECT id FROM users WHERE email = ? AND id != ?', (email, session['user_id']))
            if cursor.fetchone():
                flash('该邮箱已被其他账号使用')
            elif '@' in email and '.' in email:
                cursor.execute('UPDATE users SET email = ? WHERE id = ?', (email, session['user_id']))
                conn.commit()
                flash('邮箱已更新')
            else:
                flash('邮箱格式不正确')
    
        # 修改密码
        old_password = request.form.get('old_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        if old_password or new_password or confirm_password:
            import hashlib
            cursor.execute('SELECT password FROM users WHERE id = ?', (session['user_id'],))
            current_hash = cursor.fetchone()[0] or ''
            if hashlib.sha256(old_password.encode()).hexdigest() != current_hash:
                flash('当前密码不正确')
            elif len(new_password) < 6:
                flash('新密码至少6位')
            elif new_password != confirm_password:
                flash('两次输入的新密码不一致')
            else:
                new_hash = hashlib.sha256(new_password.encode()).hexdigest()
                cursor.execute('UPDATE users SET password = ? WHERE id = ?', (new_hash, session['user_id']))
                conn.commit()
                flash('密码修改成功')

    cursor.execute('SELECT id, username, email, avatar, created_at, last_login FROM users WHERE id = ?', (session['user_id'],))
    user = cursor.fetchone()
    conn.close()
    return render_template('profile.html', user=user)

@app.route('/user/<int:user_id>')
def user_profile(user_id):
    """用户个人主页：资料 + TA的帖子"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, email, avatar, created_at, last_login FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        flash('用户不存在')
        return redirect(url_for('index'))
    
    page, per_page = get_page_args()
    cursor.execute('''
        SELECT t.*, f.name as forum_name,
               (SELECT COUNT(*) FROM replies r WHERE r.topic_id = t.id) as reply_count
        FROM topics t JOIN forums f ON t.forum_id = f.id
        WHERE t.user_id = ?
        ORDER BY t.created_at DESC
        LIMIT ? OFFSET ?
    ''', (user_id, per_page, (page - 1) * per_page))
    topics = cursor.fetchall()
    
    cursor.execute('SELECT COUNT(*) FROM topics WHERE user_id = ?', (user_id,))
    total = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM replies WHERE user_id = ?', (user_id,))
    reply_count = cursor.fetchone()[0]
    conn.close()
    
    pages = max(1, (total + per_page - 1) // per_page)
    return render_template('user_profile.html', user=user, topics=topics, page=page, pages=pages, total=total, reply_count=reply_count)

@app.route('/like/<int:topic_id>', methods=['POST'])
def like_topic(topic_id):
    """点赞/取消点赞"""
    if 'user_id' not in session:
        return jsonify({'code': 401, 'message': '请先登录'}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM topics WHERE id = ?', (topic_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'code': 404, 'message': '帖子不存在'}), 404
    cursor.execute('SELECT id FROM topic_likes WHERE topic_id = ? AND user_id = ?', (topic_id, session['user_id']))
    existing = cursor.fetchone()
    if existing:
        cursor.execute('DELETE FROM topic_likes WHERE id = ?', (existing[0],))
        liked = False
    else:
        cursor.execute('INSERT INTO topic_likes (topic_id, user_id, created_at) VALUES (?, ?, ?)',
                       (topic_id, session['user_id'], datetime.now()))
        liked = True
    cursor.execute('SELECT COUNT(*) FROM topic_likes WHERE topic_id = ?', (topic_id,))
    count = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'liked': liked, 'count': count})

@app.route('/favorite/<int:topic_id>', methods=['POST'])
def favorite_topic(topic_id):
    """收藏/取消收藏"""
    if 'user_id' not in session:
        return jsonify({'code': 401, 'message': '请先登录'}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM topics WHERE id = ?', (topic_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'code': 404, 'message': '帖子不存在'}), 404
    cursor.execute('SELECT id FROM favorites WHERE topic_id = ? AND user_id = ?', (topic_id, session['user_id']))
    existing = cursor.fetchone()
    if existing:
        cursor.execute('DELETE FROM favorites WHERE id = ?', (existing[0],))
        favorited = False
    else:
        cursor.execute('INSERT INTO favorites (topic_id, user_id, created_at) VALUES (?, ?, ?)',
                       (topic_id, session['user_id'], datetime.now()))
        favorited = True
    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'favorited': favorited})

# ================= 交换区信用体系路由 =================

@app.route('/trade/start/<int:topic_id>', methods=['POST'])
def trade_start(topic_id):
    """发起交换：帖主+另一名用户建一条交换记录"""
    if 'user_id' not in session:
        return jsonify({'code': 401, 'message': '请先登录'}), 401
    other_id = request.form.get('user_id', type=int)
    if not other_id:
        return jsonify({'code': 400, 'message': '缺少对方用户'}), 400
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT user_id FROM topics WHERE id = ?', (topic_id,))
    row = cur.fetchone()
    if not row:
        conn.close(); return jsonify({'code': 404, 'message': '帖子不存在'}), 404
    owner_id = row[0]
    me = session['user_id']
    # 发起人必须是帖主或对方是帖主（记录里 user_a 恒为帖主）
    if me == owner_id:
        a, b = owner_id, other_id
    else:
        a, b = owner_id, me
        if other_id != owner_id:
            conn.close(); return jsonify({'code': 400, 'message': '只能和帖主发起交换'}), 400
    if a == b:
        conn.close(); return jsonify({'code': 400, 'message': '不能和自己交换'}), 400
    # 防重复：同一帖子两人之间已有进行中的交换
    cur.execute("""SELECT id FROM trades WHERE topic_id=? AND status=0 AND
                   ((user_a=? AND user_b=?) OR (user_a=? AND user_b=?))""",
                (topic_id, a, b, b, a))
    exist = cur.fetchone()
    if exist:
        conn.close(); return jsonify({'code': 409, 'message': '你们在这帖下已有一条进行中的交换', 'trade_id': exist[0]}), 409
    cur.execute('INSERT INTO trades (topic_id, user_a, user_b) VALUES (?,?,?)', (topic_id, a, b))
    trade_id = cur.lastrowid
    # 通知对方
    notify_target = b if me == a else a
    cur.execute('INSERT INTO notifications (user_id, type, content, topic_id) VALUES (?,?,?,?)',
                (notify_target, 'mention', f'有人和你发起了交换，请到帖子中确认', topic_id))
    conn.commit(); conn.close()
    return jsonify({'code': 200, 'trade_id': trade_id})

@app.route('/trade/confirm/<int:trade_id>', methods=['POST'])
def trade_confirm(trade_id):
    """双方各自点"确认收货"，都点了才算完成，各+1分"""
    if 'user_id' not in session:
        return jsonify({'code': 401, 'message': '请先登录'}), 401
    me = session['user_id']
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT * FROM trades WHERE id=?', (trade_id,))
    t = cur.fetchone()
    if not t:
        conn.close(); return jsonify({'code': 404, 'message': '交换不存在'}), 404
    if me not in (t['user_a'], t['user_b']):
        conn.close(); return jsonify({'code': 403, 'message': '不是你的交换'}), 403
    if t['status'] == 1:
        conn.close(); return jsonify({'code': 409, 'message': '该交换已完成'}), 409
    col = 'a_confirmed' if me == t['user_a'] else 'b_confirmed'
    already = t[col]
    if not already:
        cur.execute(f'UPDATE trades SET {col}=1 WHERE id=?', (trade_id,))
        # 首次确认时给对方发通知
        other = t['user_b'] if me == t['user_a'] else t['user_a']
        cur.execute('INSERT INTO notifications (user_id, type, content, topic_id) VALUES (?,?,?,?)',
                    (other, 'mention', '交换对方已确认收货，等你确认后本次交换完成', t['topic_id']))
    # 双方都确认 → 完成 + 记分
    cur.execute('SELECT a_confirmed, b_confirmed FROM trades WHERE id=?', (trade_id,))
    ac, bc = cur.fetchone()
    completed_now = False
    if ac and bc and t['status'] != 1:
        cur.execute('UPDATE trades SET status=1 WHERE id=?', (trade_id,))
        for uid in (t['user_a'], t['user_b']):
            cur.execute('INSERT INTO credit_log (user_id, points, reason, trade_id, topic_id, note) VALUES (?,?,?,?,?,?)',
                        (uid, CREDIT_RULES['trade'], 'trade', trade_id, t['topic_id'], '完成一次交换'))
        completed_now = True
    conn.commit(); conn.close()
    msg = '✅ 双方已确认，交换完成！双方信用 +1' if completed_now else ('已确认，等对方确认' if not already else '你已确认过')
    return jsonify({'code': 200, 'completed': completed_now, 'message': msg})

@app.route('/trade/review/<int:trade_id>', methods=['POST'])
def trade_review(trade_id):
    """互评：好评(对方+1)/表扬(对方+1)/差评(fake/vanish，仅版主可判罚扣分)"""
    if 'user_id' not in session:
        return jsonify({'code': 401, 'message': '请先登录'}), 401
    me = session['user_id']
    rating = request.form.get('rating', '')
    comment = (request.form.get('comment') or '').strip()[:200]
    is_admin = me == 1
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT * FROM trades WHERE id=?', (trade_id,))
    t = cur.fetchone()
    if not t:
        conn.close(); return jsonify({'code': 404, 'message': '交换不存在'}), 404
    if me not in (t['user_a'], t['user_b']) and not is_admin:
        conn.close(); return jsonify({'code': 403, 'message': '不是你的交换'}), 403
    valid = {'good', 'commend'} | ({'fake', 'vanish', 'bad'} if is_admin else set())
    if rating not in valid:
        conn.close(); return jsonify({'code': 400, 'message': '无效的评价类型'}), 400
    reviewee = t['user_b'] if me == t['user_a'] else t['user_a']
    if is_admin and me in (t['user_a'], t['user_b']):
        reviewee = request.form.get('reviewee_id', type=int) or reviewee
    # 幂等：每人每单只评一次（版主判罚除外）
    if not is_admin:
        cur.execute('SELECT id FROM trade_reviews WHERE trade_id=? AND reviewer_id=?', (trade_id, me))
        if cur.fetchone():
            conn.close(); return jsonify({'code': 409, 'message': '你已经评价过了'}), 409
    cur.execute('INSERT INTO trade_reviews (trade_id, reviewer_id, reviewee_id, rating, comment) VALUES (?,?,?,?,?)',
                (trade_id, me, reviewee, rating, comment))
    points_map = {'good': CREDIT_RULES['praise'], 'commend': CREDIT_RULES['commend'],
                  'fake': CREDIT_RULES['fake'], 'vanish': CREDIT_RULES['vanish'], 'bad': 0}
    pts = points_map.get(rating, 0)
    if pts != 0:
        cur.execute('INSERT INTO credit_log (user_id, points, reason, trade_id, topic_id, note) VALUES (?,?,?,?,?,?)',
                    (reviewee, pts, rating, trade_id, t['topic_id'],
                     comment or {'good':'好评','commend':'点名表扬','fake':'虚假/以次充好','vanish':'收货后消失'}.get(rating,'')))
    conn.commit(); conn.close()
    label = {'good':'好评','commend':'表扬','fake':'判罚：虚假','vanish':'判罚：消失','bad':'差评备案'}.get(rating)
    return jsonify({'code': 200, 'points': pts, 'reviewee': reviewee,
                    'message': f'已提交{label}' + (f'，对方信用 {pts:+d}' if pts else '')})

@app.route('/trade/detail/<int:trade_id>')
def trade_detail(trade_id):
    if 'user_id' not in session:
        return jsonify({'code': 401}), 401
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT * FROM trades WHERE id=?', (trade_id,))
    t = cur.fetchone()
    if not t: conn.close(); return jsonify({'code': 404}), 404
    reviews = [dict(r) for r in cur.execute(
        'SELECT reviewer_id, reviewee_id, rating, comment FROM trade_reviews WHERE trade_id=?', (trade_id,)).fetchall()]
    d = dict(t); d['reviews'] = reviews
    conn.close(); return jsonify(d)

@app.route('/topic/<int:topic_id>/pin', methods=['POST'])
def pin_topic(topic_id):
    """置顶/取消置顶（作者或管理员）"""
    if 'user_id' not in session:
        return jsonify({'code': 401, 'message': '请先登录'}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM topics WHERE id = ?', (topic_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'code': 404, 'message': '帖子不存在'}), 404
    is_admin = session.get('user_id') == 1  # ID=1 是管理员
    if not is_admin and row[0] != session['user_id']:
        conn.close()
        return jsonify({'code': 403, 'message': '没有权限'}), 403
    # status: 1=正常 2=置顶
    new_status = 1 if row[0] and False else None
    cursor.execute('SELECT status FROM topics WHERE id = ?', (topic_id,))
    cur_status = cursor.fetchone()[0]
    new_status = 1 if cur_status == 2 else 2
    cursor.execute('UPDATE topics SET status = ? WHERE id = ?', (new_status, topic_id))
    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'status': new_status})

@app.route('/topic/<int:topic_id>/feature', methods=['POST'])
def feature_topic(topic_id):
    """精华/取消精华（管理员）"""
    if 'user_id' not in session:
        return jsonify({'code': 401, 'message': '请先登录'}), 401
    is_admin = session.get('user_id') == 1
    if not is_admin:
        return jsonify({'code': 403, 'message': '仅管理员可操作'}), 403
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT status FROM topics WHERE id = ?', (topic_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'code': 404, 'message': '帖子不存在'}), 404
    # status: 3=精华（保留置顶位），精华用3，置顶用2
    if row[0] == 3:
        new_status = 1
    elif row[0] == 2:
        new_status = 2  # 保持置顶
    else:
        new_status = 3
    cursor.execute('UPDATE topics SET status = ? WHERE id = ?', (new_status, topic_id))
    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'status': new_status})

@app.route('/my_favorites')
def my_favorites():
    """我的收藏"""
    if 'user_id' not in session:
        flash('请先登录')
        return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor()
    page, per_page = get_page_args()
    cursor.execute('''
        SELECT t.*, f.name as forum_name, u.username as author_name
        FROM favorites fav
        JOIN topics t ON fav.topic_id = t.id
        JOIN forums f ON t.forum_id = f.id
        JOIN users u ON t.user_id = u.id
        WHERE fav.user_id = ?
        ORDER BY fav.created_at DESC
        LIMIT ? OFFSET ?
    ''', (session['user_id'], per_page, (page - 1) * per_page))
    topics = cursor.fetchall()
    cursor.execute('SELECT COUNT(*) FROM favorites WHERE user_id = ?', (session['user_id'],))
    total = cursor.fetchone()[0]
    conn.close()
    pages = max(1, (total + per_page - 1) // per_page)
    return render_template('my_favorites.html', topics=topics, page=page, pages=pages, total=total)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# ── 开放 API（AI 适配）──
# API key 从环境变量读取，默认 admin 用固定值（可通过环境变量覆盖）
API_KEYS = set(k.strip() for k in os.environ.get('FORUM_API_KEYS', 'huayouju-ai-key-2026').split(',') if k.strip())

def require_api_key():
    """校验 API key（Authorization: Bearer <key> 或 X-API-Key 头）"""
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        key = auth[7:].strip()
    else:
        key = request.headers.get('X-API-Key', '')
    if key in API_KEYS:
        return True
    return False

@app.route('/api/topics')
def api_topics():
    """获取帖子列表（支持 ?forum_id=&page=&q=）"""
    conn = get_db()
    cursor = conn.cursor()
    forum_id = request.args.get('forum_id', type=int)
    q = request.args.get('q', '').strip()
    page, per_page = get_page_args()
    
    where = []
    params = []
    if forum_id:
        where.append('t.forum_id = ?')
        params.append(forum_id)
    if q:
        like = f'%{q}%'
        where.append('(t.title LIKE ? OR t.content LIKE ?)')
        params.extend([like, like])
    
    where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''
    cursor.execute(f'''
        SELECT t.id, t.title, t.forum_id, f.name as forum_name,
               t.user_id, u.username as author, t.views, t.replies,
               t.created_at, t.updated_at
        FROM topics t
        JOIN forums f ON t.forum_id = f.id
        JOIN users u ON t.user_id = u.id
        {where_sql}
        ORDER BY t.created_at DESC
        LIMIT ? OFFSET ?
    ''', params + [per_page, (page - 1) * per_page])
    rows = cursor.fetchall()
    
    cursor.execute(f'SELECT COUNT(*) FROM topics t {where_sql}', params)
    total = cursor.fetchone()[0]
    conn.close()
    
    return jsonify({
        'total': total,
        'page': page,
        'per_page': per_page,
        'topics': [dict(r) for r in rows]
    })

@app.route('/api/topic/<int:topic_id>')
def api_topic(topic_id):
    """获取单个帖子详情（含回复）"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT t.id, t.title, t.forum_id, f.name as forum_name,
               t.user_id, u.username as author, t.content, t.views, t.replies,
               t.created_at, t.updated_at
        FROM topics t
        JOIN forums f ON t.forum_id = f.id
        JOIN users u ON t.user_id = u.id
        WHERE t.id = ?
    ''', (topic_id,))
    topic = cursor.fetchone()
    if not topic:
        conn.close()
        return jsonify({'error': '主题不存在'}), 404
    
    cursor.execute('''
        SELECT r.id, r.user_id, u.username as author, r.content, r.created_at
        FROM replies r JOIN users u ON r.user_id = u.id
        WHERE r.topic_id = ? ORDER BY r.created_at
    ''', (topic_id,))
    replies = cursor.fetchall()
    conn.close()
    
    result = dict(topic)
    result['replies'] = [dict(r) for r in replies]
    return jsonify(result)

@app.route('/api/topic/<int:topic_id>', methods=['POST'])
@limiter.limit("30 per minute")
def api_reply(topic_id):
    """AI/程序发回复（需 API key）"""
    if not require_api_key():
        return jsonify({'error': '无效的API key'}), 401
    data = request.get_json(silent=True) or request.form
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'error': '内容不能为空'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM topics WHERE id = ?', (topic_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': '主题不存在'}), 404
    
    # API 用户用第一个账号（admin）发帖
    cursor.execute('SELECT id FROM users ORDER BY id LIMIT 1')
    uid = cursor.fetchone()[0]
    cursor.execute('INSERT INTO replies (topic_id, user_id, content, created_at) VALUES (?, ?, ?, ?)',
                   (topic_id, uid, content, datetime.now()))
    cursor.execute('UPDATE topics SET replies = replies + 1 WHERE id = ?', (topic_id,))
    conn.commit()
    reply_id = cursor.lastrowid
    conn.close()
    return jsonify({'code': 200, 'reply_id': reply_id}), 201

@app.route('/api/topics', methods=['POST'])
@limiter.limit("20 per minute")
def api_new_topic():
    """AI/程序发新帖（需 API key）"""
    if not require_api_key():
        return jsonify({'error': '无效的API key'}), 401
    data = request.get_json(silent=True) or request.form
    forum_id = data.get('forum_id')
    title = (data.get('title') or '').strip()
    content = (data.get('content') or '').strip()
    
    if not forum_id:
        return jsonify({'error': '缺少 forum_id'}), 400
    if not title or not content:
        return jsonify({'error': '标题和内容不能为空'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM forums WHERE id = ?', (forum_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': '版块不存在'}), 404
    
    cursor.execute('SELECT id FROM users ORDER BY id LIMIT 1')
    uid = cursor.fetchone()[0]
    cursor.execute('INSERT INTO topics (forum_id, user_id, title, content, views, replies, created_at, updated_at) VALUES (?, ?, ?, ?, 0, 0, ?, ?)',
                   (forum_id, uid, title, content, datetime.now(), datetime.now()))
    conn.commit()
    topic_id = cursor.lastrowid
    conn.close()
    return jsonify({'code': 200, 'topic_id': topic_id}), 201

def allowed_file(filename):
    """检查文件类型是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_file(file):
    """通过图床服务上传文件（Telegraph-Image + Telegram 存储）"""
    if not (file and allowed_file(file.filename)):
        print("文件类型不允许或文件为空。")
        return None

    try:
        # 重置文件指针到开始位置，确保可以读取
        file.seek(0)
        files = {'file': (secure_filename(file.filename), file.read(), file.mimetype)}
        
        print(f"正在上传文件到图床: {file.filename}")
        response = requests.post('https://telegraph-image-dez.pages.dev/upload', files=files, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        print(f"图床API响应: {result}")
        
        if isinstance(result, list) and len(result) > 0:
            if result[0].get('url'):
                image_url = result[0]['url']
                print(f"图片上传成功，URL: {image_url}")
                return image_url
            elif result[0].get('src'):
                base_url = 'https://telegraph-image-dez.pages.dev'
                image_url = base_url + result[0]['src']
                print(f"图片上传成功，URL: {image_url}")
                return image_url
            else:
                print(f"图床响应格式异常: {result[0]}")
                return None
        else:
            error_message = result.get('error') if isinstance(result, dict) else '未知错误'
            print(f"图床上传失败: {error_message}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"请求图床服务时出错: {str(e)}")
        return None
    except Exception as e:
        print(f"处理文件上传时出错: {str(e)}")
        return None

@app.route('/new_topic/<int:forum_id>', methods=['GET', 'POST'])
def new_topic(forum_id):
    if 'user_id' not in session:
        flash('请先登录')
        return redirect(url_for('login'))
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        
        # 图片URL已经在前端通过Markdown语法添加到content中，
        # 所以这里不需要额外处理图片上传
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO topics (forum_id, user_id, title, content, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)',
                       (forum_id, session['user_id'], title, content, datetime.now(), datetime.now()))
        topic_id = cursor.lastrowid
        conn.commit()
        conn.close()
        flash('主题发布成功')
        return redirect(url_for('topic', topic_id=topic_id))
    return render_template('new_topic.html', forum_id=forum_id)

@app.route('/reply/<int:topic_id>', methods=['POST'])
def reply(topic_id):
    if 'user_id' not in session:
        flash('请先登录')
        return redirect(url_for('login'))
    content = request.form['content']
    
    # 图片URL已经在前端通过Markdown语法添加到content中，
    # 所以这里不需要额外处理图片上传
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, title FROM topics WHERE id = ?', (topic_id,))
    topic_owner = cursor.fetchone()
    if not topic_owner:
        conn.close()
        flash('帖子不存在')
        return redirect(url_for('index'))
    
    cursor.execute('INSERT INTO replies (topic_id, user_id, content, created_at) VALUES (?, ?, ?, ?)',
                   (topic_id, session['user_id'], content, datetime.now()))
    cursor.execute('UPDATE topics SET replies = replies + 1 WHERE id = ?', (topic_id,))
    
    # ── 通知：帖子作者收到回复提醒（自己回复自己不通知）──
    if topic_owner[0] != session['user_id']:
        cursor.execute('''INSERT INTO notifications (user_id, type, content, topic_id, created_at)
                          VALUES (?, 'reply', ?, ?, ?)''',
                       (topic_owner[0], f'{session.get("username", "有人")} 回复了你的帖子《{topic_owner[1][:30]}》', topic_id, datetime.now()))
    
    # ── 通知：@提及检测 ──
    import re as re_mention
    mentioned = set(re_mention.findall(r'@([\u4e00-\u9fa5\w\-]{2,20})', content))
    if mentioned:
        for name in mentioned:
            cursor.execute('SELECT id FROM users WHERE username = ?', (name,))
            u = cursor.fetchone()
            if u and u[0] != session['user_id']:
                cursor.execute('''INSERT INTO notifications (user_id, type, content, topic_id, created_at)
                                  VALUES (?, 'mention', ?, ?, ?)''',
                               (u[0], f'{session.get("username", "有人")} 在《{topic_owner[1][:30]}》中提到了你', topic_id, datetime.now()))
    
    conn.commit()
    conn.close()
    flash('回复成功')
    return redirect(url_for('topic', topic_id=topic_id))

@app.route('/notifications')
def notifications():
    """通知列表"""
    if 'user_id' not in session:
        flash('请先登录')
        return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''SELECT * FROM notifications
                      WHERE user_id = ? ORDER BY created_at DESC LIMIT 50''', (session['user_id'],))
    notifs = cursor.fetchall()
    # 标记已读
    cursor.execute('UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0', (session['user_id'],))
    conn.commit()
    conn.close()
    return render_template('notifications.html', notifications=notifs)

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    """忘记密码：输入邮箱，生成重置令牌并发送/显示重置链接"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT id, username FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        if user:
            import hashlib, secrets
            token = secrets.token_urlsafe(24)
            # 令牌有效期30分钟，存内存字典（重启失效，够用）
            reset_tokens[token] = {'user_id': user[0], 'expires': time.time() + 1800}
            reset_url = f"{request.host_url.rstrip('/')}/reset_password?token={token}"
            # 尝试发邮件，失败则显示链接
            sent = send_reset_email(user[1], email, reset_url)
            if sent:
                flash('重置链接已发送到你的邮箱，30分钟内有效')
            else:
                flash(f'邮件发送失败（未配置SMTP），重置链接：/reset_password?token={token}')
        else:
            flash('该邮箱未注册')
        conn.close()
        return redirect(url_for('forgot_password'))
    return render_template('forgot_password.html')

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    """用令牌重置密码"""
    token = request.args.get('token', '')
    if request.method == 'POST':
        token = request.form.get('token', '')
        new_password = request.form.get('password', '')
        confirm = request.form.get('confirm', '')
        if len(new_password) < 6:
            flash('密码至少6位')
            return redirect(url_for('reset_password', token=token))
        if new_password != confirm:
            flash('两次输入的密码不一致')
            return redirect(url_for('reset_password', token=token))
        info = reset_tokens.get(token)
        if not info or time.time() > info['expires']:
            flash('链接无效或已过期')
            return redirect(url_for('forgot_password'))
        import hashlib
        conn = get_db()
        cursor = conn.cursor()
        password_hash = hashlib.sha256(new_password.encode()).hexdigest()
        cursor.execute('UPDATE users SET password = ? WHERE id = ?', (password_hash, info['user_id']))
        conn.commit()
        conn.close()
        reset_tokens.pop(token, None)
        flash('密码已重置，请用新密码登录')
        return redirect(url_for('login'))
    if not token:
        return redirect(url_for('forgot_password'))
    return render_template('reset_password.html', token=token)

@app.route('/notifications/unread_count')
def unread_count():
    """未读通知数（导航栏角标用）"""
    if 'user_id' not in session:
        return jsonify({'count': 0})
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0', (session['user_id'],))
    count = cursor.fetchone()[0]
    conn.close()
    return jsonify({'count': count})

@app.template_filter('auto_link')
def auto_link(text):
    if not text:
        return ""
    
    # 替换换行符为 <br>
    text = text.replace('\n', '<br>')
    
    # 处理Markdown格式的图片和普通图片URL
    def replace_url(match):
        url = match.group(0)
        # 检查URL是否以图片扩展名结尾
        if url.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            return f'<img src="{url}" alt="图片" class="content-image" loading="lazy">'
        else:
            return f'<a href="{url}" target="_blank">{url}</a>'
    
    # 处理Markdown格式的图片 (匹配绝对和相对路径)
    img_pattern = r'!\[([^\]]*)\]\(([^)\s]+)\)'
    def replace_img(match):
        alt_text = match.group(1)
        url = match.group(2)
        return f'<img src="{url}" alt="{alt_text}" class="content-image" loading="lazy">'
    
    # 先处理Markdown格式的图片
    text = re.sub(img_pattern, replace_img, text)
    
    # 再处理普通URL (匹配绝对和相对路径)
    url_pattern = r'((?:https?://|/)[^\s<\)]+)' # 匹配以 http://, https:// 或 / 开头的URL
    text = re.sub(url_pattern, replace_url, text)
    
    return Markup(text)

from flask import send_from_directory

# ... (其他代码)

@app.route('/rss')
def rss_feed():
    """RSS 2.0 订阅源"""
    from xml.sax.saxutils import escape
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT t.id, t.title, t.content, t.created_at,
               u.username as author, f.name as forum_name
        FROM topics t
        JOIN users u ON t.user_id = u.id
        JOIN forums f ON t.forum_id = f.id
        ORDER BY t.created_at DESC
        LIMIT 20
    ''')
    topics = cursor.fetchall()
    conn.close()
    
    base_url = request.host_url.rstrip('/')
    items = []
    for t in topics:
        link = f"{base_url}/topic/{t['id']}"
        # 时间可能是 datetime 或 TEXT 字符串；统一解析成 RFC 822（RSS 2.0 要求）
        pub_dt = parse_ts(t['created_at'])
        pub = pub_dt.strftime('%a, %d %b %Y %H:%M:%S +0800') if pub_dt else str(t['created_at'])
        items.append(f'''<item>
    <title>{escape(t['title'])}</title>
    <link>{link}</link>
    <guid>{link}</guid>
    <pubDate>{pub}</pubDate>
    <author>{escape(t['author'])}</author>
    <category>{escape(t['forum_name'])}</category>
    <description>{escape(t['content'][:500])}</description>
</item>''')
    
    rss = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
    <title>花友居论坛</title>
    <link>{base_url}</link>
    <description>花友居论坛 - 最新主题</description>
    <language>zh-cn</language>
    {''.join(items)}
</channel>
</rss>'''
    return rss, 200, {'Content-Type': 'application/rss+xml; charset=utf-8'}

@app.route('/deploy/static/<path:filename>')
def serve_deploy_static(filename):
    return send_from_directory(os.path.join(app.root_path, 'deploy', 'static'), filename)

# ============ AI 资料获取接口（llms.txt / llms-full.txt / 版块RSS / 主题Markdown / openapi） ============
from ai_access import ai_bp
app.register_blueprint(ai_bp)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
