"""
网页爬取 Agent 分析工具 - 浏览器渲染探针

用真实浏览器打开页面，看清页面上有什么、能不能直接爬到正文。
只输出观察结果，不生成爬取配置；配置由你根据返回信息自行决定。
"""
from langchain_core.tools import tool

from knowledge_common.exceptions.exception import format_exception_message
from knowledge_common.utils.log_util import logger
from knowledge_content.service.rendered_page_probe_service import RenderedPageProbeService


@tool
async def probe_rendered_page(
    url: str,
    hooks: dict | None = None,
    cookies: str | None = None,
) -> str:
    """
    用浏览器打开页面，检查「打开后实际能看到什么」。

    ## 什么时候调用
    - 在「抓取首页样本」(fetch_page) 之后
    - 当 fetch_page 显示 has_js_rendering=true，或页面疑似单页应用(SPA)、
      正文很少、需要点击版本/语言/登录后才能看内容时
    - 不要对明显纯静态页调用（浪费一次浏览器请求）

    ## 登录 / 验证码阻断（重要）
    - 首次探针**不要**传 hooks/cookies；若被重定向到登录页，返回 probe_status=blocked
    - 此时只看 probe_status / block_reason / intended_url / login_gate 字段写 hook
    - **禁止**把登录页上的搜索框、站点类型当成目标页结论
    - 向用户追问账号密码或 Cookie 后，用 trial_crawl 验证登录 hook
    - 登录 trial 成功后，可带 hooks 或 cookies **复探**本工具以分析目标页结构

    ## 和 fetch_page 的区别
    - fetch_page：不发浏览器，只下载 HTML，速度快，但看不到 JS 渲染后的内容
    - 本工具：开浏览器渲染页面，能看到登录框、搜索框、版本切换、分类导航等

    ## 返回 JSON 字段说明

    probe_status — 探针是否到达目标页
      - ok: 正常完成
      - blocked: 被登录墙/验证码挡住，目标页未打开

    block_reason — 阻断原因（probe_status=blocked 时）
      - login_redirect: 被重定向到登录页
      - login_required: 当前页是登录表单或软登录提示
      - captcha_required: 检测到验证码

    intended_url / actual_url — 用户意图 URL vs 浏览器实际打开的 URL
    action_required — blocked 时为 ask_user_then_trial_with_hooks

    rendering — 页面内容是怎么来的
      - mode: 页面类型。static=HTML里已有正文; ssr=服务端渲染;
        spa=主要靠JS渲染; hybrid=HTML有内容但还需点击交互
      - http_body_chars: 不开浏览器时拿到的 HTML 字数
      - rendered_body_chars: 浏览器打开后拿到的正文字数
      - content_ratio: 渲染后字数/HTTP字数，越大说明越依赖JS
      - shell_risk: 空壳风险。high=不渲染几乎没内容; low=不渲染也有正文
      - needs_browser: 是否必须等JS/做交互才能爬到有用内容。
        true 时试爬和正式爬要配更长等待、hooks（如点版本、登录）

    page_structure — 页面规模
      - title, markdown_chars: 标题和正文字数
      - internal_link_count: 内链数量
      - internal_link_samples: 内链抽样（href + 锚文本）

    controls — 页面上有哪些表单控件（原始 DOM 事实）
      - 每条含 tag(input/button/select)、selector、文本/类型
      - 用于确认登录框有几个输入框、搜索框在哪

    interactive_elements — 交互元素归类（重点看这个）
      - category 常见值:
        login_gate=有密码登录表单; login_prompt=提示登录但无表单;
        search_box=站内搜索; pagination=分页; filter_panel=筛选下拉;
        version_switcher=文档版本切换; language_switcher=语言切换;
        category_navigation=顶部分类/频道导航; client_side_router=前端路由
      - evidence: 检测依据
      - options: 版本号/分类名等可选项列表
      - fields: 登录表单字段（login_gate 时）
      - impact: 对爬取的影响提示

    site_type_candidates — 站点类型猜测（打分，供参考）
      - 如「技术文档站」「新闻/博客站」等，score 越高越像

    version_url_patterns — 页面上发现的文档版本 URL 规律
      - 如 /docs/v2.4/ 前缀，可用来写 filter_chain 限定版本范围

    crawl_implications — 行动提示（短标签，优先读这个）
      - probe_target_unreachable / stop_probe_use_trial_after_auth → 目标页未打开，须追问用户后用 trial_crawl 验证 hook
      - redirected_to_login → 被重定向到登录页
      - needs_browser_rendering → 必须配浏览器等待/交互
      - ask_user_for_credentials → 需要问用户账号密码或 Cookie
      - ask_user_for_crawl_scope → 需要问用户爬哪些分类/板块
      - version_not_in_url_ask_user → URL没版本号，要问用户要哪个版本
      - site_search_available → 可用站内搜索辅助发现 URL
      - blocked_without_captcha → 有验证码，建议用户提供已登录 Cookie

    ## 你怎么用返回结果
    1. 若 probe_status=blocked：向用户要凭证 → 写 hooks → trial_crawl 验证 → 再决定是否带 hooks/cookies 复探
    2. 若 probe_status=ok：先看 crawl_implications，再看 interactive_elements
    3. 据此写 crawl_config（等待策略、filter_chain、hooks），再调 trial_crawl 验证
    4. 本工具不返回爬取配置，只返回观察事实

    Args:
        url: 目标页面 URL（与探站目标同源）
        hooks: 可选登录/交互 hooks（仅登录验证通过后的复探使用）
        cookies: 可选 Cookie 字符串（非 HttpOnly；或登录后复探使用）
    """
    try:
        vo = await RenderedPageProbeService.probe(url, hooks=hooks, cookies=cookies)
        return vo.model_dump_json(by_alias=True, ensure_ascii=False)
    except Exception as e:
        err = format_exception_message(e)
        logger.exception('[Analysis] probe_rendered_page 异常: {}', err)
        return f'Error: {err}'
