# 爬虫 Agent deepagents 架构规划

> 基于 A2A（Agent-to-Agent）架构理念，引入 LangChain deepagents 框架重构爬虫 Agent
> 讨论状态：Planning 为唯一子 Agent；执行类工具归 Supervisor，Execute 子 Agent 暂不引入

---

## 一、背景与目标

### 1.1 当前架构问题

现有父图（`crawler_agent/graph.py`）采用**硬编码管线**编排：

```text
START → Supervisor Agent → END

（无 url_router 前置节点；URL 提取为确定性预处理，切站确认由 Supervisor interrupt 负责）
```

痛点：
- **父图无 LLM 参与**：子图间的流转是固定连线，父图不分析子图产出物，不具备动态调度能力
- **子图职责过重**：execute_subgraph 同时承担"策略生成"（GENERATING）和"策略执行"（EXECUTING）两个阶段，单图内状态复杂
- **扩展性差**：新增场景（如修复失败、合并已爬内容）需要在子图内硬编码条件分支，无法灵活编排

### 1.2 目标架构理念

**A2A（Agent-to-Agent）——用户定义的交互模式：**

1. **多个子 Agent（Agent）之间支持双向通信**
2. **父图（Supervisor）必须经过 LLM 分析理解子 Agent 的输出结果**
3. **父图基于 LLM 的理解能力动态、自由地调度子 Agent**（可循环调用、可跳过、可重试），而非硬编码固定流程

### 1.3 deepagents 框架

LangChain 官方出品的 Agent 框架（`pip install deepagents`），核心能力：

| 能力 | 说明 |
|------|------|
| **Planning Tool（TodoList）** | Agent 内置规划工具，可拆解任务并逐步执行 |
| **Sub-Agent 委派** | 通过 `task()` 工具将子任务委派给子 Agent |
| **CompiledSubAgent** | 将已有 LangGraph `CompiledStateGraph` 包装为子 Agent |
| **虚拟文件系统** | Agent 间通过虚拟文件系统共享中间产物 |
| **可扩展 Prompt** | 支持自定义 system prompt、description、tools |

---

## 二、Agent 拆分方案

### 2.0 子 Agent 判定标准

**只有需要 LLM + 多轮工具推理的模块才包装为 CompiledSubAgent。**

| 模块 | 是否子 Agent | 理由 |
|------|-------------|------|
| Planning | **是** | ReAct 探站 + 生成 config + trial |
| 任务执行（submit/retry/rescope） | **否（现阶段）** | 确定性工具调用，Supervisor 直调即可；**后续若需 LLM 自愈再扩展 Execute 子 Agent** |

### 2.1 整体架构

划分依据：**Planning 解决「爬什么、怎么配」；Supervisor 解决「用户要什么、任务 CRUD、提交/重试/rescope、人机确认」。**

```text
┌──────────────────────────────────────────────────────────────┐
│                    Supervisor Agent（父 Agent）                 │
│                                                              │
│  任务管理: query / delete / pause / resume / merge            │
│  任务执行: crawl_execute / crawl_retry / apply_scope_change   │
│                                                              │
│  编排: task(planning)  ← 唯一子 Agent 委派                     │
│  人机协同: 策略确认 / URL 切站 / rescope 删页 interrupt         │
└───────────────────────────────┬──────────────────────────────┘
                                │
                                ▼
                ┌─────────────────────────────┐
                │   Planning Agent（站点策略）   │
                │   (CompiledSubAgent)          │
                │                             │
                │  工具: fetch_* + trial_crawl │
                │  产出: strategy_config,       │
                │        pages_to_remove, ...   │
                └─────────────────────────────┘

START → Supervisor → END（无 url_router；URL 提取为入口预处理）
```

### 2.2 Supervisor Agent（父 Agent）

**职责**：意图理解 + URL/会话路由 + 子 Agent 编排 + 人机协同 interrupt + 轻量任务 CRUD

**不做的事**：不探查站点、不产出 strategy_config JSON

**URL 处理（取代原 url_router_node）**：

| 能力 | 实现方式 |
|------|----------|
| 从用户消息提取 URL | 确定性预处理（正则/工具函数），写入 `target_url`，注入 Supervisor 上下文 |
| 会话内 URL 变更 | Supervisor LLM 判断意图；不确定时 **interrupt** 弹框确认 |
| 同站分析缓存 | `url_analysis_history` 保留在 Supervisor state，切回旧 URL 时可跳过 Planning |

不再单独维护 `url_router_node` + `crawler.router` 提示词——切站与会话路由本就是「理解用户意图」的一部分，归 Supervisor 更自然，且能利用完整对话上下文。

