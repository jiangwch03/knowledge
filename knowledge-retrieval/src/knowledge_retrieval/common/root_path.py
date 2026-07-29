from pathlib import Path


def _find_root() -> Path:
    current = Path(__file__).resolve()
    for path in [current, *current.parents]:
        if (path / 'pyproject.toml').exists():
            return path
        if (path / 'requirements.txt').exists():
            return path
    raise RuntimeError('未找到项目根目录（缺少 pyproject.toml）')


def _get_top_package() -> str:
    if not __package__:
        return Path(__file__).resolve().parent.parent.name
    return __package__.split('.')[0] if __package__ else __name__.split('.')[0]


PROJECT_ROOT = _find_root()
SRC_ROOT = PROJECT_ROOT / 'src'
CONFIG_ROOT = SRC_ROOT / 'configs'
CODE_ROOT = SRC_ROOT / _get_top_package()
