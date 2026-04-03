import os
import logging
from datetime import datetime

LOG_DIR = os.path.expanduser('~/.claude/skills/ai-writer-lite/logs')
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, f'debug_{datetime.now().strftime("%Y%m%d")}.log')

import sys

# 配置 StreamHandler 使用 UTF-8 编码
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(logging.DEBUG)
stream_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
if sys.platform == 'win32':
    stream_handler.stream.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        stream_handler
    ]
)

logger = logging.getLogger('ai-writer-lite')

def log_debug(msg):
    logger.debug(msg)

def log_info(msg):
    logger.info(msg)

def log_error(msg):
    logger.error(msg)