```
System Prompt 要点（意图与编排，不教工具参数）:
- 发起爬取 → 委派 Planning → interrupt 确认策略 → 提交正式爬取
- 查询/删除/暂停/合并/纯恢复 → 按用户意图处理已有任务
- 修复失败 → 先了解失败情况 → 直接重试或委派 Planning 调参后再重试
- 中途改范围 → 暂停 → 委派 Planning → interrupt（含删页确认）→ 按新策略续爬
- URL 切站 → 意图明确则切换；否则 interrupt 确认
```

**工具列表（Supervisor 级别）：**

| 类别 | 工具 | 场景 |
|------|------|------|
| 查询/管理 | `query_crawl_task` | 查进度/失败详情 |
| | `delete_crawl_task` | 删除任务 |
| | `pause_crawl_task` | 暂停 |
| | `resume_crawl_task` | 纯恢复（**不改** config） |
| | `merge_crawl_results` | 合并已爬内容 |
| 执行 | `crawl_execute` | 策略确认后提交新任务 |
| | `crawl_retry` | 失败重试（带可选新 config） |
| | `apply_scope_change` | rescope：删页 + 更新 config + resume |

**Sub-Agent 委派**：仅 `task(planning)`；执行类工具由 Supervisor **直接调用**，不委派子 Agent。

### 2.3 Planning Agent（站点策略子 Agent）

**职责**：理解站点结构 → 生成/调整 `strategy_config` → `trial_crawl` 验证；rescope 时计算待删 URL 列表

**工具列表：**
- `fetch_robots_txt` — robots.txt 合规边界
- `fetch_sitemap` — 站点地图、规模估算（含 path_prefix 过滤）
- `fetch_page` — 单页结构分析
- `anti_crawling_test` — 反爬检测
- `trial_crawl` — 试爬验证配置

**rescope 模式额外能力**（读 Service 层，可不暴露为独立 Agent 工具）：
- 读取当前 `crawl_config` 与已爬 URL 列表
- 用新 config 的 `include_patterns` / `exclude_patterns` 对 SUCCESS 记录做 pattern 匹配，产出 `pages_to_remove`

**产出物**（回流 Supervisor）：

| 字段 | 说明 |
|------|------|
| `analysis_results` | 各工具分析结论 |
| `strategy_config` | draft 爬取配置 JSON |
| `trial_summary` | 试跑摘要（可选） |
| `pages_to_remove` | rescope 时建议删除的 URL 列表 `[{url, title, reason}]` |
| `scope_summary` | 范围变更说明（可选） |

### 2.4 任务执行（Supervisor 工具，非子 Agent）

现阶段 **不设立 Execute 子 Agent**。下列能力均为 Supervisor 直调工具：

| 工具 | 说明 |
|------|------|
| `crawl_execute` | 策略确认后提交后台任务，返回 `task_id` |
| `crawl_retry` | 复用 `task_id` 重试，可带新 config |
| `apply_scope_change` | rescope 复合操作（见 2.5） |

**后续扩展**：若 submit 失败需 LLM 自愈、或需自主监控 RUNNING 任务，再引入 Execute CompiledSubAgent。

### 2.5 职责边界总览

| 维度 | Planning Agent | Supervisor |
|------|---------------|------------|
| 认知域 | 站点结构、config 生成/调整 | 意图路由、任务 CRUD、提交/重试/rescope、人机确认 |
| LLM | 需要（ReAct） | 需要（编排+回复） |
| 关键工具 | fetch_* + trial_crawl | query / pause / resume / delete / merge / crawl_execute / crawl_retry / apply_scope_change |
| 关键产出 | strategy_config, pages_to_remove | 无（调度层；task_id 由工具返回值写入 state） |
| 修复失败 | 调参（fix） | query → crawl_retry 或 planning(fix) → crawl_retry |
| 改范围续爬 | 新 config + pages_to_remove | pause → 确认 → apply_scope_change |

### 2.6 爬取中途调整范围（In-Task Rescope）

**用户场景**（爬取进行中）：
- 「文章不爬了，只要 API」
- 「加上 API 文档一起爬」
- 「范围缩小/扩大，已爬页面里不符合新范围的需用户确认删除」

**设计原则**：
- rescope 原子步骤收成 Supervisor 工具 `apply_scope_change`（非子 Agent）
- Planning 负责「新 config + 哪些 URL 越界」
- 删页经 Supervisor interrupt 用户确认后再调工具

**子场景拆分：**

| 子场景 | 是否删页 | Planning | Supervisor 工具 |
|--------|---------|----------|----------------|
| A. 缩小范围 | **是** | 新 config + pages_to_remove | apply_scope_change |
| B. 扩大范围 | 否 | 新 config | apply_scope_change |
| C. 缩+扩 | 仅删越界部分 | 同上 | apply_scope_change |

**复合工具 `apply_scope_change`（Supervisor / Service 层）：**

```python
apply_scope_change(
    crawl_config: dict,                    # 确认后的新策略
    urls_to_remove: list[str] | None = None,  # 用户确认后的删页列表；扩范围时传空
)
```

