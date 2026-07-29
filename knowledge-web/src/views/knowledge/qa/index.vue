<template>
  <div class="app-container qa-container">
    <el-container style="height: 100%">
      <el-aside :width="sidebarWidth + 'px'" class="session-sidebar">
        <div class="sidebar-header">
          <el-button type="primary" class="new-chat-btn" icon="Plus" @click="handleNewSession">
            新建问答会话
          </el-button>
        </div>
        <div class="session-search">
          <el-input v-model="searchTitle" placeholder="搜索会话" clearable prefix-icon="Search" size="small" />
        </div>
        <div class="session-list" v-loading="sessionLoading">
          <div
            v-for="session in filteredSessions"
            :key="session.sessionId"
            :class="['session-item', currentSessionId === session.sessionId ? 'active' : '']"
            @click="handleSelectSession(session.sessionId)"
          >
            <div class="session-icon">
              <el-icon><ChatDotRound /></el-icon>
            </div>
            <div class="session-info">
              <div class="session-title">{{ session.sessionTitle || '新会话' }}</div>
              <div class="session-meta">
                <el-tag :type="session.status === 'ACTIVE' ? 'success' : 'info'" size="small">
                  {{ session.status === 'ACTIVE' ? '活跃' : '已关闭' }}
                </el-tag>
                <span class="session-time">{{ parseTime(session.createTime) }}</span>
              </div>
            </div>
            <el-dropdown trigger="click" @command="handleSessionCommand($event, session)">
              <el-button class="more-btn" link icon="MoreFilled" @click.stop></el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="rename">重命名</el-dropdown-item>
                  <el-dropdown-item command="close" :disabled="session.status === 'CLOSED'">关闭</el-dropdown-item>
                  <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
          <div v-if="filteredSessions.length === 0 && !sessionLoading" class="empty-session">暂无会话</div>
        </div>
      </el-aside>

      <div class="resize-handle" @mousedown="startResize"></div>

      <el-main class="chat-main">
        <div v-if="!currentSessionId" class="welcome-screen">
          <div class="welcome-icon">
            <el-icon :size="60"><ChatDotRound /></el-icon>
          </div>
          <h2>知识问答</h2>
          <p>选择或创建一个会话，基于知识库混合检索进行多轮问答</p>
        </div>

        <template v-else>
          <div class="chat-header">
            <el-icon><ChatDotRound /></el-icon>
            <span class="chat-header-title">{{ currentSessionTitle }}</span>
            <el-tag type="info" size="small" effect="plain">ID: {{ currentSessionId }}</el-tag>
          </div>

          <div class="message-area" ref="messageAreaRef">
            <div
              v-for="(msg, idx) in messages"
              :key="msg._key || idx"
              :class="[
                'message-item',
                'message-' + (msg.role === 'agent_group' || (msg.role === 'ai' && !msg.type) ? 'ai' : msg.role),
                {
                  'ai-typing':
                    streaming &&
                    idx === messages.length - 1 &&
                    ((msg.role === 'agent_group' && groupHasStreaming(msg)) ||
                      (msg.role === 'ai' && msg.streaming && !msg.type)),
                },
              ]"
            >
              <!-- 知识库引用（business SSE / 历史），默认折叠 -->
              <div v-if="msg.role === 'business'" class="citations-card">
                <el-collapse>
                  <el-collapse-item>
                    <template #title>
                      <span class="citations-title">知识库引用</span>
                      <span class="citation-meta" style="margin-left: 8px">
                        {{ msg.hits?.length ? `${msg.hits.length} 条` : '无命中' }}
                      </span>
                    </template>
                    <div v-if="msg.searchQuery" class="citation-meta">检索词：{{ msg.searchQuery }}</div>
                    <div v-if="!msg.hits?.length" class="muted">本轮无命中</div>
                    <div v-for="(hit, i) in msg.hits" :key="i" class="citation-item">
                      <div class="citation-meta">
                        #{{ i + 1 }} docId={{ hit.docId }} chunkId={{ hit.chunkId }}
                        <span v-if="hit.parentChunkId">（已回填父片 {{ hit.parentChunkId }}）</span>
                      </div>
                      <div class="citation-text">{{ hit.text }}</div>
                    </div>
                  </el-collapse-item>
                </el-collapse>
              </div>

              <div v-else-if="msg.role === 'human'" class="bubble user-bubble">
                <span>{{ msg.content }}</span>
              </div>

              <div
                v-else-if="msg.role === 'ai' && !msg.type"
                class="bubble assistant-bubble"
                :class="{ 'ai-text-streaming': msg.streaming }"
              >
                <MarkdownRender :content="msg.content || ''" class="ai-md-stream" />
              </div>

              <div v-else-if="msg.role === 'tool'" class="tool-card">
                <el-collapse>
                  <el-collapse-item>
                    <template #title>
                      <el-tag type="warning" size="small">🔧 {{ msg.toolName || '工具调用' }}</el-tag>
                      <el-tag v-if="msg.phase === 'call'" type="info" size="small" style="margin-left: 8px">
                        <el-icon class="is-loading"><Loading /></el-icon>
                        调用中
                      </el-tag>
                    </template>
                    <div v-if="msg.toolArgs != null" class="tool-section">
                      <div class="tool-section-label">调用参数</div>
                      <pre class="tool-content">{{ formatToolJson(msg.toolArgs) }}</pre>
                    </div>
                    <div v-if="msg.toolResult != null" class="tool-section">
                      <div class="tool-section-label">执行结果</div>
                      <pre class="tool-content">{{ formatToolJson(msg.toolResult) }}</pre>
                    </div>
                    <div v-else-if="msg.phase === 'call'" class="tool-section-hint">等待执行结果...</div>
                  </el-collapse-item>
                </el-collapse>
              </div>

              <el-collapse
                v-else-if="msg.role === 'agent_group'"
                :model-value="isGroupExpanded(msg) ? [msg._key] : []"
                class="agent-group-collapse subagent-group-collapse"
                @update:model-value="(names) => setGroupExpanded(msg, names)"
              >
                <el-collapse-item :name="msg._key">
                  <template #title>
                    <el-tag type="success" size="small" effect="plain">🤖 子智能体</el-tag>
                    <span v-if="msg.agentNs" class="agent-ns-label">{{ msg.agentNs }}</span>
                    <el-tag v-if="groupHasStreaming(msg)" type="info" size="small" style="margin-left: 8px">
                      <el-icon class="is-loading"><Loading /></el-icon>
                      输出中
                    </el-tag>
                  </template>
                  <div class="subagent-group-body">
                    <template v-for="(item, itemIdx) in msg.items" :key="`${msg._key}_${itemIdx}`">
                      <div
                        v-if="item.role === 'ai'"
                        :class="['ai-text-block', 'subagent-ai-text', { 'ai-text-streaming': item.streaming }]"
                      >
                        <MarkdownRender :content="item.content || ''" class="ai-md-stream" />
                      </div>
                      <div v-else-if="item.role === 'tool'" class="tool-card subagent-tool">
                        <el-collapse>
                          <el-collapse-item>
                            <template #title>
                              <el-tag type="success" size="small">🔧 {{ item.toolName || '工具调用' }}</el-tag>
                              <el-tag v-if="item.phase === 'call'" type="info" size="small" style="margin-left: 8px">
                                <el-icon class="is-loading"><Loading /></el-icon>
                                调用中
                              </el-tag>
                            </template>
                            <div v-if="item.toolArgs != null" class="tool-section">
                              <div class="tool-section-label">调用参数</div>
                              <pre class="tool-content">{{ formatToolJson(item.toolArgs) }}</pre>
                            </div>
                            <div v-if="item.toolResult != null" class="tool-section">
                              <div class="tool-section-label">执行结果</div>
                              <pre class="tool-content">{{ formatToolJson(item.toolResult) }}</pre>
                            </div>
                            <div v-else-if="item.phase === 'call'" class="tool-section-hint">等待执行结果...</div>
                          </el-collapse-item>
                        </el-collapse>
                      </div>
                    </template>
                  </div>
                </el-collapse-item>
              </el-collapse>

              <div v-else-if="msg.role === 'system'" class="system-message">
                <el-tag type="info" size="small">{{ msg.content }}</el-tag>
              </div>
            </div>

            <div v-if="streaming && !hasActiveStreaming" class="message-item message-ai">
              <div class="bubble assistant-bubble streaming-indicator">
                <span>正在检索与回答...</span>
              </div>
            </div>
          </div>

          <div class="input-area">
            <div class="input-toolbar">
              <el-select
                v-model="currentModelId"
                placeholder="选择模型"
                size="small"
                clearable
                style="width: 220px"
              >
                <el-option
                  v-for="item in modelOptions"
                  :key="item.modelId"
                  :label="`${item.provider}/${item.modelCode}`"
                  :value="item.modelId"
                />
              </el-select>
            </div>
            <el-input
              v-model="inputContent"
              type="textarea"
              :rows="3"
              placeholder="输入问题（Enter 换行，Alt/⌘+Enter 发送）"
              :disabled="streaming"
              @keydown="handleInputKeydown"
              resize="none"
            />
            <div class="input-actions">
              <el-button type="primary" :loading="streaming" :disabled="!inputContent.trim()" @click="handleSendMessage">
                <el-icon><Promotion /></el-icon> 发送
              </el-button>
              <el-button v-if="streaming" type="danger" @click="stopGeneration">停止生成</el-button>
            </div>
          </div>
        </template>
      </el-main>
    </el-container>

    <el-dialog v-model="renameVisible" title="重命名会话" width="400px">
      <el-form>
        <el-form-item label="会话标题">
          <el-input v-model="renameTitle" placeholder="请输入新标题" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="renameVisible = false">取消</el-button>
        <el-button type="primary" @click="handleRenameConfirm">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useEventListener } from '@vueuse/core'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ChatDotRound, Loading, Promotion } from '@element-plus/icons-vue'
