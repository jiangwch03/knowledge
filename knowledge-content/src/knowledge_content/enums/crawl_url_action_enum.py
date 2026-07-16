from enum import Enum


class PendingUrlAction(str, Enum):
    """pending_url_action 待处理的 URL 变更动作枚举"""

    CONFIRM_URL_SWITCH = 'confirm_url_switch'  # URL 变更，需用户确认是否切换
    CHOOSE_ANALYSIS_OR_GENERATE = 'choose_analysis_or_generate'  # 有缓存，让用户选是否重新分析