**内部原子顺序**（要求 `task.status == PAUSED`）：

```text
1. 校验 PAUSED + 分布式锁（与 Worker / merge 互斥）
2. 若 urls_to_remove 非空:
     软删 url_record + 删除 MinIO doc_key + 重算 success_count
3. 更新 task.crawl_config
4. resume_task（Worker 通过 skip_urls 跳过仍保留的 SUCCESS 记录）
5. 返回摘要
```

**注意**：
- 不用 `crawl_retry` 代替 rescope：`retry` 会 `retry_count++`、语义是失败重试
- 缩小范围时**必须**删越界 SUCCESS 记录，否则 `merge_crawl_results` 仍会合并旧页
- 扩大范围若 BFS 到不了新区（如 API 与 docs 隔离），Planning 需在 config 中加 seed URL 或调整 `include_patterns`

**编排流程：**

```text
User: "文章别爬了，加上 API"

Supervisor:
  1. query_crawl_task（若 RUNNING）
  2. pause_crawl_task → 等待 PAUSED
  3. task(planning, mode=rescope, user_intent=...)

Planning:
  - 读当前 crawl_config + 已爬 URL 列表
  - 生成新 strategy_config
  - 可选 trial_crawl(API 代表页)
  - pattern 匹配 → pages_to_remove + scope_summary

Supervisor:
  4. interrupt 确认（新范围摘要 + 待删 URL 列表）
  5. apply_scope_change(config, urls_to_remove=用户确认列表)
  6. 回复用户
```

**Service 层**（已实现）：
- [x] `WebCrawlerTaskService.update_crawl_config(task_id, config)` — PAUSED 下更新配置
- [x] 按 record_id/url 批量软删 url_record + MinIO 清理 + 重算计数
- [x] `apply_scope_change` 封装上述 + `resume_task`
- [x] Planning rescope：`filter_chain_util` pattern 匹配

---

## 三、deepagents 集成设计

### 3.1 CompiledSubAgent 包装

deepagents 的 `CompiledSubAgent` 可直接包装现有的 `CompiledStateGraph`：

```python
from deepagents import CompiledSubAgent

# 包装站点策略子图（唯一子 Agent）
planning_agent = CompiledSubAgent(
    name="planning_agent",
    description="分析网站结构、生成/调整爬取策略，rescope 时计算待删 URL",
    runnable=get_planning_subgraph(),
)
```

**后续扩展**：若引入 Execute 子 Agent，再增加第二个 `CompiledSubAgent` 包装执行子图。

**要求**：
- 子图的 State schema 必须包含 `messages` key（现有 `ReactBaseState` 已满足）
- `CompiledSubAgent` 不会自动继承父图的 state schema，若子图需要父图中的额外字段（如 `task_id`），需在编译子图时自行定义

### 3.2 Supervisor Agent 创建

```python
from deepagents import create_deep_agent

supervisor = create_deep_agent(
    state_schema=CrawlerSupervisorState,
    prompt=SUPERVISOR_SYSTEM_PROMPT,
    tools=[
        query_crawl_task, delete_crawl_task,
        pause_crawl_task, resume_crawl_task,
        merge_crawl_results,
        crawl_execute, crawl_retry, apply_scope_change,
    ],
    subagents=[planning_agent],
)
```

```
# Supervisor LLM 思考示例：
1. 新站爬取 → task("planning_agent", mode=init) → interrupt → crawl_execute(config)
2. 修复失败 → query → crawl_retry 或 task(planning, fix) → interrupt → crawl_retry
3. 改范围 → pause → task(planning, rescope) → interrupt → apply_scope_change
4. 查进度 → query_crawl_task
```

### 3.3 状态架构变化

```
┌─────────────────────────────────────────┐
│         CrawlerSupervisorState          │  ← 新的 Supervisor 状态
│                                         │
│  - session_id                          │
│  - user_content / target_url            │
│  - url_analysis_history                 │
│  - messages (Supervisor 的对话消息)     │
│  - strategy_config: dict | None   # confirmed 版本（Planning draft + 用户调整）
│  - task_id: int | None            # 当前活跃任务
│  - execute_result: str | None
└─────────┬───────────────────────────────┘
           │
           │ 子 Agent 返回时自动提取
           ▼
┌─────────────────────────────────────────┐
│  PlanningState                          │
│  - messages / react_round               │
│  - analysis_results                     │
│  - strategy_config / pages_to_remove    │
└─────────────────────────────────────────┘
```

### 3.4 场景编排示例

**场景1：发起爬取**
```
User: "帮我爬一下 https://example.com"

Supervisor:
1. task("planning_agent", target_url="https://example.com")
2. interrupt 策略确认
3. crawl_execute(strategy_config={...}) → 写入 task_id
4. 回复用户
```

