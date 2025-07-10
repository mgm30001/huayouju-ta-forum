from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
# import MySQLdb # 注释掉 MySQLdb 导入
# import MySQLdb.cursors # 注释掉 MySQLdb.cursors 导入
from datetime import datetime
import os
from werkzeug.utils import secure_filename
import requests # 引入 requests 库
import re
from markupsafe import Markup

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

# 数据库配置
DB_TYPE = os.environ.get('DB_TYPE', 'sqlite')  # 默认使用sqlite，强制为sqlite以避免mysqlclient问题

# Telegraph-Image 服务上传接口
TELEGRAPH_IMAGE_UPLOAD_URL = "https://tu.moome.dpdns.org/upload" # Telegraph-Image 的上传接口

# 文件上传配置
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 限制文件大小为16MB

def get_sqlite_db():
    """获取SQLite数据库连接"""
    conn = sqlite3.connect('forum.db', detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    return conn

def get_db():
    """获取数据库连接"""
    # 强制使用SQLite，避免MySQLdb依赖问题
    return get_sqlite_db()

@app.template_filter('auto_link')
def auto_link(text):
    if not text:
        return ""
    
    # 替换换行符为 <br>
    text = text.replace('\n', '<br>')
    
    # 处理Markdown格式的图片
    img_pattern = r'!\[([^\]]*)\]\((https?://[^\s\)]+)\)'
    def replace_img(match):
        alt_text = match.group(1)
        url = match.group(2)
        return f'<a href="{url}" target="_blank"><img src="{url}" alt="{alt_text}" style="max-width: 100%; max-height: 200px; cursor: zoom-in;"></a>'
    
    text = re.sub(img_pattern, replace_img, text)
    
    # 处理普通URL
    url_pattern = r'(https?://[^\s<\)]+)'
    def replace_url(match):
        url = match.group(0)
        # 检查URL是否以图片扩展名结尾
        if url.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
            # 如果是图片，则显示为可点击的缩略图
            return f'<a href="{url}" target="_blank"><img src="{url}" alt="图片" style="max-width: 100%; max-height: 200px; cursor: zoom-in;"></a>'
        else:
            # 否则，仅显示为超链接
            return f'<a href="{url}" target="_blank">{url}</a>'
    
    text = re.sub(url_pattern, replace_url, text)
    
    return Markup(text)

@app.template_filter('datetime')
def format_datetime(value, format='%Y-%m-%d %H:%M'):
    """格式化日期时间"""
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return value
    return value.strftime(format) if value else ''

@app.route('/')
def index():
    """首页"""
    conn = get_db()
    cursor = conn.cursor()
    
    # 获取所有版块
    cursor.execute('SELECT * FROM forums ORDER BY order_num')
    forums = cursor.fetchall()
    
    # 获取最新主题
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

@app.route('/forum/<int:forum_id>')
def forum(forum_id):
    """版块页面"""
    conn = get_db()
    cursor = conn.cursor()
    
    # 获取版块信息
    cursor.execute('SELECT * FROM forums WHERE id = ?', (forum_id,))
    forum_info = cursor.fetchone()
    
    if not forum_info:
        flash('版块不存在')
        return redirect(url_for('index'))
    
    # 获取版块下的主题
    cursor.execute('''
        SELECT t.*, u.username as author_name
        FROM topics t
        JOIN users u ON t.user_id = u.id
        WHERE t.forum_id = ?
        ORDER BY t.created_at DESC
    ''', (forum_id,))
    topics = cursor.fetchall()
    
    conn.close()
    return render_template('forum.html', forum=forum_info, topics=topics)

@app.route('/topic/<int:topic_id>')
def topic(topic_id):
    """主题页面"""
    conn = get_db()
    cursor = conn.cursor()
    
    # 获取主题信息
    cursor.execute('''
        SELECT t.*, f.name as forum_name, u.username as author_name
        FROM topics t
        JOIN forums f ON t.forum_id = f.id
        JOIN users u ON t.user_id = u.id
        WHERE t.id = ?
    ''', (topic_id,))
    topic_info = cursor.fetchone()
    
    if not topic_info:
        flash('主题不存在')
        return redirect(url_for('index'))
    
    # 获取回复
    cursor.execute('''
        SELECT r.*, u.username as author_name
        FROM replies r
        JOIN users u ON r.user_id = u.id
        WHERE r.topic_id = ?
        ORDER BY r.created_at ASC
    ''', (topic_id,))
    replies = cursor.fetchall()
    
    # 更新浏览次数
    cursor.execute('UPDATE topics SET views = views + 1 WHERE id = ?', (topic_id,))
    conn.commit()
    
    conn.close()
    return render_template('topic.html', topic=topic_info, replies=replies)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """用户注册"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        
        conn = get_db()
        cursor = conn.cursor()
        
        # 检查用户名是否已存在
        cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
        if cursor.fetchone():
            flash('用户名已存在')
            return redirect(url_for('register'))
        
        # 检查邮箱是否已存在
        cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
        if cursor.fetchone():
            flash('邮箱已被注册')
            return redirect(url_for('register'))
        
        # 创建新用户
        cursor.execute('''
            INSERT INTO users (username, password, email, created_at)
            VALUES (?, ?, ?, ?)
        ''', (username, password, email, datetime.now()))
        conn.commit()
        conn.close()
        
        flash('注册成功，请登录')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """用户登录"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db()
        cursor = conn.cursor()
        
        # 验证用户
        cursor.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password))
        user = cursor.fetchone()
        
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            
            # 更新最后登录时间
            cursor.execute('UPDATE users SET last_login = ? WHERE id = ?', (datetime.now(), user['id']))
            conn.commit()
            conn.close()
            
            flash('登录成功')
            return redirect(url_for('index'))
        else:
            flash('用户名或密码错误')
            return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """用户登出"""
    session.clear()
    flash('已登出')
    return redirect(url_for('index'))

