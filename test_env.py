import os
api_key = os.getenv('FIRECRAWL_API_KEY')
print(f"当前API密钥：{api_key if api_key else '未检测到环境变量'}") 