
class CommonConstant:
    """
    常用常量

    PASSWORD_ERROR_COUNT: 密码错误次数
    WWW: www主域
    HTTP: http请求
    HTTPS: https请求
    LOOKUP_RMI: RMI远程方法调用
    LOOKUP_LDAP: LDAP远程方法调用
    LOOKUP_LDAPS: LDAPS远程方法调用
    YES: 是否为系统默认（是）
    NO: 是否为系统默认（否）
    DEPT_NORMAL: 部门正常状态
    DEPT_DISABLE: 部门停用状态
    UNIQUE: 校验是否唯一的返回标识（是）
    NOT_UNIQUE: 校验是否唯一的返回标识（否）
    """

    PASSWORD_ERROR_COUNT = 5
    WWW = 'www.'
    HTTP = 'http://'
    HTTPS = 'https://'
    LOOKUP_RMI = 'rmi:'
    LOOKUP_LDAP = 'ldap:'
    LOOKUP_LDAPS = 'ldaps:'
    YES = 'Y'
    NO = 'N'
    DEPT_NORMAL = '0'
    DEPT_DISABLE = '1'
    UNIQUE = True
    NOT_UNIQUE = False


class HttpStatusConstant:
    """
    返回状态码

    SUCCESS: 操作成功
    CREATED: 对象创建成功
    ACCEPTED: 请求已经被接受
    NO_CONTENT: 操作已经执行成功，但是没有返回数据
    MOVED_PERM: 资源已被移除
    SEE_OTHER: 重定向
    NOT_MODIFIED: 资源没有被修改
    BAD_REQUEST: 参数列表错误（缺少，格式不匹配）
    UNAUTHORIZED: 未授权
    FORBIDDEN: 访问受限，授权过期
    NOT_FOUND: 资源，服务未找到
    BAD_METHOD: 不允许的http方法
    CONFLICT: 资源冲突，或者资源被锁
    UNSUPPORTED_TYPE: 不支持的数据，媒体类型
    TOO_MANY_REQUESTS: 请求过于频繁
    ERROR: 系统内部错误
    NOT_IMPLEMENTED: 接口未实现
    WARN: 系统警告消息
    """

    SUCCESS = 200
    CREATED = 201
    ACCEPTED = 202
    NO_CONTENT = 204
    MOVED_PERM = 301
    SEE_OTHER = 303
    NOT_MODIFIED = 304
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    BAD_METHOD = 405
    CONFLICT = 409
    UNSUPPORTED_TYPE = 415
    TOO_MANY_REQUESTS = 429
    ERROR = 500
    NOT_IMPLEMENTED = 501
    WARN = 601


class JobConstant:
    """
    定时任务常量

    JOB_ERROR_LIST: 定时任务禁止调用模块及违规字符串列表
    JOB_WHITE_LIST: 定时任务允许调用模块列表
    """

    JOB_ERROR_LIST = [
        'app',
        'config',
        'exceptions',
        'import ',
        'middlewares',
        'open(',
        'os.',
        'server',
        'sub_applications',
        'subprocess.',
        'sys.',
        'utils',
        'while ',
        '__import__',
        '"',
        "'",
        ',',
        '?',
        ':',
        ';',
        '/',
        '|',
        '+',
        '-',
        '=',
        '~',
        '!',
        '#',
        '$',
        '%',
        '^',
        '&',
        '*',
        '<',
        '>',
        '(',
        ')',
        '[',
        ']',
        '{',
        '}',
        ' ',
    ]
    JOB_WHITE_LIST = ['knowledge_content','knowledge_admin','knowledge_agent']


class LockConstant:
    """
    分布式锁常量（已废弃，请使用 knowledge_common.redis.key.LockKey）

    保留此类仅为向后兼容，新代码应使用 LockKey：
        from knowledge_common.redis.key import LockKey
        key = LockKey.app_startup_key('knowledge-admin')
    """

    from knowledge_common.redis.key import LockKey as _LockKey

    APP_STARTUP_LOCK_KEY = _LockKey.app_startup_key()
    LOCK_EXPIRE_SECONDS = 60
    LOCK_RENEWAL_INTERVAL = 20


