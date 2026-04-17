from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
PRESETS_DIR = DATA_DIR / "presets"
SETTINGS_DIR = PRESETS_DIR / "settings"
TEMPLATES_DIR = PRESETS_DIR / "templates"
DEFAULTS_DIR = Path(__file__).resolve().parent.parent / "defaults"
CLIENT_DIST = PROJECT_ROOT / "client" / "dist"
DB_PATH = DATA_DIR / "pendrift.db"

LLAMA_SERVER_DEFAULT_PORT = 8080
