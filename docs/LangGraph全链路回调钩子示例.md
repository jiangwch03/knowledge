# LangGraph 全链路回调钩子示例

## 核心概念

`BaseCallbackHandler` 在 LangGraph 执行过程中覆盖三个层级：

| 层级 | 回调方法 | 触发时机 | 区分标识 |
|------|---------|---------|---------|
| **Graph** | `on_chain_start / on_chain_end` | 整张图（含子图）开始/结束 | `serialized['name']` |
| **Node** | `on_chain_start / on_chain_end` | 每个节点开始/结束 | `serialized['name']`（节点名） |
| **Tool** | `on_tool_start / on_tool_end` | 每个工具调用开始/结束 | `serialized['name']`（工具名） |
| **LLM** | `on_llm_start / on_llm_end` | LLM 调用开始/结束 | `kwargs['serialized']['kwargs']['model_name']` |

## 调用链示意图

```
Parent Graph  (on_chain_start/end)
  ├── url_router       (on_chain_start/end)
  ├── analysis_subgraph (on_chain_start/end)    ← 子图也是 on_chain
  │   ├── analyze       (on_chain_start/end)
  │   ├── tools         (on_chain_start/end)
  │   │   ├── fetch_robots_txt (on_tool_start/end)
  │   │   └── fetch_sitemap    (on_tool_start/end)
  │   └── collect       (on_chain_start/end)
  └── execute_subgraph  (on_chain_start/end)
      └── ...
```

## 示例代码

```python
"""
LangGraph 全链路回调钩子示例

展示 LangGraph 执行过程中，BaseCallbackHandler 在三个层级（Graph/Node/Tool）的触发顺序。
可直接运行，无需任何外部依赖（除 langchain/langgraph 外）。
"""
import asyncio
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict


# ── 1. 自定义钩子 ──────────────────────────────────────────────

class TraceHandler(BaseCallbackHandler):
    """全链路追踪钩子：Graph → Node → Tool → LLM 逐级打印"""

    _chain_depth: int = 0

    async def on_chain_start(self, serialized: dict, inputs: dict, **kwargs: Any) -> None:
        self._chain_depth += 1
        name = serialized.get('name', 'unknown')
        indent = '  ' * self._chain_depth
        print(f'{indent}[chain  START] {name}')

    async def on_chain_end(self, outputs: dict, **kwargs: Any) -> None:
        name = kwargs.get('name', '') or kwargs.get('serialized', {}).get('name', 'unknown')
        indent = '  ' * self._chain_depth
        print(f'{indent}[chain  END  ] {name}')
        self._chain_depth -= 1

    async def on_chain_error(self, error: Exception, **kwargs: Any) -> None:
        name = kwargs.get('serialized', {}).get('name', 'unknown')
        print(f'  [chain  ERROR] {name}: {error}')

    async def on_tool_start(self, serialized: dict, input_str: str, **kwargs: Any) -> None:
        name = serialized.get('name', 'unknown')
        print(f'    [tool  START] {name}  args={input_str[:120]}')

    async def on_tool_end(self, output: str, **kwargs: Any) -> None:
        name = kwargs.get('name', '') or kwargs.get('serialized', {}).get('name', 'unknown')
        print(f'    [tool  END  ] {name}')

    async def on_llm_start(self, serialized: dict, prompts: list[str], **kwargs: Any) -> None:
        print(f'      [llm   START] model={serialized.get("kwargs", {}).get("model_name", "unknown")}')

    async def on_llm_end(self, response, **kwargs: Any) -> None:
        print(f'      [llm   END  ]')


# ── 2. 一个简单的工具 ──────────────────────────────────────────

@tool
def greet(name: str) -> str:
    """向某人打招呼"""
    return f'你好，{name}!'


# ── 3. 构建图 ──────────────────────────────────────────────────

class State(TypedDict):
    messages: list


def call_model(state: State) -> dict:
    """LLM 节点"""
    return {'messages': [llm.invoke(state['messages'])]}


def should_continue(state: State) -> str:
    messages = state['messages']
    last = messages[-1]
    return 'tools' if getattr(last, 'tool_calls', None) else END


# 主图
builder = StateGraph(State)
builder.add_node('agent', call_model)
builder.add_node('tools', ToolNode([greet]))
builder.add_edge(START, 'agent')
builder.add_conditional_edges('agent', should_continue, {'tools': 'tools', END: END})
builder.add_edge('tools', 'agent')

llm = ChatOpenAI(model='gpt-4o-mini', temperature=0)
graph = builder.compile()


# ── 4. 运行并观察回调链 ──────────────────────────────────────

async def main():
    handler = TraceHandler()
    config = {'callbacks': [handler]}

    print('══════ 开始执行 Graph ══════')
    await graph.ainvoke(
        {'messages': [HumanMessage(content='你好，我叫张三')]},
        config=config,
    )
    print('══════ 执行完毕 ══════')

asyncio.run(main())
```

## 预期输出

```
══════ 开始执行 Graph ══════
[chain  START] LangGraph            ← 根图
  [chain  START] agent              ← agent 节点
    [llm   START] model=gpt-4o-mini  ← LLM 调用
    [llm   END  ]
  [chain  END  ] agent
  [chain  START] tools              ← tools 节点
    [tool  START] greet  args={'name': '张三'}  ← 工具调用
    [tool  END  ] greet
  [chain  END  ] tools
  [chain  START] agent              ← 第二次 agent（带结果）
    [llm   START] ...
    [llm   END  ]
  [chain  END  ] agent
[chain  END  ] LangGraph
══════ 执行完毕 ══════
```

## 在项目中使用

在现有 `crawler_agent_service.py` 中只需改 config：

```python
# 改前
config = {'configurable': {'thread_id': str(session_id)}}

# 改后
config = {
    'configurable': {'thread_id': str(session_id)},
    'callbacks': [TraceHandler()],
}
```

Callbacks 通过 `config` 沿着 Runnable 树自动传播到所有子图、节点、工具、LLM，无需额外改造。