**场景2：修复失败**
```
User: "爬失败了，帮我看下原因修一下"

Supervisor:
1. query_crawl_task
2. 偶发失败 / 「直接重试」→ crawl_retry(config=当前配置)
3. 需调参 → task(planning, fix) → interrupt → crawl_retry(config=新配置)
```

**场景3：放弃爬取合并已爬内容**
```
User: "不爬了，先把爬到的合并了吧"

Supervisor:
1. query_crawl_task
2. merge_crawl_results(task_id)
3. 回复用户
```

**场景4：爬取中途调整范围（In-Task Rescope）**
```
User: "文章别爬了，加上 API"

Supervisor:
1. query_crawl_task（确认 RUNNING）
2. pause_crawl_task → PAUSED
3. task("planning_agent", mode=rescope, user_intent=...)
   → {strategy_config, pages_to_remove, scope_summary}
4. interrupt 确认
5. apply_scope_change(config, urls_to_remove=确认列表)
6. 回复用户

扩范围且不删页: pages_to_remove=[]，其余流程相同。
```

### 3.5 URL 路由：废弃 url_router_node

**结论：新架构不需要独立的 `url_router_node`。**

| 原 url_router 职责 | 新架构归属 |
|------------------|-----------|
| URL 正则提取 | 图入口确定性预处理（非 LLM 节点） |
| 切站/下钻意图判断 | Supervisor LLM |
| interrupt 弹框 | Supervisor interrupt（与策略确认、rescope 删页同一套机制） |
| `url_analysis_history` 缓存 | Supervisor state |

**废弃理由**：
1. Supervisor 本身就要理解用户意图，再拆一个 router LLM 是重复决策
2. router 看不到完整对话，切站判断反而不如 Supervisor 准
3. 减少一种 interrupt 类型和一条固定边，图结构更简单：`START → Supervisor → END`

**Supervisor 对 URL 变更的处理规则**（写入 supervisor 提示词）：
- 用户**明确**要爬/分析新 URL（「帮我爬 xxx」「换到 xxx」）→ 更新 `target_url`，委派 Planning
- 用户**顺带提及**新 URL、意图不明 → interrupt 确认是否切换
- URL 未变 → 不处理
- 切回历史 URL 且有缓存 → 可直接委派 Planning（带 cache hint）或询问是否复用分析

---

## 四、实施路线图

### Phase 1：准备阶段
- [x] 添加 `deepagents` 依赖
- [x] `create_deep_agent` + `CompiledSubAgent(planning)` 接入父图
- [x] interrupt：interrupt_gate + HITL + 自由文本 resume

### Phase 2：Planning 子 Agent + Supervisor 工具
- [x] 创建 `PlanningState` + planning 子图
- [x] Planning 工具：fetch_* + query_proxy_pool + trial_crawl
- [x] deepagents `task` 工具委派 Planning（已删除 legacy `task_planning`）
- [x] `prompts.yaml` → `crawler.planning`
- [x] validate + trial 闭环（trial_crawl 工具 + prompt 约束）

### Phase 3：Supervisor 集成
- [x] 图结构：`START → url_preprocess → ingest → supervisor → state_sync → interrupt_gate`
- [x] Supervisor 子图 + 任务工具绑定
- [x] `prompts.yaml` → `crawler.supervisor`（完整编排版）
- [x] `create_deep_agent` 默认开启
- [x] url_router 已删除（`url_preprocess` + Supervisor interrupt）

### Phase 4：适配与测试
- [x] Supervisor interrupt + HITL + SSE input_mode
- [x] SSE 穿透 subgraphs=True
- [x] 单测：architecture / interrupt / graph_smoke / sensitive_mask
- [x] E2E 联调清单：`docs/rag/爬虫Agent_E2E联调清单.md`
- [ ] 真机 E2E（需 LLM + Redis 环境人工跑清单）

### Phase 5：In-Task Rescope
- [x] Service：`update_crawl_config`、批量删 url_record + MinIO、重算计数
- [x] Supervisor 工具 `apply_scope_change`
- [x] Planning rescope：pattern 匹配 → pages_to_remove
- [x] Supervisor interrupt：删页确认

---

## 五、待讨论问题（已决议）

1. **interrupt 统一** → Supervisor 策略/rescope/HITL；二类参数走 chat ✅
2. **流式穿透** → subgraphs=True + 子图 token ✅
3. **rescope 扩大范围** → Planning 可加 seed URL（按需迭代）
4. **Execute 子 Agent** → 暂缓，Supervisor 工具足够 ✅

---

## 六、场景归类与 Agent 映射

| 场景 | 路径 |
|------|------|
| 发起爬取 | Supervisor → Planning → interrupt → **crawl_execute** |
| 查询详情 | Supervisor（query） |
| 修复失败 | Supervisor → query → Planning(可选) → **crawl_retry** |
| 删除/合并/暂停/恢复 | Supervisor 直调工具 |
| 策略确认 | Planning → Supervisor interrupt → crawl_execute |
| 中途改范围 | pause → Planning(rescope) → interrupt → **apply_scope_change** |

