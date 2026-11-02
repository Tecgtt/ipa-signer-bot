import os

# Optional dotenv loader without hard dependency
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_file):
        try:
            with open(env_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip()
                        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                            v = v[1:-1]
                        os.environ.setdefault(k, v)
        except Exception:
            pass

BOT_TOKEN = os.getenv("BOT_TOKEN", "8682648198:AAEdBKAgP0779Pv5EgyM5MpkGAyMIWrxA1Q")

# Admin configuration (support @yqios and @yqis)
ADMIN_USERNAMES = [
    u.strip().lstrip("@").lower()
    for u in os.getenv("ADMIN_USERNAMES", "yqios,yqis").split(",")
    if u.strip()
]

ADMIN_IDS = [
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()
]

# Path to zsign binary
ZSIGN_PATH = os.getenv("ZSIGN_PATH", "zsign")

# Directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
TEMP_DIR = os.path.join(BASE_DIR, "temp")
CERTS_DIR = os.path.join(DATA_DIR, "certs")
ICONS_DIR = os.path.join(DATA_DIR, "icons")
SIGNED_DIR = os.path.join(DATA_DIR, "signed")

for d in [DATA_DIR, TEMP_DIR, CERTS_DIR, ICONS_DIR, SIGNED_DIR]:
    os.makedirs(d, exist_ok=True)

# Maximum file size for direct Telegram upload in MB (Telegram hard limit for bots is 50MB)
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))

# Built-in Web Server for Unlimited Size Downloads (> 2GB files)
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8080"))
PUBLIC_URL = os.getenv("PUBLIC_URL", "")  # If set, e.g. http://your-ip:8080 or domain