import { MarkdownRender } from 'markstream-vue'
import 'markstream-vue/index.css'
import { parseTime } from '@/utils/ruoyi'
import { getToken } from '@/utils/auth'
import { useAgentSseChat } from '@/composables/useAgentSseChat'
import {
  addQaSession,
  closeQaSession,
  delQaSession,
  listQaMessages,
  listQaModels,
  listQaSession,
  renameQaSession,
} from '@/api/retrieval/qa'

const retrievalBase = import.meta.env.VITE_APP_RETRIEVAL_API || '/dev-retrieval-api'

const {
  messages,
  streaming,
  messageAreaRef,
  hasActiveStreaming,
  groupHasStreaming,
  isGroupExpanded,
  setGroupExpanded,
  formatToolJson,
  parseStoredToolRow,
  parseMessageRemark,
  setTimelineFromFlatRows,
  resetChatState,
  clearTokenQueue,
  finalizeAllStreaming,
  readSseStream,
  createAbortController,
  stopGeneration,
  appendHumanMessage,
  scrollToBottom,
} = useAgentSseChat({
  handlers: {
    business(data, { finalizeAll, messages: msgs }) {
      finalizeAll()
      msgs.value.push({
        _key: `biz_${Date.now()}`,
        role: 'business',
        searchQuery: data.searchQuery,
        hits: data.hits || [],
        error: data.error,
      })
    },
  },
})

