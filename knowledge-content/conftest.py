import sys
from pathlib import Path

# 将 src 目录添加到 sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent
_SRC_PATH = _PROJECT_ROOT / 'src'
sys.path.insert(0, str(_SRC_PATH))
sys.path.insert(0, str(_PROJECT_ROOT))
