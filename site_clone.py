import os
import requests
import json
import time
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import sqlite3
from datetime import datetime

class SiteCloner:
    def __init__(self):
        self.base_url = 'https://bbs.tahua.net/'
        self.api_key = os.getenv('FIRECRAWL_API_KEY')
        if not self.api_key:
            raise ValueError("API key not found in environment variables")
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # 创建数据库连接
        self.conn = sqlite3.connect('forum.db')
        self.cursor = self.conn.cursor()
        self.setup_database()
    
    def setup_database(self):
        """设置数据库表结构"""
        # 创建用户表
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username VARCHAR(50) UNIQUE,
                password VARCHAR(255),
                email VARCHAR(100) UNIQUE,
                avatar VARCHAR(255),
                created_at DATETIME,
                last_login DATETIME,
                status TINYINT DEFAULT 1
            )
        ''')
        
        # 创建版块表
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS forums (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100),
                description TEXT,
                parent_id INTEGER,
                order_num INTEGER,
                created_at DATETIME,
                FOREIGN KEY (parent_id) REFERENCES forums (id)
            )
        ''')
        
        # 创建主题表
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                forum_id INTEGER,
                user_id INTEGER,
                title VARCHAR(255),
                content TEXT,
                views INTEGER DEFAULT 0,
                replies INTEGER DEFAULT 0,
                created_at DATETIME,
                updated_at DATETIME,
                status TINYINT DEFAULT 1,
                FOREIGN KEY (forum_id) REFERENCES forums (id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # 创建回复表
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER,
                user_id INTEGER,
                content TEXT,
                created_at DATETIME,
                status TINYINT DEFAULT 1,
                FOREIGN KEY (topic_id) REFERENCES topics (id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # 创建附件表
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER,
                reply_id INTEGER,
                user_id INTEGER,
                filename VARCHAR(255),
                filepath VARCHAR(255),
                filesize INTEGER,
                created_at DATETIME,
                FOREIGN KEY (topic_id) REFERENCES topics (id),
                FOREIGN KEY (reply_id) REFERENCES replies (id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        self.conn.commit()
    
    def scrape_page(self, url):
        """爬取页面内容"""
        data = {
            'url': url,
            'formats': ['html'],
            'headers': self.headers
        }
        
        try:
            response = requests.post(
                'https://api.firecrawl.dev/v1/scrape',
                headers={'Authorization': f'Bearer {self.api_key}'},
                json=data
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success') and result.get('data', {}).get('html'):
                    return result['data']['html']
            elif response.status_code == 429:
                print(f"Rate limit exceeded. 等待25秒后重试...")
                time.sleep(25)
                return self.scrape_page(url)
            else:
                print(f"请求失败，状态码: {response.status_code}")
                return None
        except Exception as e:
            print(f"发生错误: {str(e)}")
            return None
    
    def clone_forum(self, forum_url):
        """克隆论坛内容"""
        html_content = self.scrape_page(forum_url)
        if not html_content:
            return False
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 提取版块信息
        forum_tables = soup.find_all('table', class_='fl_tb')
        for table in forum_tables:
            for tr in table.find_all('tr'):
                forum_info = {}
                
                # 获取版块名称和链接
                name_td = tr.find('td', class_=None)
                if name_td and name_td.h2:
                    forum_link = name_td.h2.a
                    if forum_link:
                        forum_info['name'] = forum_link.text
                        forum_info['url'] = forum_link['href']
                    
                    # 获取版块描述
                    desc = name_td.find('p', class_='xg2')
                    if desc:
                        forum_info['description'] = desc.text
                    
                    # 获取版主信息
                    moderators = name_td.find_all('a', class_='notabs')
                    if moderators:
                        forum_info['moderators'] = [mod.text for mod in moderators]
                
                # 获取统计信息
                stats_td = tr.find('td', class_='fl_i')
                if stats_td:
                    stats = stats_td.text.strip().split('/')
                    if len(stats) == 2:
                        forum_info['topics'] = stats[0].strip()
                        forum_info['posts'] = stats[1].strip()
                
                # 获取最新帖子信息
                last_post_td = tr.find('td', class_='fl_by')
                if last_post_td:
                    last_post = last_post_td.find('a', class_='xi2')
                    if last_post:
                        forum_info['last_post'] = {
                            'title': last_post.text,
                            'url': last_post['href']
                        }
                
                if forum_info:
                    # 保存版块信息到数据库
                    self.cursor.execute('''
                        INSERT INTO forums (name, description, created_at)
                        VALUES (?, ?, ?)
                    ''', (
                        forum_info['name'],
                        forum_info.get('description', ''),
                        datetime.now()
                    ))
                    forum_id = self.cursor.lastrowid
                    
                    # 克隆最新帖子
                    if 'last_post' in forum_info:
                        self.clone_topic(forum_info['last_post']['url'], forum_id)
        
        self.conn.commit()
        return True
    
    def clone_topic(self, topic_url, forum_id):
        """克隆主题内容"""
        html_content = self.scrape_page(topic_url)
        if not html_content:
            return False
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 提取主题信息
        topic_info = {}
        
        # 获取主题标题
        title_h1 = soup.find('h1', class_='ts')
        if title_h1:
            topic_info['title'] = title_h1.text.strip()
        
        # 获取主题内容
        content_div = soup.find('div', class_='t_f')
        if content_div:
            topic_info['content'] = content_div.text.strip()
        else:
            topic_info['content'] = '内容不可用'  # 设置默认内容
        
        # 获取作者信息
        author_a = soup.find('a', class_='xw1')
        if author_a:
            topic_info['author'] = author_a.text.strip()
            # 创建用户
            self.cursor.execute('''
                INSERT OR IGNORE INTO users (username, created_at)
                VALUES (?, ?)
            ''', (topic_info['author'], datetime.now()))
            self.conn.commit()
            
            # 获取用户ID
            self.cursor.execute('SELECT id FROM users WHERE username = ?', (topic_info['author'],))
            user_row = self.cursor.fetchone()
            topic_info['user_id'] = user_row[0] if user_row else 1  # 如果找不到用户，使用ID 1
        else:
            topic_info['author'] = '匿名用户'
            topic_info['user_id'] = 1
        
        if topic_info:
            # 保存主题信息到数据库
            self.cursor.execute('''
                INSERT INTO topics (forum_id, user_id, title, content, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                forum_id,
                topic_info['user_id'],
                topic_info.get('title', '无标题'),
                topic_info.get('content', '内容不可用'),
                datetime.now(),
                datetime.now()
            ))
            topic_id = self.cursor.lastrowid
            
            # 克隆回复
            self.clone_replies(topic_url, topic_id)
        
        return True
    
    def clone_replies(self, topic_url, topic_id):
        """克隆回复内容"""
        html_content = self.scrape_page(topic_url)
        if not html_content:
            return False
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 提取回复信息
        replies = soup.find_all('div', class_='t_f')
        for reply in replies:
            reply_info = {}
            
            # 获取回复内容
            reply_info['content'] = reply.text.strip()
            
            # 获取回复作者
            author_a = reply.find_previous('a', class_='xw1')
            if author_a:
                reply_info['author'] = author_a.text.strip()
            
            if reply_info:
                # 保存回复信息到数据库
                self.cursor.execute('''
                    INSERT INTO replies (topic_id, content, created_at)
                    VALUES (?, ?, ?)
                ''', (
                    topic_id,
                    reply_info['content'],
                    datetime.now()
                ))
        
        return True
    
    def close(self):
        """关闭数据库连接"""
        self.conn.close()

def main():
    cloner = SiteCloner()
    try:
        # 克隆主页
        print("开始克隆主页...")
        cloner.clone_forum('https://bbs.tahua.net/')
        
        # 克隆各个版块
        sections = [
            {'name': '综合区', 'url': 'forum.php?gid=1'},
            {'name': '多浆植物讨论区', 'url': 'forum.php?gid=653'},
            {'name': '苦苣苔科植物讨论区', 'url': 'forum.php?gid=73'},
            {'name': '专题区', 'url': 'forum.php?gid=2'},
            {'name': '专类区', 'url': 'forum.php?gid=649'},
            {'name': '分享交换转让区', 'url': 'forum.php?gid=72'},
            {'name': '休闲区', 'url': 'forum.php?gid=42'}
        ]
        
        for section in sections:
            print(f"\n开始克隆版块: {section['name']}")
            cloner.clone_forum(urljoin('https://bbs.tahua.net/', section['url']))
            time.sleep(30)  # 避免触发频率限制
        
        print("\n网站克隆完成！")
    finally:
        cloner.close()

if __name__ == '__main__':
    main() 