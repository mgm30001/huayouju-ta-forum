import os
import requests
import json
from bs4 import BeautifulSoup
from urllib.parse import urljoin

def analyze_site_structure():
    """分析网站结构"""
    base_url = 'https://bbs.tahua.net/'
    
    # 获取主页内容
    api_key = os.getenv('FIRECRAWL_API_KEY')
    if not api_key:
        raise ValueError("API key not found in environment variables")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    data = {
        'url': base_url,
        'formats': ['html'],
        'headers': headers
    }

    try:
        response = requests.post(
            'https://api.firecrawl.dev/v1/scrape',
            headers={'Authorization': f'Bearer {api_key}'},
            json=data
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success') and result.get('data', {}).get('html'):
                soup = BeautifulSoup(result['data']['html'], 'html.parser')
                
                # 分析网站结构
                site_structure = {
                    'template': {
                        'header': {
                            'logo': soup.find('div', class_='wp cl').find('a', class_='fl')['href'] if soup.find('div', class_='wp cl') else None,
                            'navigation': []
                        },
                        'footer': {
                            'copyright': soup.find('div', class_='wp cl').text if soup.find('div', class_='wp cl') else None,
                            'links': []
                        }
                    },
                    'database': {
                        'tables': [
                            {
                                'name': 'users',
                                'fields': [
                                    {'name': 'id', 'type': 'INT', 'primary': True},
                                    {'name': 'username', 'type': 'VARCHAR(50)', 'unique': True},
                                    {'name': 'password', 'type': 'VARCHAR(255)'},
                                    {'name': 'email', 'type': 'VARCHAR(100)', 'unique': True},
                                    {'name': 'avatar', 'type': 'VARCHAR(255)'},
                                    {'name': 'created_at', 'type': 'DATETIME'},
                                    {'name': 'last_login', 'type': 'DATETIME'},
                                    {'name': 'status', 'type': 'TINYINT'}
                                ]
                            },
                            {
                                'name': 'forums',
                                'fields': [
                                    {'name': 'id', 'type': 'INT', 'primary': True},
                                    {'name': 'name', 'type': 'VARCHAR(100)'},
                                    {'name': 'description', 'type': 'TEXT'},
                                    {'name': 'parent_id', 'type': 'INT', 'foreign_key': 'forums.id'},
                                    {'name': 'order', 'type': 'INT'},
                                    {'name': 'created_at', 'type': 'DATETIME'}
                                ]
                            },
                            {
                                'name': 'topics',
                                'fields': [
                                    {'name': 'id', 'type': 'INT', 'primary': True},
                                    {'name': 'forum_id', 'type': 'INT', 'foreign_key': 'forums.id'},
                                    {'name': 'user_id', 'type': 'INT', 'foreign_key': 'users.id'},
                                    {'name': 'title', 'type': 'VARCHAR(255)'},
                                    {'name': 'content', 'type': 'TEXT'},
                                    {'name': 'views', 'type': 'INT', 'default': 0},
                                    {'name': 'replies', 'type': 'INT', 'default': 0},
                                    {'name': 'created_at', 'type': 'DATETIME'},
                                    {'name': 'updated_at', 'type': 'DATETIME'},
                                    {'name': 'status', 'type': 'TINYINT'}
                                ]
                            },
                            {
                                'name': 'replies',
                                'fields': [
                                    {'name': 'id', 'type': 'INT', 'primary': True},
                                    {'name': 'topic_id', 'type': 'INT', 'foreign_key': 'topics.id'},
                                    {'name': 'user_id', 'type': 'INT', 'foreign_key': 'users.id'},
                                    {'name': 'content', 'type': 'TEXT'},
                                    {'name': 'created_at', 'type': 'DATETIME'},
                                    {'name': 'status', 'type': 'TINYINT'}
                                ]
                            },
                            {
                                'name': 'attachments',
                                'fields': [
                                    {'name': 'id', 'type': 'INT', 'primary': True},
                                    {'name': 'topic_id', 'type': 'INT', 'foreign_key': 'topics.id'},
                                    {'name': 'reply_id', 'type': 'INT', 'foreign_key': 'replies.id'},
                                    {'name': 'user_id', 'type': 'INT', 'foreign_key': 'users.id'},
                                    {'name': 'filename', 'type': 'VARCHAR(255)'},
                                    {'name': 'filepath', 'type': 'VARCHAR(255)'},
                                    {'name': 'filesize', 'type': 'INT'},
                                    {'name': 'created_at', 'type': 'DATETIME'}
                                ]
                            }
                        ]
                    },
                    'features': [
                        {
                            'name': '用户系统',
                            'description': '用户注册、登录、个人中心等功能',
                            'components': [
                                '注册表单',
                                '登录表单',
                                '找回密码',
                                '个人资料编辑',
                                '头像上传'
                            ]
                        },
                        {
                            'name': '论坛系统',
                            'description': '论坛基本功能',
                            'components': [
                                '版块管理',
                                '主题发布',
                                '回复功能',
                                '附件上传',
                                '搜索功能'
                            ]
                        },
                        {
                            'name': '管理功能',
                            'description': '管理员功能',
                            'components': [
                                '用户管理',
                                '版块管理',
                                '内容审核',
                                '系统设置'
                            ]
                        }
                    ]
                }
                
                # 保存分析结果
                with open('site_structure.json', 'w', encoding='utf-8') as f:
                    json.dump(site_structure, f, ensure_ascii=False, indent=2)
                print("网站结构分析完成，结果已保存到 site_structure.json")
                
                return site_structure
            else:
                print("获取网站内容失败")
                return None
        else:
            print(f"请求失败，状态码: {response.status_code}")
            return None
    except Exception as e:
        print(f"发生错误: {str(e)}")
        return None

if __name__ == '__main__':
    analyze_site_structure() 