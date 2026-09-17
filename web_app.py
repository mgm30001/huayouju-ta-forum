from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import sqlite3
from datetime import datetime
import os
from werkzeug.utils import secure_filename
import requests
import re
from markupsafe import Markup
import markdown

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

# AI 资料获取接口（llms.txt / 主题Markdown / RSS / API，详见 ai_access.py）
from ai_access import ai_bp
app.register_blueprint(ai_bp)

def get_db():
    """获取SQLite数据库连接"""
    conn = sqlite3.connect('forum.db', detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    return conn

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

@app.route('/upload_image', methods=['POST'])
def upload_image():
    """将图片上传到图床"""
    if 'file' not in request.files:
        return jsonify({'code': 400, 'message': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'code': 400, 'message': 'No selected file'}), 400

    if file and allowed_file(file.filename):
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
                return jsonify({'code': 500, 'message': 'Failed to upload image to image bed'}), 500
                
        except Exception as e:
            print(f"Error uploading file to image bed: {str(e)}")
            return jsonify({'code': 500, 'message': f'Error uploading file to image bed: {str(e)}'}), 500
            
    print("Invalid file or no file part in request.")
    return jsonify({'code': 400, 'message': 'Invalid file'}), 400

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

@app.route('/forum/<int:forum_id>')
def forum(forum_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM forums WHERE id = ?', (forum_id,))
    forum = cursor.fetchone()
    if not forum:
        flash('版块不存在')
        return redirect(url_for('index'))
    cursor.execute('''
        SELECT t.*, u.username as author_name
        FROM topics t
        JOIN users u ON t.user_id = u.id
        WHERE t.forum_id = ?
        ORDER BY t.created_at DESC
    ''', (forum_id,))
    topics = cursor.fetchall()
    conn.close()
    return render_template('forum.html', forum=forum, topics=topics)

def convert_markdown_to_html(content):
    """将Markdown内容转换为HTML"""
    return Markup(markdown.markdown(content, extensions=['fenced_code', 'tables', 'extra']))

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
    conn.commit()
    conn.close()
    
    return render_template('topic.html', topic=topic, replies=replies)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
        if cursor.fetchone():
            flash('用户名已存在')
            return redirect(url_for('register'))
        cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
        if cursor.fetchone():
            flash('邮箱已被注册')
            return redirect(url_for('register'))
        cursor.execute('INSERT INTO users (username, password, email, created_at) VALUES (?, ?, ?, ?)',
                       (username, password, email, datetime.now()))
        conn.commit()
        conn.close()
        flash('注册成功，请登录')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password))
        user = cursor.fetchone()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
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
    session.clear()
    flash('已登出')
    return redirect(url_for('index'))

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    """检查文件类型是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_file(file):
    """通过图床服务上传文件"""
    if not (file and allowed_file(file.filename)):
        print("文件类型不允许或文件为空。")
        return None

    try:
        # 重置文件指针到开始位置，确保可以读取
        file.seek(0)
        files = {'file': (secure_filename(file.filename), file.read(), file.mimetype)}
        
        print(f"正在上传文件到图床: {file.filename}")
        response = requests.post('https://tu.moome.dpdns.org/upload', files=files, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        print(f"图床API响应: {result}")
        
        if isinstance(result, list) and len(result) > 0:
            if result[0].get('url'):
                image_url = result[0]['url']
                print(f"图片上传成功，URL: {image_url}")
                return image_url
            elif result[0].get('src'):
                base_url = 'https://tu.moome.dpdns.org'
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
    cursor.execute('INSERT INTO replies (topic_id, user_id, content, created_at) VALUES (?, ?, ?, ?)',
                   (topic_id, session['user_id'], content, datetime.now()))
    cursor.execute('UPDATE topics SET replies = replies + 1 WHERE id = ?', (topic_id,))
    conn.commit()
    conn.close()
    flash('回复成功')
    return redirect(url_for('topic', topic_id=topic_id))

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

@app.route('/deploy/static/<path:filename>')
def serve_deploy_static(filename):
    return send_from_directory(os.path.join(app.root_path, 'deploy', 'static'), filename)

@app.route('/debug/replies')
def debug_replies():
    """临时路由，用于调试回复内容"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, content FROM replies ORDER BY id DESC LIMIT 10')
    replies = cursor.fetchall()
    conn.close()
    
    output = []
    for reply in replies:
        output.append(f"ID: {reply['id']}")
        output.append(f"Content (raw): {reply['content']}")
        output.append(f"Content (repr): {repr(reply['content'])}")
        output.append("")
    
    return "<pre>" + "\n".join(output) + "</pre>"

if __name__ == '__main__':
    app.run(debug=True)
