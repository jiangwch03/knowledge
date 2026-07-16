/**
 * 用真实 SSE 片段模拟前端 parseSseBlock 逻辑，验证消息顺序与分组。
 * 运行: node knowledge-web/scripts/simulate_crawler_sse.mjs
 */

const NS = 'tools:17ec8d32-e171-b6b6-6ff6-cbcfeabb7935';

// 从用户提供的 SSE 日志提取的关键事件序列（简化 representative）
const events = [
  ...['我来', '帮', '您分析', '这个网站', '并制定', '爬取', '方案', '。\n\n'].map(c => ({
    event: 'token', data: { content: c, source: 'supervisor' },
  })),
  { event: 'tool_call', data: { tool_call_id: 'call_task', phase: 'call', tool_name: 'task', tool_args: {}, source: 'supervisor' } },
  ...['我来', '分析目标', '网站', '并生成', '合适的爬', '取策略', '配置。', '首先进行', '探站', '分析', '。\n\n'].map(c => ({
    event: 'token', data: { content: c, source: 'subagent', agent_ns: NS },
  })),
  { event: 'tool_call', data: { tool_call_id: 'call_robots', phase: 'call', tool_name: 'fetch_robots_txt', tool_args: {}, source: 'subagent', agent_ns: NS } },
  { event: 'tool_call', data: { tool_call_id: 'call_robots', phase: 'result', tool_name: 'fetch_robots_txt', content: {}, source: 'subagent', agent_ns: NS } },
  { event: 'tool_call', data: { tool_call_id: 'call_sitemap', phase: 'call', tool_name: 'fetch_sitemap', tool_args: {}, source: 'subagent', agent_ns: NS } },
  { event: 'tool_call', data: { tool_call_id: 'call_sitemap', phase: 'result', tool_name: 'fetch_sitemap', content: {}, source: 'subagent', agent_ns: NS } },
  { event: 'tool_call', data: { tool_call_id: 'call_page', phase: 'call', tool_name: 'fetch_page', tool_args: {}, source: 'subagent', agent_ns: NS } },
  { event: 'tool_call', data: { tool_call_id: 'call_page', phase: 'result', tool_name: 'fetch_page', content: {}, source: 'subagent', agent_ns: NS } },
  ...['现在', '我已经', '完成了', '初步的', '探站', '分析', '。'].map(c => ({
    event: 'token', data: { content: c, source: 'subagent', agent_ns: NS },
  })),
  { event: 'tool_call', data: { tool_call_id: 'call_proxy', phase: 'call', tool_name: 'query_proxy_pool', tool_args: {}, source: 'subagent', agent_ns: NS } },
  ...['基于', '分析', '结果，', '我', '生成了', '配置。'].map(c => ({
    event: 'token', data: { content: c, source: 'subagent', agent_ns: NS },
  })),
  { event: 'tool_call', data: { tool_call_id: 'call_task', phase: 'result', tool_name: 'task', content: '子图最终返回', source: 'supervisor' } },
  ...['根据', '规划', '助手的分析', '，总结'].map(c => ({
    event: 'token', data: { content: c, source: 'supervisor' },
  })),
];

function createState() {
  return {
    messages: [],
    parentStreamingContent: '',
    subagentStreamingContent: '',
    currentAgentNs: null,
  };
}

function commitParent(s) {
  const content = s.parentStreamingContent.trim();
  if (content) s.messages.push({ role: 'ai', content });
  s.parentStreamingContent = '';
}

function commitSubagent(s) {
  const content = s.subagentStreamingContent.trim();
  if (content && s.currentAgentNs) {
    s.messages.push({ role: 'ai', content, agentNs: s.currentAgentNs, source: 'subagent' });
  }
  s.subagentStreamingContent = '';
}

function commitAll(s) {
  commitSubagent(s);
  commitParent(s);
}

function upsertTool(s, data, source, agentNs) {
  const tcId = data.tool_call_id || '';
  const phase = data.phase || (data.content !== undefined ? 'result' : 'call');
  const payload = { role: 'tool', toolName: data.tool_name, toolCallId: tcId, phase, source, agentNs };
  if (tcId) {
    const existing = [...s.messages].reverse().find(m => m.role === 'tool' && m.toolCallId === tcId);
    if (existing) { Object.assign(existing, payload); return; }
  }
  s.messages.push(payload);
}

function parseEvent(s, event, data) {
  const source = data.source || 'supervisor';
  const agentNs = data.agent_ns || null;
  if (event === 'token') {
    if (source === 'subagent' && agentNs) {
      s.currentAgentNs = agentNs;
      s.subagentStreamingContent += data.content || '';
    } else {
      commitSubagent(s);
      s.currentAgentNs = null;
      s.parentStreamingContent += data.content || '';
    }
  } else if (event === 'tool_call') {
    commitAll(s);
    upsertTool(s, data, source, agentNs);
  }
}

function groupMessages(messages) {
  const result = [];
  let i = 0;
  while (i < messages.length) {
    const msg = messages[i];
    if (msg.source === 'subagent' && msg.agentNs) {
      const groupAgentNs = msg.agentNs;
      const items = [];
      while (i < messages.length && messages[i].source === 'subagent' && messages[i].agentNs === groupAgentNs) {
        items.push(messages[i]);
        i++;
      }
      result.push({ role: 'subagent_group', agentNs: groupAgentNs, items });
    } else {
      result.push(msg);
      i++;
    }
  }
  return result;
}

function summarizeItem(m) {
  if (m.role === 'ai') return `ai:${m.content.slice(0, 20)}...`;
  if (m.role === 'tool') return `tool:${m.toolName}(${m.phase})`;
  return m.role;
}

const s = createState();
for (const { event, data } of events) parseEvent(s, event, data);
commitAll(s); // finally

console.log('=== messages 顺序 ===');
s.messages.forEach((m, i) => console.log(`${i}: ${summarizeItem(m)}`));

const grouped = groupMessages(s.messages);
console.log('\n=== groupedMessages 子图框内顺序 ===');
const sub = grouped.find(g => g.role === 'subagent_group');
if (sub) {
  sub.items.forEach((m, i) => console.log(`  ${i}: ${summarizeItem(m)}`));
  const firstAi = sub.items.findIndex(m => m.role === 'ai');
  const firstTool = sub.items.findIndex(m => m.role === 'tool');
  console.log(`\n首条 AI 在 index ${firstAi}, 首个工具在 index ${firstTool}`);
  console.log(firstAi < firstTool ? '✓ 文字在工具前' : '✗ 文字在工具后 — 顺序错误');
} else {
  console.log('未找到 subagent_group');
}

// 模拟流式渲染：有已提交 group 时，streaming 是否应合并进同一框
console.log('\n=== 流式渲染场景 ===');
console.log('当 tools 已提交、subagentStreamingContent 非空时：');
console.log('- 当前实现：底部新开一个绿色框（用户看到两个框）');
console.log('- 正确实现：流式内容追加到已有 subagent_group 末尾');
