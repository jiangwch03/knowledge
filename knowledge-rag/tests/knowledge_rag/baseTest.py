from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / 'src' / 'configs' / '.env.dev'

if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=True)