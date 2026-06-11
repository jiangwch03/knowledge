from enum import Enum


class HttpMethod(str, Enum):
    """
    HTTP请求方法枚举

    GET: 获取资源
    POST: 创建资源
    PUT: 整体更新资源
    DELETE: 删除资源
    PATCH: 局部更新资源
    HEAD: 获取响应头
    OPTIONS: 获取允许的方法信息
    TRACE: 回显诊断请求
    CONNECT: 建立隧道连接
    """

    GET = 'GET'
    POST = 'POST'
    PUT = 'PUT'
    DELETE = 'DELETE'
    PATCH = 'PATCH'
    HEAD = 'HEAD'
    OPTIONS = 'OPTIONS'
    TRACE = 'TRACE'
    CONNECT = 'CONNECT'


class BusinessType(Enum):
    """
    业务操作类型

    OTHER: 其它
    INSERT: 新增
    UPDATE: 修改
    DELETE: 删除
    GRANT: 授权
    EXPORT: 导出
    IMPORT: 导入
    FORCE: 强退
    GENCODE: 生成代码
    CLEAN: 清空数据
    """

    OTHER = 0
    INSERT = 1
    UPDATE = 2
    DELETE = 3
    GRANT = 4
    EXPORT = 5
    IMPORT = 6
    FORCE = 7
    GENCODE = 8
    CLEAN = 9

