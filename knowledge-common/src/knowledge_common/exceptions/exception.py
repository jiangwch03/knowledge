class LoginException(Exception):
    """
    自定义登录异常LoginException
    """

    def __init__(self, message: str | None = None, data: str | None = None) -> None:
        self.message = message
        self.data = data


class AuthException(Exception):
    """
    自定义令牌异常AuthException
    """

    def __init__(self, message: str | None = None, data: str | None = None) -> None:
        self.message = message
        self.data = data


class PermissionException(Exception):
    """
    自定义权限异常PermissionException
    """

    def __init__(self, message: str | None = None, data: str | None = None) -> None:
        self.message = message
        self.data = data


class ServiceException(Exception):
    """
    自定义服务异常ServiceException
    """

    def __init__(self, message: str | None = None, data: str | None = None) -> None:
        self.message = message
        self.data = data


class ServiceWarning(Exception):
    """
    自定义服务警告ServiceWarning
    """

    def __init__(self, message: str | None = None, data: str | None = None) -> None:
        self.message = message
        self.data = data


class ModelValidatorException(Exception):
    """
    自定义模型校验异常ModelValidatorException
    """

    def __init__(self, message: str | None = None, data: str | None = None) -> None:
        self.message = message
        self.data = data
