"""声明式客户端，对齐 @FeignClient(name, path, url)。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FeignClient:
    """对齐 OpenFeign @FeignClient：

    - 仅 name：走 Nacos 发现
    - 同时配置 url：直连该地址，绕过 Nacos（本地调试）
    - path：应用上下文前缀，拼在每个请求路径前
    """

    name: str
    path: str = ''
    url: str = ''
    # 空则用 Feign.DEFAULT_TIMEOUT；方法上的 timeout 优先
    timeout: float | None = None
