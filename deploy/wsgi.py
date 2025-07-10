import os
import sys

# 添加应用目录到Python路径
path = os.path.dirname(os.path.abspath(__file__))
if path not in sys.path:
    sys.path.append(path)

from web_app import app as application

# PythonAnywhere使用WSGI应用程序对象名称'application'
if __name__ == '__main__':
    application.run() 