const sessions = ref([])
const sessionLoading = ref(false)
const searchTitle = ref('')
const currentSessionId = ref(null)
const inputContent = ref('')
const modelOptions = ref([])
const currentModelId = ref(undefined)
const renameVisible = ref(false)
const renameTitle = ref('')
const renameSessionId = ref(null)

const sidebarWidth = ref(280)
let resizing = false

const filteredSessions = computed(() => {
  if (!searchTitle.value) return sessions.value
  return sessions.value.filter((s) => (s.sessionTitle || '').includes(searchTitle.value))
})

const currentSessionTitle = computed(() => {
  if (!currentSessionId.value) return ''
  const session = sessions.value.find((s) => s.sessionId === currentSessionId.value)
  return session ? session.sessionTitle || '新会话' : ''
})

function startResize(e) {
  resizing = true
  const startX = e.clientX
  const startW = sidebarWidth.value
  const onMove = (ev) => {
    if (!resizing) return
    sidebarWidth.value = Math.min(480, Math.max(200, startW + (ev.clientX - startX)))
  }
  const onUp = () => {
    resizing = false
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

useEventListener(window, 'mouseup', () => {
  resizing = false
})

onMounted(async () => {
  await Promise.all([loadSessions(), loadModels()])
})

onBeforeUnmount(() => {
  clearTokenQueue()
})

async function loadSessions() {
  sessionLoading.value = true
  try {
    const res = await listQaSession({ pageNum: 1, pageSize: 50 })
    sessions.value = res.rows || res.data || []
  } catch {
    sessions.value = []
  } finally {
    sessionLoading.value = false
  }
}

async function loadModels() {
  try {
    const res = await listQaModels()
    modelOptions.value = res.data || []
    if (modelOptions.value.length > 0 && !currentModelId.value) {
      currentModelId.value = modelOptions.value[0].modelId
    }
  } catch {
    modelOptions.value = []
  }
}

async function handleNewSession() {
  try {
    const res = await addQaSession({
      sessionTitle: '新问答会话',
      modelId: currentModelId.value,
    })
    await loadSessions()
    const newSession = res.data
    if (newSession?.sessionId) {
      await handleSelectSession(newSession.sessionId)
    }
  } catch {
    ElMessage.error('创建会话失败')
  }
}

async function handleSelectSession(sessionId) {
  if (streaming.value) {
    stopGeneration()
  }
  resetChatState()
  currentSessionId.value = sessionId
  const session = sessions.value.find((s) => s.sessionId === sessionId)
  if (session?.modelId) currentModelId.value = session.modelId
  await loadMessages(sessionId)
}

async function loadMessages(sessionId) {
  try {
    const res = await listQaMessages(sessionId, { pageNum: 1, pageSize: 200 })
    const flatRows = (res.rows || res.data || []).map((m) => {
      if (m.role === 'business') {
        let payload = {}
        try {
          payload = JSON.parse(m.content || '{}')
        } catch {
          payload = {}
        }
        return {
          role: 'business',
          searchQuery: payload.searchQuery,
          hits: payload.hits || [],
          error: payload.error,
        }
      }
      if (m.role === 'tool') {
        return parseStoredToolRow(m)
      }
      return {
        role: m.role === 'user' ? 'human' : m.role,
        content: m.content,
        ...parseMessageRemark(m.remark),
      }
    })
    setTimelineFromFlatRows(flatRows)
    await scrollToBottom()
  } catch {
    messages.value = []
  }
}

async function handleSessionCommand(command, session) {
  if (command === 'rename') {
    renameSessionId.value = session.sessionId
    renameTitle.value = session.sessionTitle || ''
    renameVisible.value = true
  } else if (command === 'close') {
    await closeQaSession(session.sessionId)
    await loadSessions()
  } else if (command === 'delete') {
    await ElMessageBox.confirm('确认删除该会话？', '提示', { type: 'warning' })
    await delQaSession(session.sessionId)
    if (currentSessionId.value === session.sessionId) {
      currentSessionId.value = null
      messages.value = []
    }
    await loadSessions()
  }
}

async function handleRenameConfirm() {
  await renameQaSession(renameSessionId.value, { sessionTitle: renameTitle.value })
  renameVisible.value = false
  await loadSessions()
}

function handleInputKeydown(e) {
  if (e.key === 'Enter' && (e.altKey || e.metaKey)) {
    e.preventDefault()
    handleSendMessage()
  }
}

async function handleSendMessage() {
  const content = inputContent.value.trim()
  if (!content || streaming.value || !currentSessionId.value) return

  appendHumanMessage(content)
  inputContent.value = ''
  streaming.value = true
  await scrollToBottom()

  const controller = createAbortController()

  try {
    const response = await fetch(`${retrievalBase}/qa/chat/${currentSessionId.value}/message`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer ' + getToken(),
      },
      body: JSON.stringify({ content, modelId: currentModelId.value }),
      signal: controller.signal,
    })
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    await readSseStream(response)
  } catch (e) {
    if (e.name !== 'AbortError') {
      console.error('[SSE] Stream connection error:', e)
      ElMessage.error('连接失败，请检查 knowledge-retrieval 服务')
    }
  } finally {
    finalizeAllStreaming()
    streaming.value = false
    await scrollToBottom()
  }
}
</script>

