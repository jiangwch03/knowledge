"""content MCP：复用现有 FastAPI，不另起进程/端口。

不调用 MCPServer.run(transport='streamable-http')——那会再起一个独立 HTTP 服务。
这里用 streamable_http_app() + app.mount()，挂到 content 同一进程、同一端口。

对外地址：{content_base}{APP_ROOT_PATH}{MCP_MOUNT}
本地默认：http://127.0.0.1:9098/api/knowledge_content/mcp
工具按领域注册到这一个服务上，mcp/ 目录只放工具实现（用 @server.tool() 注解）。
"""
from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

from knowledge_common.config.env import McpConfig
from knowledge_common.exceptions.exception import AuthException
from knowledge_common.service.login_user_service import LoginUserService

# 模块级单例，供 mcp/*.py 用 @server.tool() 注册工具
server = MCPServer(
    McpConfig.mcp_server_name,  # MCP_SERVER_NAME
    instructions=McpConfig.mcp_server_instructions,  # MCP_SERVER_INSTRUCTIONS，交给客户端的工具使用说明
)


def build_mcp_server() -> MCPServer:
    """
    构建 content 的 MCP Server（导入工具模块以触发 @server.tool() 注册）。

    服务名和说明从 McpConfig 读取。工具按领域写在 mcp/ 下并用注解挂到这一个服务；
    以后新增能力时再 import 一组工具模块，不要另挂一个 MCP。

    :return: 已注册工具的 MCPServer
    """
    # 导入即注册（装饰器在模块加载时执行）
    from knowledge_content.mcp import segment_mcp as _segment_mcp  # noqa: F401

    return server


class _McpAuthApp:
    """
    MCP 入口鉴权包装。

    只校验登录，不校验菜单权限。
    parent 传 content 的 FastAPI，便于 LoginUserService 读到 app.state.redis。
    """

    def __init__(self, inner: Any, parent: Any) -> None:
        self.inner = inner
        self.parent = parent

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get('type') != 'http':
            await self.inner(scope, receive, send)
            return

        auth_scope = dict(scope)
        auth_scope['app'] = self.parent
        request = Request(auth_scope)
        token = request.headers.get('authorization') or request.headers.get('Authorization')
        if not token:
            response = JSONResponse({'code': 401, 'msg': '用户未登录，请先完成登录'}, status_code=401)
            await response(scope, receive, send)
            return
        try:
            await LoginUserService.get_current_user(request, token)
        except AuthException as exc:
            response = JSONResponse({'code': 401, 'msg': exc.message or '用户未登录'}, status_code=401)
            await response(scope, receive, send)
            return
        await self.inner(scope, receive, send)


def mount_mcp(app: Any) -> MCPServer:
    """
    把 MCP 挂到 content 现有 FastAPI，复用同一进程与端口。

    对比 MCPServer.run(transport='streamable-http', host=..., port=...)：
    那会再起一个独立 HTTP 服务；这里不另开端口，只挂路径 MCP_MOUNT（默认 /mcp）。

    传输：Streamable HTTP，无状态，每次请求回一包 JSON（非 SSE 长连接）。
    子应用 lifespan 不会随主应用自动跑；session manager 由 server.py 的 lifespan
    读取 app.state.mcp_server 后拉起。

    :param app: content 的 FastAPI 应用
    :return: 已挂载的 MCPServer
    """
    mcp = build_mcp_server()
    # 生成可挂载的 ASGI 子应用；真正对外路径 = mount 前缀，不是这里再起端口
    mcp_app = mcp.streamable_http_app(
        streamable_http_path='/',  # 子应用内根路径；完整路径由下面 app.mount(MCP_MOUNT) 决定
        json_response=True,  # 单次 JSON 响应，不走 SSE 长连接
        stateless_http=True,  # 不在服务端维持 MCP 会话
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),  # 内网调用，不校验 Host
        host='0.0.0.0',
    )
    # MCP_MOUNT 默认 /mcp；入口只校验登录，具体权限由各工具检查
    app.mount(McpConfig.mcp_mount, _McpAuthApp(mcp_app, app))
    app.state.mcp_server = mcp  # 供 lifespan 启动 session_manager.run()
    return mcp
