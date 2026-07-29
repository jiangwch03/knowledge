/**
 * Agent SSE 聊天流处理（从网页爬取页抽离的成熟实现）。
 *
 * 负责：token 匀速吐字、tool_call 卡片合并、agent_group 分组、
 * done/error 收尾、历史扁平行 → 时间线。
 *
 * 业务旁路事件（business / strategy / user_choice 等）通过 handlers 注入，
 * 不在此硬编码爬取/问答差异。
 */
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

/**
 * @param {object} [options]
 * @param {Record<string, (data: any, ctx: { finalizeAll: Function, messages: import('vue').Ref }) => void>} [options.handlers]
 *        自定义 SSE 事件：handlers[eventName](data, ctx)
 */
export function useAgentSseChat(options = {}) {
  const handlers = options.handlers || {}

  const messages = ref([])
  const streaming = ref(false)
  const expandedGroupKeys = ref([])
  const messageAreaRef = ref(null)
  let abortController = null

  const hasActiveStreaming = computed(() =>
    messages.value.some(
      (m) =>
        (m.role === 'agent_group' && groupHasStreaming(m)) ||
        (m.role === 'ai' && m.streaming && !m.type)
    )
  )

  function groupHasStreaming(groupMsg) {
    return (groupMsg.items || []).some((item) => item.role === 'ai' && item.streaming)
  }

  function isGroupExpanded(groupMsg) {
    return expandedGroupKeys.value.includes(groupMsg._key)
  }

  function setGroupExpanded(groupMsg, names) {
    const shouldExpand = names.includes(groupMsg._key)
    const idx = expandedGroupKeys.value.indexOf(groupMsg._key)
    if (shouldExpand && idx === -1) {
      expandedGroupKeys.value.push(groupMsg._key)
    } else if (!shouldExpand && idx !== -1) {
      expandedGroupKeys.value.splice(idx, 1)
    }
  }

  function _agentCtxKey(source, agentNs) {
    return source === 'subagent' && agentNs ? `subagent:${agentNs}` : 'supervisor'
  }

  function _isSubagentSource(source) {
    return source === 'subagent'
  }

  function _finalizeSupervisorStreaming() {
    const last = messages.value[messages.value.length - 1]
    if (last?.role !== 'ai' || last.type || !last.streaming) return
    last.streaming = false
    last.content = (last.content || '').trimEnd()
    if (!last.content.trim()) {
      messages.value.pop()
    }
  }

  function _finalizeGroupStreaming(group) {
    if (!group?.items?.length) return
    const lastAi = [...group.items].reverse().find((item) => item.role === 'ai' && item.streaming)
    if (!lastAi) return
    lastAi.streaming = false
    lastAi.content = (lastAi.content || '').trimEnd()
    if (!lastAi.content.trim()) {
      const idx = group.items.indexOf(lastAi)
      if (idx >= 0) group.items.splice(idx, 1)
    }
  }

  function finalizeAllStreaming() {
    _flushTokenQueue()
    messages.value.forEach((msg) => {
      if (msg.role === 'agent_group') {
        _finalizeGroupStreaming(msg)
      } else if (msg.role === 'ai' && msg.streaming && !msg.type) {
        msg.streaming = false
        msg.content = (msg.content || '').trimEnd()
      }
    })
    messages.value = messages.value.filter(
      (msg) => !(msg.role === 'ai' && !msg.type && !(msg.content || '').trim())
    )
  }

  function _getOrCreateSubagentGroup(agentNs) {
    const ctxKey = _agentCtxKey('subagent', agentNs)
    const last = messages.value[messages.value.length - 1]
    if (last?.role === 'agent_group' && last._ctxKey === ctxKey) {
      return last
    }
    if (last?.role === 'agent_group') {
      _finalizeGroupStreaming(last)
    }
    const group = {
      _key: `grp_${ctxKey}_${Date.now()}`,
      _ctxKey: ctxKey,
      role: 'agent_group',
      source: 'subagent',
      agentNs: agentNs || undefined,
      items: [],
    }
    messages.value.push(group)
    if (!expandedGroupKeys.value.includes(group._key)) {
      expandedGroupKeys.value.push(group._key)
    }
    return group
  }

  /** SSE token 缓冲：收包与绘制解耦，按帧匀速吐字 */
  const _tokenQueue = []
  let _tokenDrainRaf = null
  let _lastStreamScrollAt = 0
  let _isFlushingTokens = false

  function _pendingTokenChars() {
    return _tokenQueue.reduce((sum, item) => sum + item.content.length, 0)
  }

  function _charsPerFrame() {
    const pending = _pendingTokenChars()
    if (pending > 800) return Math.min(pending, 240)
    if (pending > 300) return 96
    if (pending > 100) return 48
    return 28
  }

  function _maybeScrollDuringStream() {
    const now = performance.now()
    if (now - _lastStreamScrollAt < 80) return
    _lastStreamScrollAt = now
    if (messageAreaRef.value) {
      messageAreaRef.value.scrollTop = messageAreaRef.value.scrollHeight
    }
  }

  function _commitToken(source, agentNs, content) {
    const chunk = content || ''
    if (!chunk) return
    if (!_isSubagentSource(source)) {
      const last = messages.value[messages.value.length - 1]
      if (last?.role === 'ai' && !last.type && last.streaming) {
        last.content += chunk
        return
      }
      messages.value.push({
        _key: `ai_${Date.now()}`,
        role: 'ai',
        content: chunk,
        streaming: true,
      })
      return
    }
    const group = _getOrCreateSubagentGroup(agentNs)
    const lastItem = group.items[group.items.length - 1]
    if (lastItem?.role === 'ai' && lastItem.streaming) {
      lastItem.content += chunk
      return
    }
    group.items.push({ role: 'ai', content: chunk, streaming: true })
  }

  function _drainTokenQueue() {
    _tokenDrainRaf = null
    let budget = _charsPerFrame()
    while (budget > 0 && _tokenQueue.length) {
      const item = _tokenQueue[0]
      if (item.content.length <= budget) {
        budget -= item.content.length
        _commitToken(item.source, item.agentNs, item.content)
        _tokenQueue.shift()
      } else {
        const take = item.content.slice(0, budget)
        item.content = item.content.slice(budget)
        _commitToken(item.source, item.agentNs, take)
        budget = 0
      }
    }
    _maybeScrollDuringStream()
    if (_tokenQueue.length) {
      _tokenDrainRaf = requestAnimationFrame(_drainTokenQueue)
    }
  }

  function _ensureTokenDrain() {
    if (_tokenDrainRaf == null) {
      _tokenDrainRaf = requestAnimationFrame(_drainTokenQueue)
    }
  }

  function _flushTokenQueue() {
    if (_tokenDrainRaf != null) {
      cancelAnimationFrame(_tokenDrainRaf)
      _tokenDrainRaf = null
    }
    if (_isFlushingTokens) return
    _isFlushingTokens = true
    try {
      while (_tokenQueue.length) {
        const item = _tokenQueue.shift()
        _commitToken(item.source, item.agentNs, item.content)
      }
    } finally {
      _isFlushingTokens = false
    }
  }

  function clearTokenQueue() {
    if (_tokenDrainRaf != null) {
      cancelAnimationFrame(_tokenDrainRaf)
      _tokenDrainRaf = null
    }
    _tokenQueue.length = 0
  }

  function _appendToken(source, agentNs, content) {
    const chunk = content || ''
    if (!chunk) return
    _tokenQueue.push({ source, agentNs, content: chunk })
    _ensureTokenDrain()
  }

  function formatToolJson(value) {
    if (value == null) return ''
    if (typeof value === 'string') {
      try {
        return JSON.stringify(JSON.parse(value), null, 2)
      } catch {
        return value
      }
    }
    return JSON.stringify(value, null, 2)
  }

  function _mergeToolCallItem(existing, incoming) {
    const phase = incoming.phase || (incoming.toolResult != null ? 'result' : 'call')
    return {
      ...existing,
      role: 'tool',
      toolName: incoming.toolName || existing.toolName,
      toolCallId: incoming.toolCallId || existing.toolCallId,
      phase,
      toolArgs: incoming.toolArgs != null ? incoming.toolArgs : existing.toolArgs,
      toolResult: incoming.toolResult != null ? incoming.toolResult : existing.toolResult,
    }
  }

  function _buildToolCallItem(data) {
    const phase = data.phase || (data.content !== undefined ? 'result' : 'call')
    return {
      role: 'tool',
      toolName: data.tool_name,
      toolCallId: data.tool_call_id || '',
      phase,
      toolArgs: data.tool_args,
      toolResult: phase === 'result' ? data.content : undefined,
    }
  }

  function parseMessageRemark(remark) {
    if (!remark) return {}
    try {
      const meta = JSON.parse(remark)
      if (meta?.source === 'subagent' && meta.agent_ns) {
        return { source: 'subagent', agentNs: meta.agent_ns }
      }
    } catch {
      /* ignore */
    }
    return {}
  }

  function parseStoredToolRow(m) {
    if (m.role !== 'tool') return m
    let toolArgs
    let toolResult
    let toolName = m.toolName
    if (m.content) {
      try {
        const parsed = JSON.parse(m.content)
        if (parsed && typeof parsed === 'object') {
          if (parsed.tool_args != null) toolArgs = parsed.tool_args
          if (parsed.result != null) toolResult = parsed.result
          if (!toolName && parsed.tool_name) toolName = parsed.tool_name
        }
      } catch {
        /* 非 JSON 内容保持原样 */
      }
    }
    return {
      role: m.role,
      toolName,
      toolCallId: m.toolCallId,
      phase: toolResult != null ? 'result' : 'call',
      toolArgs,
      toolResult,
      ...parseMessageRemark(m.remark),
    }
  }

  function _upsertToolCall(data, source = 'supervisor', agentNs = null) {
    _flushTokenQueue()
    const tcId = data.tool_call_id || ''
    const incoming = _buildToolCallItem(data)

    if (!_isSubagentSource(source)) {
      _finalizeSupervisorStreaming()
      if (tcId) {
        const existing = messages.value.find((item) => item.role === 'tool' && item.toolCallId === tcId)
        if (existing) {
          Object.assign(existing, _mergeToolCallItem(existing, incoming))
          return
        }
      }
      messages.value.push({ ...incoming, _key: `tool_${tcId || Date.now()}` })
      return
    }

    const group = _getOrCreateSubagentGroup(agentNs)
    _finalizeGroupStreaming(group)

    if (tcId) {
      const existing = group.items.find((item) => item.role === 'tool' && item.toolCallId === tcId)
      if (existing) {
        Object.assign(existing, _mergeToolCallItem(existing, incoming))
        return
      }
    }
    group.items.push(incoming)
  }

  function _isAgentFlatRow(row) {
    if (row.type) return false
    return row.role === 'ai' || row.role === 'tool'
  }

  function _flatRowToGroupItem(row) {
    if (row.role === 'tool') {
      return {
        role: 'tool',
        toolName: row.toolName,
        toolCallId: row.toolCallId,
        phase: row.phase || (row.toolResult != null ? 'result' : 'call'),
        toolArgs: row.toolArgs,
        toolResult: row.toolResult,
      }
    }
    return { role: 'ai', content: row.content || '', streaming: false }
  }

  function _flatRowToTimelineMsg(row) {
    if (row.role === 'tool') {
      return {
        role: 'tool',
        toolName: row.toolName,
        toolCallId: row.toolCallId,
        phase: row.phase || (row.toolResult != null ? 'result' : 'call'),
        toolArgs: row.toolArgs,
        toolResult: row.toolResult,
      }
    }
    return { role: 'ai', content: row.content || '', streaming: false }
  }

  function rowsToTimeline(rows) {
    const timeline = []
    let i = 0
    while (i < rows.length) {
      const row = rows[i]
      if (!_isAgentFlatRow(row)) {
        timeline.push({ ...row, _key: row._key || `msg_${timeline.length}` })
        i += 1
        continue
      }
      if (row.source !== 'subagent') {
        timeline.push({
          ..._flatRowToTimelineMsg(row),
          _key: row._key || `msg_${timeline.length}`,
        })
        i += 1
        continue
      }
      const ctxKey = _agentCtxKey('subagent', row.agentNs)
      const agentNs = row.agentNs
      const items = []
      while (i < rows.length && _isAgentFlatRow(rows[i])) {
        const currentKey = _agentCtxKey(
          rows[i].source === 'subagent' ? 'subagent' : 'supervisor',
          rows[i].agentNs
        )
        if (currentKey !== ctxKey) break
        items.push(_flatRowToGroupItem(rows[i]))
        i += 1
      }
      timeline.push({
        _key: `grp_${ctxKey}_${timeline.length}`,
        _ctxKey: ctxKey,
        role: 'agent_group',
        source: 'subagent',
        agentNs,
        items,
      })
    }
    return timeline
  }

  watch(
    () => messages.value.filter((m) => m.role === 'agent_group').map((m) => m._key),
    (keys) => {
      keys.forEach((key) => {
        if (!expandedGroupKeys.value.includes(key)) {
          expandedGroupKeys.value.push(key)
        }
      })
    },
    { immediate: true }
  )

  function resetChatState() {
    if (abortController) {
      abortController.abort()
      abortController = null
    }
    clearTokenQueue()
    streaming.value = false
    expandedGroupKeys.value = []
  }

  function parseSseBlock(block) {
    const eventMatch = block.match(/event:\s*(.+)/)
    const dataMatch = block.match(/data:\s*(.+)/)
    if (!eventMatch || !dataMatch) return

    const event = eventMatch[1].trim()
    let data
    try {
      data = JSON.parse(dataMatch[1])
    } catch {
      return
    }

    const source = data.source || 'supervisor'
    const agentNs = data.agent_ns || null
    const ctx = { finalizeAll: finalizeAllStreaming, messages }

    if (event === 'token') {
      _appendToken(source, agentNs, data.content || '')
    } else if (event === 'tool_call') {
      _upsertToolCall(data, source, agentNs)
    } else if (event === 'done') {
      finalizeAllStreaming()
    } else if (event === 'error') {
      finalizeAllStreaming()
      ElMessage.error(data.message || 'Agent 执行出错')
      console.warn('[SSE] Agent error event:', data)
    } else if (typeof handlers[event] === 'function') {
      handlers[event](data, ctx)
    }
  }

  async function readSseStream(response) {
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n\n')
      buffer = lines.pop() || ''
      for (const block of lines) {
        if (block.trim()) parseSseBlock(block)
      }
    }
  }

  function createAbortController() {
    abortController = new AbortController()
    return abortController
  }

  function getAbortSignal() {
    return abortController?.signal
  }

  function stopGeneration() {
    if (abortController) abortController.abort()
    _flushTokenQueue()
  }

  function appendHumanMessage(content) {
    messages.value.push({ role: 'human', content, _key: `human_${Date.now()}` })
  }

  function pushMessage(msg) {
    messages.value.push(msg)
  }

  async function scrollToBottom() {
    await nextTick()
    if (messageAreaRef.value) {
      messageAreaRef.value.scrollTop = messageAreaRef.value.scrollHeight
    }
  }

  function setTimelineFromFlatRows(flatRows) {
    messages.value = rowsToTimeline(flatRows)
  }

  return {
    messages,
    streaming,
    expandedGroupKeys,
    messageAreaRef,
    hasActiveStreaming,
    groupHasStreaming,
    isGroupExpanded,
    setGroupExpanded,
    formatToolJson,
    parseStoredToolRow,
    parseMessageRemark,
    rowsToTimeline,
    setTimelineFromFlatRows,
    resetChatState,
    clearTokenQueue,
    finalizeAllStreaming,
    parseSseBlock,
    readSseStream,
    createAbortController,
    getAbortSignal,
    stopGeneration,
    appendHumanMessage,
    pushMessage,
    scrollToBottom,
  }
}
