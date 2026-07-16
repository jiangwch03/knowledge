"""爬虫代理池查询结果 VO"""

from pydantic import BaseModel, Field


class ProxyPoolItemVo(BaseModel):
    """单条代理节点（来自 sys_dict_data）"""

    label: str = Field(description='字典标签，节点名称')
    server: str = Field(description='代理地址，如 http://host:port')
    username: str = Field(default='', description='代理用户名，无则空串')
    password: str = Field(default='', description='代理密码，无则空串')


class ProxyPoolVo(BaseModel):
    """
    代理池查询结果

    由 WebCrawlerProxyPoolService.query_proxy_pool 返回，供 Agent 工具消费。
    """

    available: bool = Field(description='是否存在可用代理节点')
    pool_size: int = Field(description='可用节点数量')
    dict_type: str = Field(default='crawl_proxy_pool', description='字典类型')
    message: str = Field(description='给 LLM 的说明，含无池时的应对建议')
    proxies: list[ProxyPoolItemVo] = Field(default_factory=list, description='代理节点列表')