---

## 七、工具归属总表

| 工具 | 归属 | 场景 |
|------|------|------|
| fetch_* / trial_crawl | Planning | 探查、验证 config |
| crawl_execute | **Supervisor** | 新建任务 |
| crawl_retry | **Supervisor** | 失败重试 |
| apply_scope_change | **Supervisor** | rescope |
| query / pause / resume / delete / merge | **Supervisor** | 任务 CRUD |

---

## 八、提示词设计

> 以下按**目标架构**从零编写，不绑定现有 `prompts.yaml` 条目，不做「迁移对照」。

### 8.1 设计原则

| 原则 | 说明 |
|------|------|
| **两个 LLM 角色** | Supervisor（编排+工具+interrupt）/ Planning（探查+config） |
| **唯一子 Agent** | 仅 Planning；执行工具归 Supervisor，**Execute 子 Agent 后续按需扩展** |
| **Supervisor 不写 crawl4ai 细节** | 只路由、转述、确认 |
| **工具用法不进 prompt** | 前置条件、参数等由 tool description + Service 校验承载 |
| **不写「禁止调用未绑定工具」** | 工具绑定即能力边界，Planning 只有 fetch_* + trial，无需在 prompt 里列禁止项 |
| **Planning 唯一产出 strategy_config** | validate + trial；rescope 产出 pages_to_remove |
| **无 url_router** | URL 预处理 + Supervisor interrupt |
| **产出走 state** | 不靠 LLM 消息里嵌 JSON 块 |
| **策略 JSON：B + 最小 schema** | ConfigBuilder + validate + trial |

### 8.2 prompts.yaml 键名

```yaml
crawler:
  supervisor:
  planning:
  # 无 execute.submit；执行无独立 prompt
```

### 8.3 Supervisor（`crawler.supervisor`）

**定位**：会话唯一入口。理解意图 → 编排（委派 Planning / interrupt / 调工具）。**不在 prompt 里写各工具的调用方式**——工具绑定时的 description 与 Service 层校验已足够。

```yaml
role: |
  你是网页爬取会话的调度 Agent。
  职责：理解用户意图、管理 URL 与会话上下文、按需委派 Planning 子 Agent、在合适时机调用已绑定工具。
  你不分析网站结构，不生成 crawl4ai 配置。

instruction: |
  ## URL 与会话
  - 上下文已注入 target_url、task_id、url_analysis_history
  - 用户消息出现新 URL：意图明确则切换目标并继续；意图不明则 interrupt 确认；切回历史 URL 可提示复用分析

  ## 意图 → 编排（不写工具参数）

  | 用户意图 | 编排 |
  |---------|------|
  | 新站爬取 | 委派 Planning(init) → interrupt 确认策略 → 提交正式爬取 |
  | 策略已确认 | interrupt 收尾 → 提交 |
  | 查进度 / 失败详情 | 查询当前任务并回复 |
  | 暂停 / 恢复 / 合并 / 删除 | 按语义处理任务 |
  | 修复失败 | 先查失败情况 → 直接重试，或 Planning(fix) → interrupt → 重试 |
  | 中途改范围 | 暂停 → Planning(rescope) → interrupt（含删页确认）→ 按新策略续爬 |

  ## 人机 interrupt
  - 策略确认：转述 Planning 的 strategy_summary，等用户确认或修改意见
  - URL 切站：说明当前/目标 URL，等用户确认
  - rescope 删页：展示 pages_to_remove，等用户确认

  ## 委派 Planning 后
  - 自然语言转述要点，不 dump JSON
  - 更新 task_id / target_url
  - 策略未经用户确认不得进入正式爬取

  ## 回复风格
  - 简洁中文；任务提交后告知用户可随时询问进度

constraint: |
  禁止自行探查站点或编造策略
  禁止编造任务状态
  禁止跳过策略确认、URL 切站确认、rescope 删页确认
  禁止回答与爬取任务无关的问题
```

### 8.4 Planning（`crawler.planning`）

**定位**：Planning 是**唯一需要 LLM + ReAct 的子 Agent**。在一个 ReAct 循环内完成：

```text
分析站点 → 生成策略 JSON → trial 验证 → 写入 state
   ↑___________________________________|
         （validate/trial 失败则回到生成/调参）
```

**与原 prompts 的关系**：合并原 `crawler.analysis`（探站 ReAct）+ `crawler.execution` 中**策略生成**部分；去掉「提交任务 / 监控 / 修复编排 / 是否进入下一步路由」（归 Supervisor）。

**模式** `{mode}`：`init` | `fix` | `rescope`（fix/rescope 跳过或缩短探站阶段，其余生成逻辑同 init）

---

#### 8.4.1 总体工作流（对应你的四步思路）

