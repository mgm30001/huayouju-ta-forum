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

## 许可证

MIT License 