def allowed_file(filename):
    """检查文件类型是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_file(file):
    """通过Telegraph-Image服务上传文件"""
    if not (file and allowed_file(file.filename)):
        print("文件类型不允许或文件为空。")
        return None

    try:
        files = {'file': (secure_filename(file.filename), file.read(), file.mimetype)}
        response = requests.post(TELEGRAPH_IMAGE_UPLOAD_URL, files=files)
        response.raise_for_status()
        
        result = response.json()
        # The response is a list containing a dictionary
        if isinstance(result, list) and len(result) > 0 and result[0].get('src'):
            base_url = TELEGRAPH_IMAGE_UPLOAD_URL.rsplit('/', 1)[0]
            image_url = base_url + result[0]['src']
            print(f"图片上传成功，URL: {image_url}")
            return image_url
        else:
            error_message = result[0].get('error') if isinstance(result, list) and len(result) > 0 else '未知错误'
            print(f"Telegraph-Image 上传失败: {error_message}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"请求 Telegraph-Image 服务时出错: {str(e)}")
        return None
    except Exception as e:
        print(f"处理文件上传时出错: {str(e)}")
        return None

@app.route('/new_topic/<int:forum_id>', methods=['GET', 'POST'])
def new_topic(forum_id):
    """发布新主题"""
    if 'user_id' not in session:
        flash('请先登录')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        
        # 处理图片上传
        images = []
        if 'images' in request.files:
            files = request.files.getlist('images')
            for file in files:
                file_path = save_file(file)
                if file_path:
                    images.append(file_path)
        
        # 将图片路径添加到内容中
        if images:
            image_html = '\n'.join(images)
            content = f"{content}\n\n{image_html}"
        
        conn = get_db()
        cursor = conn.cursor()
        
        # 创建新主题
        cursor.execute('''
            INSERT INTO topics (forum_id, user_id, title, content, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (forum_id, session['user_id'], title, content, datetime.now(), datetime.now()))
        topic_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        
        flash('主题发布成功')
        return redirect(url_for('topic', topic_id=topic_id))
    
    return render_template('new_topic.html', forum_id=forum_id)

@app.route('/reply/<int:topic_id>', methods=['POST'])
def reply(topic_id):
    """发表回复"""
    if 'user_id' not in session:
        flash('请先登录')
        return redirect(url_for('login'))
    
    content = request.form['content']
    
    # 处理图片上传
    images = []
    if 'images' in request.files:
        files = request.files.getlist('images')
        for file in files:
            file_path = save_file(file)
            if file_path:
                images.append(file_path)
    
    # 将图片路径添加到内容中
    if images:
        image_html = '\n'.join(images)
        content = f"{content}\n\n{image_html}"
    
    conn = get_db()
    cursor = conn.cursor()
    
    # 创建回复
    cursor.execute('''
        INSERT INTO replies (topic_id, user_id, content, created_at)
        VALUES (?, ?, ?, ?)
    ''', (topic_id, session['user_id'], content, datetime.now()))
    reply_id = cursor.lastrowid
    
    # 更新主题回复数
    cursor.execute('UPDATE topics SET replies = replies + 1 WHERE id = ?', (topic_id,))
    
    conn.commit()
    conn.close()
    
    flash('回复成功')
    return redirect(url_for('topic', topic_id=topic_id))

if __name__ == '__main__':
    app.run(debug=True)