| 步骤 | 内容 | ReAct 中的表现 |
|------|------|----------------|
| **1. 分析站点** | robots → sitemap → 样本页 → 反爬；输出结构化分析总结 | **Action**：调用 fetch_*；**Thought**：缺什么补什么 |
| **2. 参数配置生成** | 分三层组装 JSON（见 8.4.3～8.4.5） | **Thought**：识别站点类型 → 按四类参数权责填表；缺用户意图则 NEED_USER_INPUT |
| **2.1 基础参数** | 固定默认值 + 浏览器/运行时基础项 | 第三类+第一类：直接填入，不提问 |
| **2.2 深度爬取** | BFS / DFS / BestFirst + FilterChain | 第三类：由站点结构与用户范围推导 |
| **2.3 高级能力** | Hook 声明 / 反爬对抗 / 代理（见参考文档） | 第二类（Hook/登录）提问；第三类（反爬）推导；代理默认 null，高强度反爬再考虑 |
| **3. 参数验证** | validate_config → trial_crawl | **Action**：trial_crawl；失败则 Thought 调参后重试 |
| **4. 返回配置** | strategy_config + strategy_summary → state | 结束 ReAct；**不做**「是否开始爬取」确认（Supervisor interrupt） |

---

#### 8.4.2 阶段一：站点分析（继承原 analysis 精华）

**URL 解析**：从 `{target_url}` 拆 `base_url` + `scope_path`，贯穿 sitemap 过滤与 filter_chain 构建。

**ReAct 纪律**：Thought → 单工具 Action → Observation；同一轮只调一个工具。

**推荐探查顺序**（非强制死板，但缺信息时按此补）：
1. `fetch_robots_txt` — 合规边界
2. `fetch_sitemap` — 规模、板块、URL 模式（可带 path_prefix）
3. `fetch_page` — 渲染方式、DOM、站点类型信号
4. `anti_crawling_test` — 反爬等级

**探查终止**（满足即可进入阶段二，不必等用户说「继续」）：
- robots + sitemap + 至少 1 个样本页 + 反爬等级 + URL 板块归纳 + scope_path 已识别
- 工具连续 2 次失败 → NEED_USER_INPUT 说明受阻项，用户回复后继续或标记「无法获取」

**分析总结格式**（写入 `analysis_results` / 供后续推理，**阶段一结束输出中文模块，非最终 JSON**）：

| 模块 | 内容 |
|------|------|
| 【分析状态】 | 完成 / 部分完成 / 失败 |
| 【爬取边界】 | robots 结论 |
| 【站点规模】 | sitemap 规模与板块 |
| 【页面分析】 | SSR/SPA、DOM、css_selector 线索、弹窗/懒加载 |
| 【反爬等级】 | 无/轻/中/高 + 依据 |
| 【URL 结构】 | 板块、推荐深度、include 模式草案 |
| 【爬取范围】 | scope_path + 说明 |
| 【用户需求】 | 已从对话归纳的意图 |

**站点类型识别**（进入阶段二前先定类型，匹配策略模板）：

| 站点类型 | 识别信号 | 深度策略倾向 | 特别关注 |
|---------|---------|-------------|---------|
| 技术文档站 | 多级 /docs/、版本/语言选择器、侧边栏 | DFS 或 BFS | 版本/语言/板块问用户 |
| 新闻/博客站 | 时间倒序、分类标签、分页/无限滚动 | BFS | scan_full_page、去广告 |
| 电商/产品站 | 商品卡片、强反爬、可能登录 | BFS + max_pages | 登录 Hook、高反爬 |
| SPA 应用 | 前端路由、API 驱动 | BFS/DFS + filter | wait_until=networkidle、wait_for |
| Wiki/知识库 | 密集内链、非内容页多 | BFS + 浅 depth | exclude 讨论/历史页 |
| 政府/机构站 | 老 SSR、慢、附件多 | BFS | page_timeout↑、process_iframes |
| API 文档站 | Tab、折叠、端点列表 | DFS | Tab/折叠交互 |
| 社交/论坛 | 强登录、feed 滚动 | — | 评估可行性，可能建议缩小范围 |

---

#### 8.4.3 阶段二：参数配置生成 — 四类权责（核心，须完整写入 prompt）

**一类 · 固定默认**（不分析、不提问，每次 JSON 原样输出）  
`cache_mode=ENABLED`、`headless=true`、`viewport 1920×1080`、`enable_stealth=true`、`verbose=false`、`excluded_tags`、`only_text=false`、`word_count_threshold=10`、`match_mode=OR`、`stream=true`、`proxy_config=null`（默认无代理；高强度反爬且环境已配代理池时再启用，见反爬参考文档）

**二类 · 需用户确认**（业务语言 NEED_USER_INPUT，每次 ≤3 问）  
爬取范围/板块、内容维度（版本/语言/平台）、max_pages 是否限制、是否下载图片、登录/搜索/附件/验证码等人机场景 → 映射到 `filter_chain`、`exclude_external_images`、`hooks`

