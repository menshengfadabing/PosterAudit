"""前端配置"""
import os

API_BASE_URL    = os.getenv("API_BASE_URL", "http://localhost:8000")
API_KEY         = os.getenv("API_KEY", "")
POLL_INTERVAL   = 2     # 轮询间隔（秒）
PAGE_SIZE       = 20    # 历史记录每页数量
REQUEST_TIMEOUT = 120.0 # 默认请求超时
