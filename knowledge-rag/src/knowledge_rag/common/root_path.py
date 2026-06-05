import os
from pathlib import Path

# 或者更稳健：查找标记文件
def _find_root() -> Path:
    current = Path(__file__).resolve()
    for path in [current, *current.parents]:
        if (path / "pyproject.toml").exists():
            return path
        # 兼容老旧项目
        if (path / "requirements.txt").exists():
            return path

    raise RuntimeError("未找到项目根目录（缺少 pyproject.toml）")
def _get_top_package() -> str:
    """获取当前模块的顶层包名"""
    if not __package__ :# or __package__ == ""
        # 上溯 2 层到 knowledge_admin，取目录名
        return Path(__file__).resolve().parent.parent.name
    return __package__.split('.')[0] if __package__ else __name__.split('.')[0]


PROJECT_ROOT = _find_root()
SRC_ROOT = PROJECT_ROOT / "src"
CONFIG_ROOT = SRC_ROOT / "configs"
CODE_ROOT = SRC_ROOT / _get_top_package()

if __name__ == '__main__':
    print(f"项目路径: {PROJECT_ROOT}")
    print(f"SRC路径：{SRC_ROOT}")
    print(f"包开始路径: {CODE_ROOT}")
    print(f"配置路径: {CONFIG_ROOT}")