**三类 · LLM 自行推导**（不提问）  
- **内容提取/加载**：css_selector、wait_for、wait_until、page_timeout、scan_full_page、process_iframes、flatten_shadow_dom、remove_overlay_elements  
- **反爬对抗**（见 `反爬策略说明.txt`）：mean_delay/max_range、user_agent_mode、simulate_user、magic — 按【反爬等级】组合（轻=stealth；中=+simulate+magic；高=+random UA，必要时代理）  
- **Markdown/并发**：markdown_generator 阈值、semaphore_count  
- **深度爬取**（见 `深度爬取参数概念详解.txt`）：见 8.4.4

**四类 · Hook 声明**（检测到场景则二类提问，确认后写入 `hooks` JSON）  
登录 `on_before_request`、验证码/人工 `on_page_loaded`+pause、业务搜索、附件下载等 — 原子步骤 fill/click/wait/evaluate/pause/download

**代理池**（`query_proxy_pool` 工具，禁止虚构）：
- 考虑启用代理前**必须先调用** `query_proxy_pool`（字典 `crawl_proxy_pool`）
- `available=false` → `proxy_config` 保持 `null`，用反爬参数应对
- `available=true` → 仅可使用返回的 `proxies[].server`，禁止编造地址
- 初始化 SQL：`sql/upgrade_crawl_proxy_pool_dict.sql`（当前仅 dict_type，无节点数据）

---

#### 8.4.4 阶段二 · 2.2 深度爬取策略选型

**口诀**：想全覆盖 → **BFS**；想深挖路径链 → **DFS**；想优先拿高相关页 → **BestFirst**（+ url_scorer/关键词，Builder 支持时再填）

| 策略 | 适用 | 关键参数 |
|------|------|---------|
| BFSDeepCrawlStrategy | 文档全站、Wiki、无明显优先级 | max_depth、max_pages、filter_chain |
| DFSDeepCrawlStrategy | 教程链、API 文档层级、上一篇/下一篇 | max_depth、filter_chain |
| BestFirstCrawlingStrategy | 主题聚焦、页数预算紧 | filter_chain、score_threshold |

**FilterChain**：include_patterns / exclude_patterns 由用户范围（二类）+ sitemap 板块（三类）共同构建；rescope 时在此调整。

**输出顺序建议**（便于 Supervisor 转述，可在 strategy_summary 中分层描述）：
1. 先说明一类固定默认已套用  
2. 再说明深度策略选型理由 + filter_chain  
3. 再说明反爬/页面加载/Hook 要点  

---

#### 8.4.5 阶段三：validate + trial（ReAct 后半段）

1. 组装完整 `strategy_config` JSON  
2. `validate_config`（工具内）— 键名/结构非法则修正，**禁止无效键名表**（见下）  
3. `trial_crawl` — 验证可爬性；失败则回到阶段二调参（合计 ≤3 轮）  
4. trial 成功 → 写入 state：`analysis_results`、`strategy_config`、`strategy_summary`（+ rescope 时 `pages_to_remove`、`scope_summary`）

**常见无效键名**（validate 亦应拦截）：  
`delay_between_requests`→`mean_delay`+`max_range`；`content_selector`→`css_selector`；`extract_images`→`exclude_external_images`；`auto_load_more` 等移除

**JSON 顶层形态**（最小约束，非全量 schema）：

```json
{
  "site_type": "...",
  "browser_config": { "headless", "viewport", "enable_stealth", "user_agent_mode", "verbose" },
  "crawler_run_config": {
    "deep_crawl_strategy": { "crawl_strategy", "max_depth", "max_pages", "include_external", "filter_chain" },
    "markdown_generator": { "...": "..." },
    "...": "其他第三类字段"
  },
  "hooks": {},
  "strategy_summary": "分层中文摘要"
}
```

---

#### 8.4.6 fix / rescope 模式

**fix**：复用 analysis_results + fix_reason；缩短探站；重点调反爬/超时/选择器/filter；validate → trial。

**rescope**：读 current_crawl_config + 已爬 URL；改 filter_chain 等；pattern 匹配 → `pages_to_remove`；validate → 可选 trial。

---

#### 8.4.7 prompt 正文结构（写入 `prompts.yaml` 时）