class ApiNamespace:
    """
    接口注解通用命名空间常量

    这一组常量统一提供给 `ApiCache`、`ApiCacheEvict`、`ApiRateLimit`
    等接口注解使用，用同一套“模块:功能”命名规则收敛缓存和限流场景。

    LOGIN: 登录接口命名空间
    REGISTER: 注册接口命名空间
    LOGIN_USER_INFO: 登录用户信息接口命名空间
    LOGIN_USER_ROUTERS: 登录用户路由接口命名空间
    CAPTCHA_IMAGE: 图片验证码接口命名空间
    COMMON_UPLOAD: 通用上传接口命名空间
    TRANSPORT_CRYPTO_PUBLIC_KEY: 传输层加密公钥接口命名空间
    TRANSPORT_CRYPTO_FRONTEND_CONFIG: 传输层加密前端配置接口命名空间

    MONITOR_CACHE_CLEAR_NAME: 缓存名称清理接口命名空间
    MONITOR_CACHE_CLEAR_KEY: 缓存键清理接口命名空间
    MONITOR_CACHE_CLEAR_ALL: 缓存全量清理接口命名空间
    MONITOR_ONLINE_FORCE_LOGOUT: 在线用户强退接口命名空间
    MONITOR_OPERLOG_CLEAN: 操作日志清空接口命名空间
    MONITOR_OPERLOG_DELETE: 操作日志删除接口命名空间
    MONITOR_OPERLOG_EXPORT: 操作日志导出接口命名空间
    MONITOR_LOGININFO_CLEAN: 登录日志清空接口命名空间
    MONITOR_LOGININFO_DELETE: 登录日志删除接口命名空间
    MONITOR_LOGININFO_UNLOCK: 账户解锁接口命名空间
    MONITOR_LOGININFO_EXPORT: 登录日志导出接口命名空间
    MONITOR_JOB_LIST: 定时任务分页列表接口命名空间
    MONITOR_JOB_DETAIL: 定时任务详情接口命名空间
    MONITOR_JOB_RUN: 定时任务执行接口命名空间
    MONITOR_JOB_DELETE: 定时任务删除接口命名空间
    MONITOR_JOB_EXPORT: 定时任务导出接口命名空间
    MONITOR_JOB_LOG_CLEAN: 定时任务日志清空接口命名空间
    MONITOR_JOB_LOG_DELETE: 定时任务日志删除接口命名空间
    MONITOR_JOB_LOG_EXPORT: 定时任务日志导出接口命名空间

    SYSTEM_DEPT_EDIT_TREE: 部门编辑树接口命名空间
    SYSTEM_DEPT_LIST: 部门列表接口命名空间
    SYSTEM_DEPT_DETAIL: 部门详情接口命名空间
    SYSTEM_CONFIG_LIST: 参数配置列表接口命名空间
    SYSTEM_CONFIG_DETAIL: 参数配置详情接口命名空间
    SYSTEM_CONFIG_REFRESH_CACHE: 参数缓存刷新接口命名空间
    SYSTEM_CONFIG_EXPORT: 参数导出接口命名空间
    SYSTEM_DICT_TYPE_LIST: 字典类型列表接口命名空间
    SYSTEM_DICT_TYPE_OPTIONS: 字典类型选项接口命名空间
    SYSTEM_DICT_TYPE_DETAIL: 字典类型详情接口命名空间
    SYSTEM_DICT_REFRESH_CACHE: 字典缓存刷新接口命名空间
    SYSTEM_DICT_TYPE_EXPORT: 字典类型导出接口命名空间
    SYSTEM_DICT_DATA_LIST: 字典数据列表接口命名空间
    SYSTEM_DICT_DATA_DETAIL: 字典数据详情接口命名空间
    SYSTEM_DICT_DATA_EXPORT: 字典数据导出接口命名空间
    SYSTEM_MENU_TREE: 菜单树接口命名空间
    SYSTEM_MENU_ROLE_TREE: 角色菜单树接口命名空间
    SYSTEM_MENU_LIST: 菜单分页列表接口命名空间
    SYSTEM_MENU_DETAIL: 菜单详情接口命名空间
    SYSTEM_NOTICE_LIST: 通知公告列表接口命名空间
    SYSTEM_NOTICE_DETAIL: 通知公告详情接口命名空间
    SYSTEM_POST_LIST: 岗位列表接口命名空间
    SYSTEM_POST_DETAIL: 岗位详情接口命名空间
    SYSTEM_POST_EXPORT: 岗位导出接口命名空间
    SYSTEM_ROLE_DEPT_TREE: 角色部门树接口命名空间
    SYSTEM_ROLE_LIST: 角色列表接口命名空间
    SYSTEM_ROLE_DETAIL: 角色详情接口命名空间
    SYSTEM_ROLE_ALLOCATED_USER_LIST: 已分配用户角色列表接口命名空间
    SYSTEM_ROLE_UNALLOCATED_USER_LIST: 未分配用户角色列表接口命名空间
    SYSTEM_ROLE_EXPORT: 角色导出接口命名空间
    SYSTEM_ROLE_AUTH_USER_SELECT_ALL: 角色批量分配用户接口命名空间
    SYSTEM_ROLE_AUTH_USER_CANCEL: 角色取消分配用户接口命名空间
    SYSTEM_ROLE_AUTH_USER_CANCEL_ALL: 角色批量取消分配用户接口命名空间
    SYSTEM_USER_DEPT_TREE: 用户部门树接口命名空间
    SYSTEM_USER_LIST: 用户列表接口命名空间
    SYSTEM_USER_PROFILE: 用户个人信息接口命名空间
    SYSTEM_USER_DETAIL: 用户详情接口命名空间
    SYSTEM_USER_PROFILE_AVATAR: 用户头像上传接口命名空间
    SYSTEM_USER_IMPORT: 用户导入接口命名空间
    SYSTEM_USER_EXPORT: 用户导出接口命名空间

    AI_MODEL_LIST: AI模型列表接口命名空间
    AI_MODEL_ALL: AI模型全量列表接口命名空间
    AI_MODEL_DETAIL: AI模型详情接口命名空间
    AI_MODEL_FUNCTION_ADAPTER_LIST: 模型功能适配列表接口命名空间

    """

    LOGIN = 'login'
    REGISTER = 'register'
    LOGIN_USER_INFO = 'login:user:info'
    LOGIN_USER_ROUTERS = 'login:user:routers'
    CAPTCHA_IMAGE = 'captcha:image'
    COMMON_UPLOAD = 'common:upload'
    TRANSPORT_CRYPTO_PUBLIC_KEY = 'transport-crypto:public-key'
    TRANSPORT_CRYPTO_FRONTEND_CONFIG = 'transport-crypto:frontend-config'

    MONITOR_CACHE_CLEAR_NAME = 'monitor:cache:clear-name'
    MONITOR_CACHE_CLEAR_KEY = 'monitor:cache:clear-key'
    MONITOR_CACHE_CLEAR_ALL = 'monitor:cache:clear-all'
    MONITOR_ONLINE_FORCE_LOGOUT = 'monitor:online:force-logout'
    MONITOR_OPERLOG_CLEAN = 'monitor:operlog:clean'
    MONITOR_OPERLOG_DELETE = 'monitor:operlog:delete'
    MONITOR_OPERLOG_EXPORT = 'monitor:operlog:export'
    MONITOR_LOGININFO_CLEAN = 'monitor:logininfor:clean'
    MONITOR_LOGININFO_DELETE = 'monitor:logininfor:delete'
    MONITOR_LOGININFO_UNLOCK = 'monitor:logininfor:unlock'
    MONITOR_LOGININFO_EXPORT = 'monitor:logininfor:export'
    MONITOR_JOB_LIST = 'monitor:job:list'
    MONITOR_JOB_DETAIL = 'monitor:job:detail'
    MONITOR_JOB_RUN = 'monitor:job:run'
    MONITOR_JOB_DELETE = 'monitor:job:delete'
    MONITOR_JOB_EXPORT = 'monitor:job:export'
    MONITOR_JOB_LOG_CLEAN = 'monitor:job-log:clean'
    MONITOR_JOB_LOG_DELETE = 'monitor:job-log:delete'
    MONITOR_JOB_LOG_EXPORT = 'monitor:job-log:export'

    SYSTEM_DEPT_EDIT_TREE = 'system:dept:edit-tree'
    SYSTEM_DEPT_LIST = 'system:dept:list'
    SYSTEM_DEPT_DETAIL = 'system:dept:detail'

    SYSTEM_CONFIG_LIST = 'system:config:list'
    SYSTEM_CONFIG_DETAIL = 'system:config:detail'
    SYSTEM_CONFIG_REFRESH_CACHE = 'system:config:refresh-cache'
    SYSTEM_CONFIG_EXPORT = 'system:config:export'

    SYSTEM_DICT_TYPE_LIST = 'system:dict:type-list'
    SYSTEM_DICT_TYPE_OPTIONS = 'system:dict:type-options'
    SYSTEM_DICT_TYPE_DETAIL = 'system:dict:type-detail'
    SYSTEM_DICT_REFRESH_CACHE = 'system:dict:refresh-cache'
    SYSTEM_DICT_TYPE_EXPORT = 'system:dict:type-export'
    SYSTEM_DICT_DATA_LIST = 'system:dict:data-list'
    SYSTEM_DICT_DATA_DETAIL = 'system:dict:data-detail'
    SYSTEM_DICT_DATA_EXPORT = 'system:dict:data-export'

    SYSTEM_MENU_TREE = 'system:menu:tree'
    SYSTEM_MENU_ROLE_TREE = 'system:menu:role-tree'
    SYSTEM_MENU_LIST = 'system:menu:list'
    SYSTEM_MENU_DETAIL = 'system:menu:detail'

    SYSTEM_NOTICE_LIST = 'system:notice:list'
    SYSTEM_NOTICE_DETAIL = 'system:notice:detail'

    SYSTEM_POST_LIST = 'system:post:list'
    SYSTEM_POST_DETAIL = 'system:post:detail'
    SYSTEM_POST_EXPORT = 'system:post:export'

    SYSTEM_ROLE_DEPT_TREE = 'system:role:dept-tree'
    SYSTEM_ROLE_LIST = 'system:role:list'
    SYSTEM_ROLE_DETAIL = 'system:role:detail'
    SYSTEM_ROLE_ALLOCATED_USER_LIST = 'system:role:allocated-user-list'
    SYSTEM_ROLE_UNALLOCATED_USER_LIST = 'system:role:unallocated-user-list'
    SYSTEM_ROLE_EXPORT = 'system:role:export'
    SYSTEM_ROLE_AUTH_USER_SELECT_ALL = 'system:role:auth-user-select-all'
    SYSTEM_ROLE_AUTH_USER_CANCEL = 'system:role:auth-user-cancel'
    SYSTEM_ROLE_AUTH_USER_CANCEL_ALL = 'system:role:auth-user-cancel-all'

    SYSTEM_USER_DEPT_TREE = 'system:user:dept-tree'
    SYSTEM_USER_LIST = 'system:user:list'
    SYSTEM_USER_PROFILE = 'system:user:profile'
    SYSTEM_USER_DETAIL = 'system:user:detail'
    SYSTEM_USER_PROFILE_AVATAR = 'system:user:profile-avatar'
    SYSTEM_USER_IMPORT = 'system:user:import'
    SYSTEM_USER_EXPORT = 'system:user:export'

    AI_MODEL_LIST = 'ai:model:list'
    AI_MODEL_ALL = 'ai:model:all'
    AI_MODEL_DETAIL = 'ai:model:detail'
    AI_MODEL_FUNCTION_ADAPTER_LIST = 'ai:model:function-adapter:list'


