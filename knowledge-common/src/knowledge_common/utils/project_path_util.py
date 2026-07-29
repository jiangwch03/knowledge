import os
import sys


def resolve_workspace_root() -> str | None:
    """
    从 knowledge_common 包位置回溯 workspace 根目录
    """
    try:
        # project_path_util.py 位于 knowledge-common/src/knowledge_common/utils/project_path_util.py
        # 回溯 3 层到达 knowledge-common/，再上一层即为 workspace 根
        util_dir = os.path.dirname(os.path.abspath(__file__))
        knowledge_common_dir = os.path.dirname(os.path.dirname(os.path.dirname(util_dir)))
        workspace_root = os.path.dirname(knowledge_common_dir)
        if os.path.isdir(workspace_root):
            return workspace_root
    except Exception:
        pass
    return None


def infer_current_project() -> str | None:
    """
    根据 sys.argv 推断当前启动的是哪个子项目
    """
    argv_str = ' '.join(sys.argv)
    if 'knowledge_admin' in argv_str or 'knowledge-admin' in argv_str:
        return 'knowledge-admin'
    if 'knowledge_content' in argv_str or 'knowledge-content' in argv_str:
        return 'knowledge-content'
    if 'knowledge_retrieval' in argv_str or 'knowledge-retrieval' in argv_str:
        return 'knowledge-retrieval'
    return None
