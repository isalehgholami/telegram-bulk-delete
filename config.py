import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")
SESSION_NAME = os.getenv("TG_SESSION", "userbot")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8686"))

# Proxy: socks5://user:pass@host:port or http://host:port
PROXY_URL = os.getenv("TG_PROXY", "")