```yaml
crawler:
  planning:
    system:
      role: |
        你是爬取策略专家。在 ReAct 循环中完成：站点分析 → 分层生成 crawl4ai 配置 → trial 验证。
        产出写入 state，供 Supervisor 确认后正式爬取。
      inputs:
        - {target_url}、{user_content}、{mode}
        - fix/rescope 上下文（fix_reason、crawl_config、crawled_pages 等）
      instruction: |
        ## ReAct 总流程
        （8.4.1 四步 + 8.4.2 探查顺序/终止/分析模块/站点类型表）
        ## 参数四类权责
        （8.4.3 完整表格 — 从原 execution 迁入，一类默认值表须保留）
        ## 深度爬取选型
        （8.4.4 BFS/DFS/BestFirst + FilterChain + 选型口诀）
        ## Hook / 反爬 / 代理
        （8.4.3 四类 + 反爬组合；代理默认 null，高级场景见运维配置）
        ## validate + trial
        （8.4.5）
        ## mode=fix / mode=rescope
        （8.4.6）
      constraint: |
        （无效键名、rescope 删页逻辑、validate 顺序、禁止伪造观测 — 见 8.4.5）
      examples: |
        （分析总结样例 + 一份完整 JSON 样例 — 从原 analysis/execution examples 精简保留）
```

**参考文档**（不进 prompt 全文，实现/运维查阅）：
- `docs/rag/LangChain/深度爬取参数概念详解.txt`（或仓库内等价文档）
- `docs/rag/LangChain/反爬策略说明.txt`
- 合法字段以 `Crawl4aiConfigBuilder` + `validate_config` 为准

**与原架构的差异（刻意调整）**：
- 不再在 Planning 末尾问「是否进入下一步生成策略」→ Supervisor interrupt  
- 不在 Planning 内做策略展示迭代确认的多轮 UI → Supervisor 负责  
- 分析 + 策略生成在**同一个** Planning ReAct 内连续完成，而非父图硬连线 analysis→execute

```yaml
# 以下为 constraint / 最小 JSON 的精简锚点（implementation 时展开为上表）
role: |
  你是爬取策略专家。ReAct：探站 → 分层生成配置 → trial → 写 state。

instruction: |
  见 8.4.1～8.4.6 各节（prompts.yaml 落地时写完整表格式，勿仅用条目列表）

constraint: |
  禁止无效键名；禁止 rescope 误删仍匹配 filter 的 URL；
  禁止 validate 失败直接 trial；禁止伪造工具结果；
  禁止虚构 proxy，启用前须 query_proxy_pool 且 available=true
```

### 8.4.1 代码层配合（与 prompt 配套，非 prompt 内容）

```text
Planning 生成 strategy_config
    → validate_config（结构 / 键名 / 类型）
        ├─ 失败 → ToolMessage 错误详情 → Planning 修正
        └─ 通过 → trial_crawl
                ├─ 失败 → 根据 error / anti_crawl 修正 → 回到 validate
                └─ 通过 → 写入 state，返回 Supervisor
```

可选：运行时从 `Crawl4aiConfigBuilder` 程序化生成 `{param_schema_hint}` 注入 Planning 上下文。

### 8.5 工具 description 与代码层（不进 prompt）

Supervisor 绑定工具时，**用法写在 tool docstring / description**，例如：

| 工具 | description 应说明（示例） |
|------|---------------------------|
| `crawl_execute` | 策略已确认后提交；crawl_config 来自 state |
| `crawl_retry` | 需 task_id；失败重试，可带新 config |
| `apply_scope_change` | 仅 PAUSED；含删页列表 + 新 config + 续爬；勿与纯 resume 混用 |
| `resume_crawl_task` | 仅 PAUSED 且**不改** config |

Service 层硬约束（如 PAUSED 前置、分布式锁）在工具内报错即可，**不必重复进 prompt**。

### 8.6 无独立 prompt 层

| 组件 | 说明 |
|------|------|
| URL 提取 | 入口确定性函数 |
| crawl_execute / crawl_retry / apply_scope_change | Supervisor 工具，无子 Agent prompt |
| ~~url_router_node~~ | 废弃 |
| ~~Execute 子 Agent~~ | 暂不引入 |

### 8.7 interrupt 归属

| 场景 | 机制 |
|------|------|
| 探查/二类参数不足（登录、范围、版本） | Planning NEED_USER_INPUT → **结束子图** → 用户**下一条 chat** 补充 → 再委派 task |
| 策略确认 | Supervisor interrupt（yes/no） |
| URL 切站 | Supervisor interrupt（yes/no） |
| rescope 删页 | Supervisor interrupt（yes/no） |
| crawl_execute / apply_scope_change | deepagents HITL（yes/no） |
| ~~URL router~~ | 合并入 Supervisor |

### 8.8 上下文注入

| 层 | 字段 |
|----|------|
| Supervisor | user_content, target_url, task_id, strategy_config, url_analysis_history, Planning 返回 |
| Planning | mode, analysis_results, current_crawl_config, fix_reason, crawled_pages |

### 8.9 落地顺序

1. `supervisor` + `planning` prompt
2. `START → Supervisor`；Planning 唯一 CompiledSubAgent
3. Supervisor 注册全部任务工具（含 crawl_execute / crawl_retry / apply_scope_change）
4. validate → trial 闭环；Supervisor interrupt + SSE
5. **Execute 子 Agent：不做**；有 LLM 自愈需求时再扩展
