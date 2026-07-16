"""业务异常定义与统一文案提取。

注意：所有自定义异常必须把文案挂到 Exception.args（super().__init__），
否则 str(e) 为空，Agent 工具 / 日志会吞掉真实错误信息。
"""


def format_exception_message(exc: BaseException, *, fallback: str | None = None) -> str:
    """
    提取可读异常文案，保证工具回包 / 落库从不返回空串。

    优先业务异常的 .message，其次 str(exc)，最后类型名。
    """
    msg = getattr(exc, 'message', None)
    if isinstance(msg, str) and msg.strip():
        return msg.strip()
    text = str(exc).strip() if exc is not None else ''
    if text:
        return text
    if fallback and fallback.strip():
        return fallback.strip()
    return type(exc).__name__


class LoginException(Exception):
    """
    自定义登录异常LoginException
    """

    def __init__(self, message: str | None = None, data: str | None = None) -> None:
        self.message = message or ''
        self.data = data
        super().__init__(self.message)


class AuthException(Exception):
    """
    自定义令牌异常AuthException
    """

    def __init__(self, message: str | None = None, data: str | None = None) -> None:
        self.message = message or ''
        self.data = data
        super().__init__(self.message)


class PermissionException(Exception):
    """
    自定义权限异常PermissionException
    """

    def __init__(self, message: str | None = None, data: str | None = None) -> None:
        self.message = message or ''
        self.data = data
        super().__init__(self.message)


class ServiceException(Exception):
    """
    自定义服务异常ServiceException
    """

    def __init__(self, message: str | None = None, data: str | None = None) -> None:
        self.message = message or ''
        self.data = data
        # 必须挂到 Exception.args，否则 str(e) 为空，工具层/日志会吞掉真实错误信息
        super().__init__(self.message)


class ServiceWarning(Exception):
    """
    自定义服务警告ServiceWarning
    """

    def __init__(self, message: str | None = None, data: str | None = None) -> None:
        self.message = message or ''
        self.data = data
        super().__init__(self.message)


class ModelValidatorException(Exception):
    """
    自定义模型校验异常ModelValidatorException
    """

    def __init__(self, message: str | None = None, data: str | None = None) -> None:
        self.message = message or ''
        self.data = data
        super().__init__(self.message)
