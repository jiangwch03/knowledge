"""Agent 工具定义（薄适配层）"""
from knowledge_content.agents.tools.apply_scope_change import apply_scope_change
from knowledge_content.agents.tools.crawl_execute import crawl_execute
from knowledge_content.agents.tools.crawl_merge_results import merge_crawl_results
from knowledge_content.agents.tools.crawl_retry import crawl_retry
from knowledge_content.agents.tools.crawl_task_list_actionable import list_actionable_crawl_tasks
from knowledge_content.agents.tools.crawl_task_delete import delete_crawl_task
from knowledge_content.agents.tools.crawl_task_query import query_crawl_task
from knowledge_content.agents.tools.crawl_task_pause import pause_crawl_task
from knowledge_content.agents.tools.crawl_task_resume import resume_crawl_task
from knowledge_content.agents.tools.preview_scope_removal import preview_scope_removal
from knowledge_content.agents.tools.crawl_trial import trial_crawl
from knowledge_content.agents.tools.fetch_crawling_anti import anti_crawling_test
from knowledge_content.agents.tools.fetch_page import fetch_page
from knowledge_content.agents.tools.probe_rendered_page import probe_rendered_page
from knowledge_content.agents.tools.fetch_robots_txt import fetch_robots_txt
from knowledge_content.agents.tools.fetch_sitemap import fetch_sitemap
from knowledge_content.agents.tools.query_proxy_pool import query_proxy_pool

# Planning Agent 工具集：探站分析 → 生成策略 → 试爬验证
CRAWL_AGENT_PLANNING_TOOLS: list = [
    fetch_robots_txt,      # 获取并解析 robots.txt（允许/禁止路径、sitemap 地址、爬取延迟）
    fetch_sitemap,         # 获取并解析 sitemap.xml（URL 总量、路径分组、抽样 URL）
    fetch_page,            # 抓取单页并分析结构（HTTP 快探：分页、弹窗、内外链等）
    probe_rendered_page,   # 浏览器打开页面看实际内容（登录/版本/分类/空壳风险；fetch_page 发现需JS时调用）
    anti_crawling_test,    # 检测反爬等级（验证码、限速、Cloudflare 等）并给出应对建议
    query_proxy_pool,      # 查询系统代理 IP 池（高强度反爬时须先查，禁止虚构代理）
    trial_crawl,           # 用候选 crawl_config 做单页试探爬取，验证配置是否生效
]

# Supervisor Agent 工具集：任务生命周期管理（执行 / 监控 / 干预 / 合并）
CRAWL_AGENT_DEEP_SUPERVISOR_TOOLS: list = [
    list_actionable_crawl_tasks,  # 查询当前用户有权操作的任务列表（RUNNING/PAUSED/USER_DECISION/FAILED）
    query_crawl_task,      # task_id 查详情验权限；target_url 防重复查 found
    preview_scope_removal, # 改范围前：按新 filter_chain 计算待删已爬 URL 清单
    pause_crawl_task,      # 暂停 RUNNING 状态的任务
    resume_crawl_task,     # 恢复 PAUSED 状态的任务（不修改 crawl_config）
    apply_scope_change,    # PAUSED 下调整爬取范围（更新 config、删越界 URL 后恢复）
    delete_crawl_task,     # 软删除指定任务
    merge_crawl_results,   # 放弃失败 URL，将已成功页面投入文档合并队列
    crawl_execute,         # 提交正式全站后台爬取任务（异步，返回 task_id）
    crawl_retry,           # 失败任务重试（复用 task_id，可更新 crawl_config / target_url） 
]

_seen_names: set[str] = set()
ALL_TOOLS: list = []
# 去重合并工具列表
for _tool in CRAWL_AGENT_PLANNING_TOOLS + CRAWL_AGENT_DEEP_SUPERVISOR_TOOLS:
    if _tool.name not in _seen_names:
        _seen_names.add(_tool.name)
        ALL_TOOLS.append(_tool)