<style scoped>
.qa-container {
  height: calc(100vh - 84px);
  padding: 0;
  display: flex;
  flex-direction: column;
}
.qa-container > .el-container {
  flex: 1;
  overflow: hidden;
}

.session-sidebar { display: flex; flex-direction: column; background: #fafafa; }
.sidebar-header { padding: 16px; }
.new-chat-btn { width: 100%; }
.session-search { padding: 0 12px 8px; }
.session-list { flex: 1; overflow-y: auto; padding: 0 8px; }
.session-item { display: flex; align-items: center; padding: 10px 8px; border-radius: 8px; cursor: pointer; margin-bottom: 4px; transition: background 0.2s; }
.session-item:hover { background: #e8f4fd; }
.session-item.active { background: #d9ecff; }
.session-icon { margin-right: 10px; font-size: 18px; color: #409eff; }
.session-info { flex: 1; overflow: hidden; }
.session-title { font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.session-meta { display: flex; align-items: center; gap: 6px; margin-top: 4px; font-size: 12px; color: #909399; }
.more-btn { padding: 2px; }
.empty-session { text-align: center; color: #909399; padding: 40px 0; }

.resize-handle {
  width: 4px;
  cursor: col-resize;
  background: transparent;
  flex-shrink: 0;
}
.resize-handle:hover { background: #d0d5dd; }

.chat-main { display: flex; flex-direction: column; padding: 0; }
.chat-header { display: flex; align-items: center; gap: 8px; padding: 10px 16px; border-bottom: 1px solid #e4e7ed; background: #fff; flex-shrink: 0; }
.chat-header-title { font-size: 14px; font-weight: 600; color: #303133; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.message-area { flex: 1; overflow-y: auto; padding: 16px; background: #f0f2f5; }
.message-item { margin-bottom: 16px; }
.message-human { display: flex; justify-content: flex-end; }
.message-ai { display: flex; justify-content: flex-start; }
.message-system { display: flex; justify-content: center; }
.message-business { display: flex; justify-content: flex-start; }
.bubble { max-width: 70%; padding: 12px 16px; border-radius: 12px; line-height: 1.6; font-size: 14px; }
.user-bubble { background: #409eff; color: #fff; border-bottom-right-radius: 4px; }
.assistant-bubble { background: #e5e7eb; color: #303133; border-bottom-left-radius: 4px; }
.assistant-bubble.ai-text-streaming { border-left: 3px solid #409eff; }
.ai-md-stream {
  font-size: 14px;
  line-height: 1.6;
  overflow-wrap: break-word;
  word-break: break-word;
}
.ai-md-stream :deep(p) { margin: 0 0 0.6em; }
.ai-md-stream :deep(p:last-child) { margin-bottom: 0; }
.ai-md-stream :deep(pre) {
  margin: 0.5em 0;
  padding: 8px 10px;
  border-radius: 6px;
  background: #f5f7fa;
  overflow: auto;
  font-size: 12px;
}
.ai-md-stream :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.92em;
}
.system-message { margin: 8px 0; background: #fef3c7; border-radius: 4px; padding: 4px 12px; }
.tool-card { max-width: 70%; margin-bottom: 8px; background: #fafafa; border: 1px solid #d0d5dd; border-radius: 8px; overflow: hidden; }

.agent-group-collapse { max-width: 70%; margin-bottom: 8px; border-radius: 8px; overflow: hidden; }
.subagent-group-collapse { border: 2px solid #67c23a; background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%); }
.subagent-group-collapse :deep(.el-collapse-item__header) { background: transparent; border-bottom: 1px dashed #d0d5dd; padding: 10px 12px; height: auto; line-height: 1.5; }
.subagent-group-collapse :deep(.el-collapse-item__wrap) { background: transparent; border: none; }
.subagent-group-collapse :deep(.el-collapse-item__content) { padding: 12px; }
.subagent-group-body { position: relative; }
.subagent-group-body::before { content: ''; position: absolute; left: -16px; top: 0; bottom: 0; width: 4px; background: #67c23a; border-radius: 4px 0 0 4px; }
.agent-ns-label { margin-left: 8px; font-size: 12px; color: #909399; font-family: monospace; background: #f5f7fa; padding: 2px 6px; border-radius: 4px; }
.ai-text-block { margin-bottom: 10px; font-size: 14px; line-height: 1.6; }
.ai-text-block:last-child { margin-bottom: 0; }
.ai-text-block.ai-text-streaming { border-left: 3px solid #409eff; padding-left: 10px; }
.subagent-group-body .ai-text-block.ai-text-streaming { border-left-color: #67c23a; }
.subagent-tool { border-color: #67c23a; background: linear-gradient(135deg, #fafafa 0%, #f0f9ff 100%); }
.tool-section { margin-bottom: 8px; }
.tool-section:last-child { margin-bottom: 0; }
.tool-section-label { font-size: 12px; font-weight: 600; color: #606266; margin-bottom: 4px; }
.tool-section-hint { font-size: 12px; color: #909399; font-style: italic; padding: 4px 0; }
.tool-content { font-size: 12px; max-height: 300px; overflow: auto; background: #f5f7fa; padding: 8px; border-radius: 4px; white-space: pre-wrap; word-break: break-all; }

.citations-card {
  max-width: 85%;
  padding: 0 12px;
  border-radius: 8px;
  background: #ecf5ff;
  border: 1px solid #d9ecff;
  font-size: 13px;
}
.citations-card :deep(.el-collapse) { border: none; background: transparent; }
.citations-card :deep(.el-collapse-item__header) {
  background: transparent;
  border: none;
  height: auto;
  line-height: 1.5;
  padding: 10px 0;
}
.citations-card :deep(.el-collapse-item__wrap) { background: transparent; border: none; }
.citations-card :deep(.el-collapse-item__content) { padding: 0 0 10px; display: grid; gap: 6px; }
.citations-title { font-weight: 600; }
.citation-item { border-top: 1px dashed var(--el-border-color); padding-top: 6px; }
.citation-meta { color: #909399; font-size: 12px; }
.citation-text { white-space: pre-wrap; }
.muted { color: #909399; }

.streaming-indicator { animation: pulse 1.5s ease-in-out infinite; }
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.55; }
}

.input-area { padding: 12px 16px; border-top: 1px solid #d0d5dd; background: #fff; box-shadow: 0 -2px 8px rgba(0,0,0,0.04); }
.input-toolbar { display: flex; align-items: center; margin-bottom: 8px; }
.input-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }

.welcome-screen { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: #909399; opacity: 0.8; }
.welcome-icon { background: #f5f7fa; border-radius: 50%; padding: 20px; margin-bottom: 20px; color: #409eff; }
.welcome-screen h2 { margin-bottom: 10px; font-weight: 500; font-size: 18px; color: #606266; }
.welcome-screen p { font-size: 14px; }
</style>
