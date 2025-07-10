import MySQLdb
import sqlite3
import os

def init_mysql_tables(mysql_cur):
    """初始化MySQL数据库表结构"""
    # 创建用户表
    mysql_cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) UNIQUE,
            password VARCHAR(255),
            email VARCHAR(100) UNIQUE,
            avatar VARCHAR(255),
            created_at DATETIME,
            last_login DATETIME,
            status TINYINT DEFAULT 1
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
    ''')
    print("用户表创建成功！")
    
    # 创建版块表
    mysql_cur.execute('''
        CREATE TABLE IF NOT EXISTS forums (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100),
            description TEXT,
            parent_id INT,
            order_num INT,
            created_at DATETIME
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
    ''')
    print("版块表创建成功！")
    
    # 创建主题表
    mysql_cur.execute('''
        CREATE TABLE IF NOT EXISTS topics (
            id INT AUTO_INCREMENT PRIMARY KEY,
            forum_id INT,
            user_id INT,
            title VARCHAR(255),
            content TEXT,
            views INT DEFAULT 0,
            replies INT DEFAULT 0,
            created_at DATETIME,
            updated_at DATETIME,
            status TINYINT DEFAULT 1
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
    ''')
    print("主题表创建成功！")
    
    # 创建回复表
    mysql_cur.execute('''
        CREATE TABLE IF NOT EXISTS replies (
            id INT AUTO_INCREMENT PRIMARY KEY,
            topic_id INT,
            user_id INT,
            content TEXT,
            created_at DATETIME,
            status TINYINT DEFAULT 1
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
    ''')
    print("回复表创建成功！")
    
    # 创建附件表
    mysql_cur.execute('''
        CREATE TABLE IF NOT EXISTS attachments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            topic_id INT,
            reply_id INT,
            user_id INT,
            filename VARCHAR(255),
            filepath VARCHAR(255),
            filesize INT,
            created_at DATETIME
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
    ''')
    print("附件表创建成功！")

def migrate_data():
    """从SQLite迁移数据到MySQL"""
    try:
        print("开始连接MySQL数据库...")
        mysql_conn = MySQLdb.connect(
            host='mgm3000.mysql.pythonanywhere-services.com',
            user='mgm3000',
            passwd='12131213mm',
            db='mgm3000$forum',
            charset='utf8mb4',
            port=3306
        )
        print("MySQL数据库连接成功！")
        mysql_cur = mysql_conn.cursor()
        
        # 初始化MySQL表结构
        print("开始创建MySQL数据库表...")
        init_mysql_tables(mysql_cur)
        print("MySQL数据库表创建完成！")
        
        print("开始连接SQLite数据库...")
        sqlite_conn = sqlite3.connect('forum.db')
        print("SQLite数据库连接成功！")
        sqlite_cur = sqlite_conn.cursor()
        
        # 迁移用户表数据
        print("迁移用户表数据...")
        sqlite_cur.execute("SELECT * FROM users")
        for row in sqlite_cur.fetchall():
            mysql_cur.execute(
                "INSERT INTO users (id, username, password, email, avatar, created_at, last_login, status) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                row
            )
        print("用户表数据迁移完成！")
        
        # 迁移版块表数据
        print("迁移版块表数据...")
        sqlite_cur.execute("SELECT * FROM forums")
        for row in sqlite_cur.fetchall():
            mysql_cur.execute(
                "INSERT INTO forums (id, name, description, parent_id, order_num, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                row
            )
        print("版块表数据迁移完成！")
        
        # 迁移主题表数据
        print("迁移主题表数据...")
        sqlite_cur.execute("SELECT * FROM topics")
        for row in sqlite_cur.fetchall():
            mysql_cur.execute(
                "INSERT INTO topics (id, forum_id, user_id, title, content, views, replies, created_at, updated_at, status) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                row
            )
        print("主题表数据迁移完成！")
        
        # 迁移回复表数据
        print("迁移回复表数据...")
        sqlite_cur.execute("SELECT * FROM replies")
        for row in sqlite_cur.fetchall():
            mysql_cur.execute(
                "INSERT INTO replies (id, topic_id, user_id, content, created_at, status) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                row
            )
        print("回复表数据迁移完成！")
        
        # 迁移附件表数据
        print("迁移附件表数据...")
        sqlite_cur.execute("SELECT * FROM attachments")
        for row in sqlite_cur.fetchall():
            mysql_cur.execute(
                "INSERT INTO attachments (id, topic_id, reply_id, user_id, filename, filepath, filesize, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                row
            )
        print("附件表数据迁移完成！")
        
        mysql_conn.commit()
        print("所有数据迁移完成！")
        
    except MySQLdb.Error as e:
        print(f"MySQL数据库错误：{str(e)}")
    except sqlite3.Error as e:
        print(f"SQLite数据库错误：{str(e)}")
    except Exception as e:
        print(f"发生错误：{str(e)}")
    finally:
        if 'mysql_conn' in locals():
            mysql_conn.close()
        if 'sqlite_conn' in locals():
            sqlite_conn.close()
        print("数据库连接已关闭")

if __name__ == '__main__':
    migrate_data() 