class ApiGroup:
    """
    接口命名空间分组常量

    当前主要用于 `ApiCacheEvict` 批量清理关联命名空间，分组成员均来自
    `ApiNamespace`，按业务写操作影响范围收敛管理。

    PERMISSION_MUTATION: 权限与菜单视图关联命名空间分组
    DATA_SCOPE_MUTATION: 数据范围相关视图关联命名空间分组
    MENU_MUTATION: 菜单写操作关联命名空间分组
    JOB_MUTATION: 定时任务写操作关联命名空间分组
    POST_MUTATION: 岗位写操作关联命名空间分组
    NOTICE_MUTATION: 通知公告写操作关联命名空间分组
    ROLE_ENTITY_MUTATION: 角色实体信息变更关联命名空间分组
    ROLE_PERMISSION_MUTATION: 角色权限变更关联命名空间分组
    ROLE_MUTATION: 角色通用写操作关联命名空间组合分组
    USER_ENTITY_MUTATION: 用户实体信息变更关联命名空间分组
    USER_PERMISSION_MUTATION: 用户权限变更关联命名空间分组
    USER_INFO_MUTATION: 用户资料与安全相关写操作关联命名空间分组
    LOGIN_SUCCESS_MUTATION: 登录成功后关联命名空间分组
    LOGOUT_MUTATION: 登出后关联命名空间分组
    CONFIG_MUTATION: 参数配置写操作关联命名空间分组
    DICT_TYPE_MUTATION: 字典类型写操作关联命名空间分组
    DICT_DATA_MUTATION: 字典数据写操作关联命名空间分组
    AI_MODEL_MUTATION: AI模型写操作关联命名空间分组
    AI_MODEL_FUNCTION_ADAPTER_MUTATION: 模型功能适配写操作关联命名空间分组
    """

    PERMISSION_MUTATION = (
        ApiNamespace.LOGIN_USER_INFO,
        ApiNamespace.LOGIN_USER_ROUTERS,
        ApiNamespace.SYSTEM_MENU_TREE,
        ApiNamespace.SYSTEM_MENU_ROLE_TREE,
        ApiNamespace.SYSTEM_MENU_LIST,
    )

    DATA_SCOPE_MUTATION = (
        ApiNamespace.LOGIN_USER_INFO,
        ApiNamespace.SYSTEM_DEPT_EDIT_TREE,
        ApiNamespace.SYSTEM_DEPT_LIST,
        ApiNamespace.SYSTEM_DEPT_DETAIL,
        ApiNamespace.SYSTEM_ROLE_DEPT_TREE,
        ApiNamespace.SYSTEM_ROLE_LIST,
        ApiNamespace.SYSTEM_ROLE_DETAIL,
        ApiNamespace.SYSTEM_ROLE_ALLOCATED_USER_LIST,
        ApiNamespace.SYSTEM_ROLE_UNALLOCATED_USER_LIST,
        ApiNamespace.SYSTEM_USER_DEPT_TREE,
        ApiNamespace.SYSTEM_USER_LIST,
        ApiNamespace.SYSTEM_USER_DETAIL,
        ApiNamespace.SYSTEM_USER_PROFILE,
        ApiNamespace.AI_MODEL_LIST,
        ApiNamespace.AI_MODEL_ALL,
        ApiNamespace.AI_MODEL_DETAIL,
    )

    MENU_MUTATION = (
        *PERMISSION_MUTATION,
        ApiNamespace.SYSTEM_MENU_DETAIL,
    )

    JOB_MUTATION = (
        ApiNamespace.MONITOR_JOB_LIST,
        ApiNamespace.MONITOR_JOB_DETAIL,
    )

    POST_MUTATION = (
        ApiNamespace.SYSTEM_POST_LIST,
        ApiNamespace.SYSTEM_POST_DETAIL,
        ApiNamespace.SYSTEM_USER_DETAIL,
        ApiNamespace.SYSTEM_USER_PROFILE,
    )

    NOTICE_MUTATION = (
        ApiNamespace.SYSTEM_NOTICE_LIST,
        ApiNamespace.SYSTEM_NOTICE_DETAIL,
    )

    ROLE_ENTITY_MUTATION = (
        ApiNamespace.SYSTEM_ROLE_DEPT_TREE,
        ApiNamespace.SYSTEM_ROLE_LIST,
        ApiNamespace.SYSTEM_ROLE_DETAIL,
        ApiNamespace.SYSTEM_ROLE_ALLOCATED_USER_LIST,
        ApiNamespace.SYSTEM_ROLE_UNALLOCATED_USER_LIST,
        ApiNamespace.SYSTEM_MENU_ROLE_TREE,
        ApiNamespace.SYSTEM_USER_DETAIL,
    )

    ROLE_PERMISSION_MUTATION = (
        *ROLE_ENTITY_MUTATION,
        ApiNamespace.SYSTEM_USER_PROFILE,
        ApiNamespace.LOGIN_USER_INFO,
        *PERMISSION_MUTATION,
    )

    ROLE_MUTATION = (
        *ROLE_PERMISSION_MUTATION,
        *DATA_SCOPE_MUTATION,
    )

    USER_ENTITY_MUTATION = (
        ApiNamespace.SYSTEM_USER_LIST,
        ApiNamespace.SYSTEM_USER_DETAIL,
        ApiNamespace.SYSTEM_ROLE_ALLOCATED_USER_LIST,
        ApiNamespace.SYSTEM_ROLE_UNALLOCATED_USER_LIST,
    )

    USER_PERMISSION_MUTATION = (
        *DATA_SCOPE_MUTATION,
        *PERMISSION_MUTATION,
    )

    USER_INFO_MUTATION = (
        ApiNamespace.SYSTEM_USER_LIST,
        ApiNamespace.SYSTEM_USER_DETAIL,
        ApiNamespace.SYSTEM_USER_PROFILE,
        ApiNamespace.LOGIN_USER_INFO,
    )

    LOGIN_SUCCESS_MUTATION = (
        ApiNamespace.SYSTEM_USER_LIST,
        ApiNamespace.LOGIN_USER_INFO,
        ApiNamespace.LOGIN_USER_ROUTERS,
        ApiNamespace.SYSTEM_USER_PROFILE,
        ApiNamespace.SYSTEM_USER_DETAIL,
    )

    LOGOUT_MUTATION = (
        ApiNamespace.LOGIN_USER_INFO,
        ApiNamespace.LOGIN_USER_ROUTERS,
    )

    CONFIG_MUTATION = (
        ApiNamespace.SYSTEM_CONFIG_LIST,
        ApiNamespace.SYSTEM_CONFIG_DETAIL,
    )

    DICT_TYPE_MUTATION = (
        ApiNamespace.SYSTEM_DICT_TYPE_LIST,
        ApiNamespace.SYSTEM_DICT_TYPE_OPTIONS,
        ApiNamespace.SYSTEM_DICT_TYPE_DETAIL,
        ApiNamespace.SYSTEM_DICT_DATA_LIST,
        ApiNamespace.SYSTEM_DICT_DATA_DETAIL,
    )

    DICT_DATA_MUTATION = (
        ApiNamespace.SYSTEM_DICT_DATA_LIST,
        ApiNamespace.SYSTEM_DICT_DATA_DETAIL,
    )

    AI_MODEL_MUTATION = (
        ApiNamespace.AI_MODEL_LIST,
        ApiNamespace.AI_MODEL_ALL,
        ApiNamespace.AI_MODEL_DETAIL,
    )

    AI_MODEL_FUNCTION_ADAPTER_MUTATION = (ApiNamespace.AI_MODEL_FUNCTION_ADAPTER_LIST,)

class MenuConstant:
    """
    菜单常量

    TYPE_DIR: 菜单类型（目录）
    TYPE_MENU: 菜单类型（菜单）
    TYPE_BUTTON: 菜单类型（按钮）
    YES_FRAME: 是否菜单外链（是）
    NO_FRAME: 是否菜单外链（否）
    LAYOUT: Layout组件标识
    PARENT_VIEW: ParentView组件标识
    INNER_LINK: InnerLink组件标识
    """

    TYPE_DIR = 'M'
    TYPE_MENU = 'C'
    TYPE_BUTTON = 'F'
    YES_FRAME = 0
    NO_FRAME = 1
    LAYOUT = 'Layout'
    PARENT_VIEW = 'ParentView'
    INNER_LINK = 'InnerLink'
