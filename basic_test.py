import os
import requests
import json
import time
from urllib.parse import urljoin
from bs4 import BeautifulSoup

def get_forum_sections(url):
    """获取论坛版块列表"""
    sections = [
        {'name': '综合区', 'url': 'forum.php?gid=1'},
        {'name': '多浆植物讨论区', 'url': 'forum.php?gid=653'},
        {'name': '苦苣苔科植物讨论区', 'url': 'forum.php?gid=73'},
        {'name': '专题区', 'url': 'forum.php?gid=2'},
        {'name': '专类区', 'url': 'forum.php?gid=649'},
        {'name': '分享交换转让区', 'url': 'forum.php?gid=72'},
        {'name': '休闲区', 'url': 'forum.php?gid=42'}
    ]
    return [(section['name'], urljoin(url, section['url'])) for section in sections]

def extract_forum_info(html_content):
    """从HTML中提取论坛信息"""
    soup = BeautifulSoup(html_content, 'html.parser')
    forums = []
    
    # 查找所有版块
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
                forums.append(forum_info)
    
    return forums

def scrape_forum_page(url, page=1, headers=None):
    """爬取论坛页面"""
    if not headers:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    
    api_key = os.getenv('FIRECRAWL_API_KEY')
    if not api_key:
        raise ValueError("API key not found in environment variables")

    data = {
        'url': url,
        'formats': ['html'],
        'headers': headers
    }

    max_retries = 3
    retry_delay = 25

    for attempt in range(max_retries):
        try:
            print(f"尝试第 {attempt + 1} 次爬取...")
            response = requests.post(
                'https://api.firecrawl.dev/v1/scrape',
                headers={'Authorization': f'Bearer {api_key}'},
                json=data
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success') and result.get('data', {}).get('html'):
                    forums = extract_forum_info(result['data']['html'])
                    return {'success': True, 'forums': forums}
                return {'success': False, 'error': 'No HTML content found'}
            elif response.status_code == 429:  # Rate limit
                print(f"Rate limit exceeded. 等待 {retry_delay} 秒后重试...")
                time.sleep(retry_delay)
                continue
            else:
                print(f"爬取失败，状态码: {response.status_code}")
                print(f"错误信息: {response.text}")
                time.sleep(retry_delay)
        except Exception as e:
            print(f"发生错误: {str(e)}")
            if attempt < max_retries - 1:
                print(f"等待 {retry_delay} 秒后重试...")
                time.sleep(retry_delay)
            else:
                print("达到最大重试次数，爬取失败")
                return {'success': False, 'error': str(e)}

def main():
    base_url = 'https://bbs.tahua.net/'
    sections = get_forum_sections(base_url)
    
    all_forums = {}
    for section_name, section_url in sections:
        print(f"\n开始爬取版块: {section_name}")
        print(f"版块URL: {section_url}")
        
        result = scrape_forum_page(section_url)
        if result['success']:
            all_forums[section_name] = result['forums']
            # 保存爬取结果
            filename = f"scraped_{section_name.replace('/', '_')}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(result['forums'], f, ensure_ascii=False, indent=2)
            print(f"保存爬取结果到: {filename}")
        else:
            print(f"爬取版块 {section_name} 失败: {result.get('error', 'Unknown error')}")
        
        # 在爬取下一个版块之前等待，以避免触发频率限制
        time.sleep(30)
    
    # 保存所有版块的数据
    with open('all_forums.json', 'w', encoding='utf-8') as f:
        json.dump(all_forums, f, ensure_ascii=False, indent=2)
    print("\n所有数据已保存到 all_forums.json")

if __name__ == '__main__':
    main()