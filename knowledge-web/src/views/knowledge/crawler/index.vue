<template>
  <div class="app-container crawler-container">
    <!-- 页面级 Tab：爬取会话 / 任务详情 / 文档信息 -->
    <el-tabs v-model="pageTab" class="page-tabs" @tab-change="handlePageTabChange">

      <!-- =============== Tab1: 爬取会话 =============== -->
      <el-tab-pane label="爬取会话" name="session">
        <el-container style="height: 100%">
          <!-- 左侧：会话列表 -->
          <el-aside :width="sidebarWidth + 'px'" class="session-sidebar">
            <div class="sidebar-header">
              <el-button type="primary" class="new-chat-btn" icon="Plus" @click="handleNewSession">
                新建爬取会话
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
                  <el-icon><Link /></el-icon>
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

          <!-- 拖拽调整宽度的手柄 -->
          <div class="resize-handle" @mousedown="startResize"></div>

          <!-- 右侧：聊天区域（仅聊天，无任务/文档子 tab） -->
          <el-main class="chat-main">
            <div v-if="!currentSessionId" class="welcome-screen">
              <div class="welcome-icon">
                <el-icon :size="60"><Link /></el-icon>
              </div>
              <h2>我是您的网页爬取配置助手</h2>
              <p>选择或创建一个会话，开始网页爬取</p>
            </div>

            <template v-else>
              <!-- 聊天区域标题 -->
              <div class="chat-header">
                <el-icon><Link /></el-icon>
                <span class="chat-header-title">{{ currentSessionTitle }}</span>
                <el-tag type="info" size="small" effect="plain">ID: {{ currentSessionId }}</el-tag>
              </div>
              <div class="message-area" ref="messageAreaRef">
                <div v-for="(msg, idx) in messages" :key="msg._key || idx" :class="['message-item', 'message-' + (msg.role === 'agent_group' || (msg.role === 'ai' && !msg.type) ? 'ai' : msg.role), { 'ai-typing': streaming && idx === messages.length - 1 && ((msg.role === 'agent_group' && groupHasStreaming(msg)) || (msg.role === 'ai' && msg.streaming && !msg.type)) }]">
                  <!-- 第一优先：特殊卡片（按 type，避免被 role 分支误捕获） -->
                  <StrategyConfirmCard
                    v-if="msg.type === 'strategy'"
                    :config="msg.strategyConfig"
                    :sessionId="currentSessionId"
                    @confirm="handleStrategyConfirm"
                    @regenerate="handleRegenerate"
                  />
                  <!-- URL 路由审批卡片（用户确认是否切换分析目标） -->
                  <div v-else-if="msg.type === 'user_choice'" class="bubble assistant-bubble user-choice-card">
                    <div class="choice-title">{{ (msg.choiceData && msg.choiceData.title) || '确认操作' }}</div>
                    <div class="choice-desc" v-html="formatChoiceDesc(msg.choiceData)"></div>
                    <div class="choice-urls" v-if="msg.choiceData && msg.choiceData.current_url">
                      <div class="url-row">
                        <el-tag size="small" type="info" style="margin-right:4px">当前</el-tag>
                        <span class="url-text">{{ msg.choiceData.current_url }}</span>
                      </div>
                      <div class="url-row">
                        <el-tag size="small" type="warning" style="margin-right:4px">新网址</el-tag>
                        <span class="url-text">{{ msg.choiceData.new_url }}</span>
                      </div>
                    </div>
                    <div v-if="msg.choiceData && msg.choiceData.cached_analysis" class="choice-cache">
                      <el-tag size="small" type="success">历史缓存</el-tag>
                      <pre class="cache-preview">{{ msg.choiceData.cached_analysis }}</pre>
                    </div>
                    <div class="choice-buttons" v-if="isChoiceInterrupt(msg.choiceData)">
                      <el-button
                        v-for="choice in (msg.choiceData && msg.choiceData.choices || [])"
                        :key="choice.value"
                        type="primary"
                        size="small"
                        plain
                        @click="handleUserChoice(choice.value, choice.label, msg.choiceData)"
                      >
                        {{ choice.label }}
                      </el-button>
                    </div>
                    <div v-else-if="isTextInterrupt(msg.choiceData)" class="choice-text-input">
                      <el-input
                        v-model="msg.choiceTextInput"
                        type="textarea"
                        :rows="3"
                        :placeholder="(msg.choiceData && msg.choiceData.placeholder) || '请输入账号、Cookie/Token、爬取范围等'"
                        :disabled="streaming"
                      />
                      <el-button
                        type="primary"
                        size="small"
                        style="margin-top: 8px"
                        :disabled="streaming || !(msg.choiceTextInput || '').trim()"
                        @click="handleUserChoiceText(msg.choiceTextInput, msg.choiceData)"
                      >
                        提交
                      </el-button>
                    </div>
                  </div>
                  <!-- 任务进度卡片 -->
                  <TaskProgressCard
                    v-else-if="msg.type === 'task_progress'"
                    :task="msg.taskData"
                    :status-options="taskStatusOptions"
                    @retry="handleTaskRetry"
                    @view-detail="handleViewDetail"
                    @delete-task="handleTaskDelete"
                    @pause-task="handleTaskPause"
                    @resume-task="handleTaskResume"
                    @merge="handleTaskMerge"
                  />
                  <!-- 用户消息 -->
                  <div v-else-if="msg.role === 'human'" class="bubble user-bubble">
                    <span>{{ msg.content }}</span>
                  </div>
                  <!-- 父图：每条 AI 回复独立气泡 -->
                  <div
                    v-else-if="msg.role === 'ai' && !msg.type"
                    class="bubble assistant-bubble"
                    :class="{ 'ai-text-streaming': msg.streaming }"
                  >
                    <MarkdownRender :content="msg.content || ''" class="ai-md-stream" />
                  </div>
                  <!-- 父图：每条工具调用独立卡片 -->
                  <div v-else-if="msg.role === 'tool'" class="tool-card">
                    <el-collapse>
                      <el-collapse-item>
                        <template #title>
                          <el-tag type="warning" size="small">
                            🔧 {{ msg.toolName || '工具调用' }}
                          </el-tag>
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
                  <!-- 子图：agent_group 折叠分组 -->
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
                                  <el-tag type="success" size="small">
                                    🔧 {{ item.toolName || '工具调用' }}
                                  </el-tag>
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
                <div
                  v-if="streaming && !hasActiveStreaming"
                  class="message-item message-ai"
                >
                  <div class="bubble assistant-bubble streaming-indicator">
                    <span>正在分析...</span>
                  </div>
                </div>
              </div>

              <!-- 输入区 -->
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
                  placeholder="输入目标 URL 或描述（Enter 换行，Alt/⌘+Enter 发送）"
                  :disabled="streaming"
                  @keydown="handleInputKeydown"
                  resize="none"
                />
                <div class="input-actions">
                  <el-button type="primary" :loading="streaming" :disabled="!inputContent.trim()" @click="handleSendMessage()">
                    <el-icon><Promotion /></el-icon> 发送
                  </el-button>
                  <el-button v-if="streaming" type="danger" @click="handleStopGeneration">停止生成</el-button>
                </div>
              </div>
            </template>
          </el-main>
        </el-container>
      </el-tab-pane>

      <!-- =============== Tab2: 任务详情 =============== -->
      <el-tab-pane label="任务详情" name="task">
        <div class="task-page" v-loading="allTaskLoading">
          <div class="task-header">
            <el-space wrap>
              <el-select v-model="taskFilterStatus" placeholder="任务状态" clearable size="small" style="width: 140px">
                <el-option label="全部" value="" />
                <el-option v-for="opt in taskStatusOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
              <el-select v-model="taskFilterErrorCode" placeholder="错误码" clearable size="small" style="width: 160px">
                <el-option label="全部" value="" />
                <el-option v-for="opt in taskErrorCodeOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
              <el-input
                v-model="taskFilterCreateBy"
                placeholder="操作用户"
                clearable
                size="small"
                style="width: 150px"
                @keyup.enter="loadAllTasks"
              />
              <el-button type="primary" size="small" @click="loadAllTasks">查询</el-button>
              <el-button size="small" @click="resetTaskFilters">重置</el-button>
            </el-space>
          </div>
          <div class="task-list-area">
            <div v-for="task in filteredAllTasks" :key="task.taskId" class="task-item">
              <TaskProgressCard :task="task" :status-options="taskStatusOptions" @retry="handleTaskRetry" @view-detail="handleViewDetail" @delete-task="handleTaskDelete" @pause-task="handleTaskPause" @resume-task="handleTaskResume" @merge="handleTaskMerge" />
            </div>
            <el-empty v-if="filteredAllTasks.length === 0 && !allTaskLoading" description="暂无爬取任务" />
          </div>
        </div>
      </el-tab-pane>

      <!-- =============== Tab3: 文档信息 =============== -->
      <el-tab-pane label="文档信息" name="document">
        <div class="document-page" v-loading="allDocLoading">
          <div class="doc-header">
            <el-space wrap>
              <el-input
                v-model="docFilterTitle"
                placeholder="标题"
                clearable
                size="small"
                style="width: 180px"
                @keyup.enter="loadAllDocs"
              />
              <el-select v-model="docFilterStatus" placeholder="文档状态" clearable size="small" style="width: 140px">
                <el-option label="全部" value="" />
                <el-option v-for="opt in docStatusOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
              <el-input
                v-model="docFilterCreateBy"
                placeholder="操作用户"
                clearable
                size="small"
                style="width: 150px"
                @keyup.enter="loadAllDocs"
              />
              <el-select v-model="docFilterDelFlag" placeholder="删除标识" clearable size="small" style="width: 140px">
                <el-option label="全部" value="" />
                <el-option label="正常" value="0" />
                <el-option label="已删除" value="2" />
              </el-select>
              <el-button type="primary" size="small" @click="loadAllDocs">查询</el-button>
              <el-button size="small" @click="resetDocFilters">重置</el-button>
            </el-space>
          </div>
          <div class="document-list-area">
            <el-table :data="filteredAllDocs" stripe>
              <el-table-column prop="docTitle" label="标题" min-width="150" show-overflow-tooltip />
              <el-table-column prop="docDesc" label="描述" min-width="200" show-overflow-tooltip />
              <el-table-column prop="fileCount" label="文件数" width="80" align="center" />
              <el-table-column prop="taskId" label="关联任务" width="100" align="center" />
              <el-table-column prop="docType" label="类型" width="70" />
              <el-table-column prop="docVersion" label="版本" width="70" />
              <el-table-column prop="status" label="文档状态" width="120" align="center">
                <template #default="{ row }">
                  <el-tag :type="docStatusType(row.status)" size="small">{{ docStatusLabel(row.status) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="createBy" label="操作用户" width="120" />
              <el-table-column prop="delFlag" label="删除标识" width="100" align="center">
                <template #default="{ row }">
                  <el-tag v-if="row.delFlag === '2'" type="danger" size="small">已删除</el-tag>
                  <el-tag v-else type="success" size="small">正常</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="createTime" label="创建时间" width="170">
                <template #default="{ row }">{{ parseTime(row.createTime) }}</template>
              </el-table-column>
              <el-table-column label="操作" width="140" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" @click="handlePreviewDoc(row.docId)">预览</el-button>
                  <el-button link type="primary" @click="handleDownloadDoc(row.docId)">下载</el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-if="filteredAllDocs.length === 0 && !allDocLoading" description="暂无文档" />
          </div>
        </div>
      </el-tab-pane>

    </el-tabs>

    <!-- 重命名对话框 -->
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

    <!-- 文档预览对话框 -->
    <el-dialog v-model="previewVisible" title="文档预览" width="70%" top="5vh">
      <div class="doc-preview" v-html="previewContent"></div>
    </el-dialog>

    <!-- 爬取文档选页（预览/下载） -->
    <el-dialog v-model="filePickVisible" :title="filePickMode === 'preview' ? '选择预览页面' : '选择下载页面'" width="640px">
      <el-table
        ref="filePickTableRef"
        :data="filePickList"
        @selection-change="onFilePickSelection"
        max-height="360"
      >
        <el-table-column v-if="filePickMode === 'download'" type="selection" width="48" />
        <el-table-column v-else width="48">
          <template #default="{ row }">
            <el-radio v-model="filePickSingleId" :label="row.id">&nbsp;</el-radio>
          </template>
        </el-table-column>
        <el-table-column prop="docName" label="文件名" min-width="140" show-overflow-tooltip />
        <el-table-column prop="sourceUrl" label="来源URL" min-width="220" show-overflow-tooltip />
        <el-table-column prop="docType" label="类型" width="70" />
      </el-table>
      <template #footer>
        <el-button v-if="filePickMode === 'download'" @click="confirmFilePickDownload(true)">全量下载 ZIP</el-button>
        <el-button @click="filePickVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmFilePick">确定</el-button>
      </template>
    </el-dialog>

    <!-- 任务详情对话框 -->
    <el-dialog v-model="taskDetailVisible" title="任务详情" width="1100px" append-to-body>
      <el-tabs v-model="detailTab" @tab-change="handleDetailTabChange">
        <el-tab-pane label="任务信息" name="info">
          <template v-if="taskDetail">
            <el-descriptions :column="2" border>
              <el-descriptions-item label="任务ID" :span="2">{{ taskDetail.taskId }}</el-descriptions-item>
              <el-descriptions-item label="目标URL" :span="2">
                <el-link :href="taskDetail.targetUrl" target="_blank" type="primary">{{ taskDetail.targetUrl }}</el-link>
              </el-descriptions-item>
              <el-descriptions-item label="任务状态">
                <el-tag :type="detailStatusType" size="small">{{ detailStatusLabel }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="进度">{{ taskDetail.progress }}%</el-descriptions-item>
              <el-descriptions-item label="当前步骤" :span="2">{{ taskDetail.currentStep || '-' }}</el-descriptions-item>
              <el-descriptions-item label="操作用户" :span="2">{{ taskDetail.createBy || '-' }}</el-descriptions-item>
              <el-descriptions-item label="成功页面">{{ taskDetail.successCount || 0 }}</el-descriptions-item>
              <el-descriptions-item label="失败页面">{{ taskDetail.failedCount || 0 }}</el-descriptions-item>
              <el-descriptions-item label="总页面">{{ taskDetail.totalCount || 0 }}</el-descriptions-item>
              <el-descriptions-item label="已重试次数">{{ taskDetail.retryCount || 0 }}</el-descriptions-item>
              <el-descriptions-item label="错误码">
                <el-tag v-if="taskDetail.errorCode" type="danger" size="small">{{ taskDetail.errorCode }}</el-tag>
                <span v-else>-</span>
              </el-descriptions-item>
              <el-descriptions-item label="错误信息" :span="2">
                <el-tag v-if="taskDetail.errorMessage" type="danger">{{ taskDetail.errorMessage }}</el-tag>
                <span v-else>-</span>
              </el-descriptions-item>
              <el-descriptions-item label="开始时间">{{ parseTime(taskDetail.startedTime) }}</el-descriptions-item>
              <el-descriptions-item label="完成时间">{{ parseTime(taskDetail.completedTime) }}</el-descriptions-item>
              <el-descriptions-item label="创建时间">{{ parseTime(taskDetail.createTime) }}</el-descriptions-item>
              <el-descriptions-item label="更新时间">{{ parseTime(taskDetail.updateTime) }}</el-descriptions-item>
            </el-descriptions>
          </template>
        </el-tab-pane>
        <el-tab-pane label="URL记录" name="urls">
          <div class="url-filter-row">
            <el-select v-model="urlStatusFilter" placeholder="状态过滤" clearable size="small" style="width:140px" @change="loadUrlRecords">
              <el-option label="全部" value="" />
              <el-option label="成功" value="SUCCESS" />
              <el-option label="失败" value="FAILED" />
            </el-select>
          </div>
          <el-table :data="urlRecordList" v-loading="urlRecordLoading" stripe max-height="480" style="min-height: 240px">
            <el-table-column prop="url" label="URL" min-width="360" show-overflow-tooltip />
            <el-table-column prop="title" label="页面标题" min-width="160" show-overflow-tooltip />
            <el-table-column prop="status" label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="row.status === 'SUCCESS' ? 'success' : row.status === 'FAILED' ? 'danger' : 'info'" size="small">
                  {{ row.status === 'SUCCESS' ? '成功' : row.status === 'FAILED' ? '失败' : '待处理' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="statusCode" label="HTTP状态码" width="110" />
            <el-table-column prop="errorCode" label="错误码" width="120" />
            <el-table-column prop="errorMessage" label="错误详情" min-width="180" show-overflow-tooltip />
            <el-table-column prop="retryCount" label="重试" width="60" align="center" />
          </el-table>
          <el-empty v-if="!urlRecordLoading && urlRecordList.length === 0" description="暂无URL记录" />
          <div class="url-pagination" v-if="urlRecordTotal > 0">
            <el-pagination
              v-model:current-page="urlRecordPageNum"
              v-model:page-size="urlRecordPageSize"
              :total="urlRecordTotal"
              layout="prev, pager, next, total"
              small
              @current-change="loadUrlRecords"
            />
          </div>
        </el-tab-pane>
        <el-tab-pane label="配置信息" name="config">
          <div class="config-content" v-if="taskDetail && taskDetail.crawlConfig">
            <pre class="config-json">{{ formattedConfig }}</pre>
          </div>
          <el-empty v-else description="暂无配置信息" />
        </el-tab-pane>
      </el-tabs>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, watch, onMounted, onBeforeUnmount } from 'vue';
import { useEventListener } from '@vueuse/core';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Link, Promotion, Loading } from '@element-plus/icons-vue';
import { parseTime } from '@/utils/ruoyi';
import { getToken } from '@/utils/auth';
import {
  listCrawlerSession, listAllCrawlerSession, addCrawlerSession, renameCrawlerSession,
  closeCrawlerSession, delCrawlerSession,
  listCrawlerMessages, confirmCrawlerStrategy,
  listCrawlTask, getCrawlTask, delCrawlTask, pauseCrawlTask, resumeCrawlTask, mergeCrawlResults,
  listCrawlerDocument,
  listCrawlUrlRecords, listCrawlerModels,
  getTaskStatusOptions, getTaskErrorCodeOptions,
} from '@/api/content/crawler';
import { previewDocument, downloadDocument, listDocumentFiles } from '@/api/content/document';
import { MarkdownRender } from 'markstream-vue';
import 'markstream-vue/index.css';
import StrategyConfirmCard from './components/StrategyConfirmCard.vue';
import TaskProgressCard from './components/TaskProgressCard.vue';

const contentBase = import.meta.env.VITE_APP_CONTENT_API || '/dev-content-api';

// ==================== 会话管理 ====================
const sessionList = ref([]);
const sessionLoading = ref(false);
const currentSessionId = ref(null);
const searchTitle = ref('');

// 数据权限范围的会话列表（用于任务/文档筛选下拉）
const allSessionList = ref([]);

const filteredSessions = computed(() => {
  if (!searchTitle.value) return sessionList.value;
  return sessionList.value.filter(s => (s.sessionTitle || '').includes(searchTitle.value));
});

// 当前选中的会话标题
const currentSessionTitle = computed(() => {
  if (!currentSessionId.value) return '';
  const session = sessionList.value.find(s => s.sessionId === currentSessionId.value);
  return session ? (session.sessionTitle || '新会话') : '';
});

async function loadSessions() {
  sessionLoading.value = true;
  try {
    const res = await listCrawlerSession({ pageNum: 1, pageSize: 50 });
    sessionList.value = res.rows || res.data || [];
  } finally {
    sessionLoading.value = false;
  }
}

async function handleNewSession() {
  try {
    const res = await addCrawlerSession({});
    await loadSessions();
    const newSession = res.data;
    if (newSession?.sessionId) {
      await handleSelectSession(newSession.sessionId);
    }
  } catch (e) {
    ElMessage.error('创建会话失败');
  }
}

async function handleSelectSession(sessionId) {
  _resetChatState();
  messages.value = [];
  currentSessionId.value = sessionId;
  await loadMessages(sessionId);
  await loadTasks(sessionId);
}

function handleSessionCommand(command, session) {
  if (command === 'rename') {
    renameTitle.value = session.sessionTitle || '';
    renameSessionId.value = session.sessionId;
    renameVisible.value = true;
  } else if (command === 'close') {
    handleCloseOperation(session.sessionId);
  } else if (command === 'delete') {
    handleDeleteSession(session.sessionId);
  }
}

async function loadAllSessions() {
  try {
    const res = await listAllCrawlerSession({ pageNum: 1, pageSize: 200 });
    allSessionList.value = res.rows || res.data || [];
  } catch (e) {
    allSessionList.value = [];
  }
}

const renameVisible = ref(false);
const renameTitle = ref('');
const renameSessionId = ref(null);

async function handleRenameConfirm() {
  if (!renameTitle.value.trim()) return;
  await renameCrawlerSession(renameSessionId.value, { sessionTitle: renameTitle.value });
  renameVisible.value = false;
  await loadSessions();
}

async function handleCloseOperation(sessionId) {
  await closeCrawlerSession(sessionId);
  await loadSessions();
}

async function handleDeleteSession(sessionId) {
  await ElMessageBox.confirm('确定删除该会话？关联的消息和任务记录将一并删除。', '确认删除', { type: 'warning' });
  await delCrawlerSession(sessionId);
  if (currentSessionId.value === sessionId) {
    currentSessionId.value = null;
    _resetChatState();
    messages.value = [];
  }
  await loadSessions();
}

// ==================== 消息管理（统一时间线） ====================
const messages = ref([]);
const inputContent = ref('');
const streaming = ref(false);
const expandedGroupKeys = ref([]);
const messageAreaRef = ref(null);
const modelOptions = ref([]);
const currentModelId = ref(undefined);
let abortController = null;

const hasActiveStreaming = computed(() =>
  messages.value.some((m) =>
    (m.role === 'agent_group' && groupHasStreaming(m))
    || (m.role === 'ai' && m.streaming && !m.type),
  ),
);

function groupHasStreaming(groupMsg) {
  return (groupMsg.items || []).some((item) => item.role === 'ai' && item.streaming);
}

function isGroupExpanded(groupMsg) {
  return expandedGroupKeys.value.includes(groupMsg._key);
}

function setGroupExpanded(groupMsg, names) {
  const shouldExpand = names.includes(groupMsg._key);
  const idx = expandedGroupKeys.value.indexOf(groupMsg._key);
  if (shouldExpand && idx === -1) {
    expandedGroupKeys.value.push(groupMsg._key);
  } else if (!shouldExpand && idx !== -1) {
    expandedGroupKeys.value.splice(idx, 1);
  }
}

function _agentCtxKey(source, agentNs) {
  return source === 'subagent' && agentNs ? `subagent:${agentNs}` : 'supervisor';
}

function _isSubagentSource(source) {
  return source === 'subagent';
}

function _finalizeSupervisorStreaming() {
  const last = messages.value[messages.value.length - 1];
  if (last?.role !== 'ai' || last.type || !last.streaming) return;
  last.streaming = false;
  last.content = (last.content || '').trimEnd();
  if (!last.content.trim()) {
    messages.value.pop();
  }
}

function _finalizeGroupStreaming(group) {
  if (!group?.items?.length) return;
  const lastAi = [...group.items].reverse().find((item) => item.role === 'ai' && item.streaming);
  if (!lastAi) return;
  lastAi.streaming = false;
  lastAi.content = (lastAi.content || '').trimEnd();
  if (!lastAi.content.trim()) {
    const idx = group.items.indexOf(lastAi);
    if (idx >= 0) group.items.splice(idx, 1);
  }
}

function _finalizeAllStreaming() {
  _flushTokenQueue();
  messages.value.forEach((msg) => {
    if (msg.role === 'agent_group') {
      _finalizeGroupStreaming(msg);
    } else if (msg.role === 'ai' && msg.streaming && !msg.type) {
      msg.streaming = false;
      msg.content = (msg.content || '').trimEnd();
    }
  });
  messages.value = messages.value.filter((msg) => !(msg.role === 'ai' && !msg.type && !(msg.content || '').trim()));
}

function _getOrCreateSubagentGroup(agentNs) {
  const ctxKey = _agentCtxKey('subagent', agentNs);
  const last = messages.value[messages.value.length - 1];
  if (last?.role === 'agent_group' && last._ctxKey === ctxKey) {
    return last;
  }
  if (last?.role === 'agent_group') {
    _finalizeGroupStreaming(last);
  }
  const group = {
    _key: `grp_${ctxKey}_${Date.now()}`,
    _ctxKey: ctxKey,
    role: 'agent_group',
    source: 'subagent',
    agentNs: agentNs || undefined,
    items: [],
  };
  messages.value.push(group);
  if (!expandedGroupKeys.value.includes(group._key)) {
    expandedGroupKeys.value.push(group._key);
  }
  return group;
}

/** SSE token 缓冲：收包与绘制解耦，按帧匀速吐字 */
const _tokenQueue = [];
let _tokenDrainRaf = null;
let _lastStreamScrollAt = 0;
let _isFlushingTokens = false;

function _pendingTokenChars() {
  return _tokenQueue.reduce((sum, item) => sum + item.content.length, 0);
}

function _charsPerFrame() {
  const pending = _pendingTokenChars();
  if (pending > 800) return Math.min(pending, 240);
  if (pending > 300) return 96;
  if (pending > 100) return 48;
  return 28;
}

function _maybeScrollDuringStream() {
  const now = performance.now();
  if (now - _lastStreamScrollAt < 80) return;
  _lastStreamScrollAt = now;
  if (messageAreaRef.value) {
    messageAreaRef.value.scrollTop = messageAreaRef.value.scrollHeight;
  }
}

function _commitToken(source, agentNs, content) {
  const chunk = content || '';
  if (!chunk) return;
  if (!_isSubagentSource(source)) {
    const last = messages.value[messages.value.length - 1];
    if (last?.role === 'ai' && !last.type && last.streaming) {
      last.content += chunk;
      return;
    }
    messages.value.push({
      _key: `ai_${Date.now()}`,
      role: 'ai',
      content: chunk,
      streaming: true,
    });
    return;
  }
  const group = _getOrCreateSubagentGroup(agentNs);
  const lastItem = group.items[group.items.length - 1];
  if (lastItem?.role === 'ai' && lastItem.streaming) {
    lastItem.content += chunk;
    return;
  }
  group.items.push({ role: 'ai', content: chunk, streaming: true });
}

function _drainTokenQueue() {
  _tokenDrainRaf = null;
  let budget = _charsPerFrame();
  while (budget > 0 && _tokenQueue.length) {
    const item = _tokenQueue[0];
    if (item.content.length <= budget) {
      budget -= item.content.length;
      _commitToken(item.source, item.agentNs, item.content);
      _tokenQueue.shift();
    } else {
      const take = item.content.slice(0, budget);
      item.content = item.content.slice(budget);
      _commitToken(item.source, item.agentNs, take);
      budget = 0;
    }
  }
  _maybeScrollDuringStream();
  if (_tokenQueue.length) {
    _tokenDrainRaf = requestAnimationFrame(_drainTokenQueue);
  }
}

function _ensureTokenDrain() {
  if (_tokenDrainRaf == null) {
    _tokenDrainRaf = requestAnimationFrame(_drainTokenQueue);
  }
}

function _flushTokenQueue() {
  if (_tokenDrainRaf != null) {
    cancelAnimationFrame(_tokenDrainRaf);
    _tokenDrainRaf = null;
  }
  if (_isFlushingTokens) return;
  _isFlushingTokens = true;
  try {
    while (_tokenQueue.length) {
      const item = _tokenQueue.shift();
      _commitToken(item.source, item.agentNs, item.content);
    }
  } finally {
    _isFlushingTokens = false;
  }
}

function _clearTokenQueue() {
  if (_tokenDrainRaf != null) {
    cancelAnimationFrame(_tokenDrainRaf);
    _tokenDrainRaf = null;
  }
  _tokenQueue.length = 0;
}

function _appendToken(source, agentNs, content) {
  const chunk = content || '';
  if (!chunk) return;
  _tokenQueue.push({ source, agentNs, content: chunk });
  _ensureTokenDrain();
}

function formatToolJson(value) {
  if (value == null) return '';
  if (typeof value === 'string') {
    try {
      return JSON.stringify(JSON.parse(value), null, 2);
    } catch {
      return value;
    }
  }
  return JSON.stringify(value, null, 2);
}

function _mergeToolCallItem(existing, incoming) {
  const phase = incoming.phase || (incoming.toolResult != null ? 'result' : 'call');
  return {
    ...existing,
    role: 'tool',
    toolName: incoming.toolName || existing.toolName,
    toolCallId: incoming.toolCallId || existing.toolCallId,
    phase,
    toolArgs: incoming.toolArgs != null ? incoming.toolArgs : existing.toolArgs,
    toolResult: incoming.toolResult != null ? incoming.toolResult : existing.toolResult,
  };
}

function _buildToolCallItem(data) {
  const phase = data.phase || (data.content !== undefined ? 'result' : 'call');
  return {
    role: 'tool',
    toolName: data.tool_name,
    toolCallId: data.tool_call_id || '',
    phase,
    toolArgs: data.tool_args,
    toolResult: phase === 'result' ? data.content : undefined,
  };
}

function _parseStoredToolRow(m) {
  if (m.role !== 'tool') return m;
  let toolArgs;
  let toolResult;
  let toolName = m.toolName;
  if (m.content) {
    try {
      const parsed = JSON.parse(m.content);
      if (parsed && typeof parsed === 'object') {
        if (parsed.tool_args != null) toolArgs = parsed.tool_args;
        if (parsed.result != null) toolResult = parsed.result;
        if (!toolName && parsed.tool_name) toolName = parsed.tool_name;
      }
    } catch { /* 非 JSON 内容保持原样 */ }
  }
  return {
    role: m.role,
    toolName,
    toolCallId: m.toolCallId,
    phase: toolResult != null ? 'result' : 'call',
    toolArgs,
    toolResult,
    ..._parseMessageRemark(m.remark),
  };
}

function _upsertToolCall(data, source = 'supervisor', agentNs = null) {
  _flushTokenQueue();
  const tcId = data.tool_call_id || '';
  const incoming = _buildToolCallItem(data);

  if (!_isSubagentSource(source)) {
    _finalizeSupervisorStreaming();
    if (tcId) {
      const existing = messages.value.find((item) => item.role === 'tool' && item.toolCallId === tcId);
      if (existing) {
        Object.assign(existing, _mergeToolCallItem(existing, incoming));
        return;
      }
    }
    messages.value.push({ ...incoming, _key: `tool_${tcId || Date.now()}` });
    return;
  }

  const group = _getOrCreateSubagentGroup(agentNs);
  _finalizeGroupStreaming(group);

  if (tcId) {
    const existing = group.items.find((item) => item.role === 'tool' && item.toolCallId === tcId);
    if (existing) {
      Object.assign(existing, _mergeToolCallItem(existing, incoming));
      return;
    }
  }
  group.items.push(incoming);
}

function _isAgentFlatRow(row) {
  if (row.type) return false;
  return row.role === 'ai' || row.role === 'tool';
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
    };
  }
  return { role: 'ai', content: row.content || '', streaming: false };
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
    };
  }
  return { role: 'ai', content: row.content || '', streaming: false };
}

function _rowsToTimeline(rows) {
  const timeline = [];
  let i = 0;
  while (i < rows.length) {
    const row = rows[i];
    if (!_isAgentFlatRow(row)) {
      timeline.push({ ...row, _key: row._key || `msg_${timeline.length}` });
      i += 1;
      continue;
    }
    if (row.source !== 'subagent') {
      timeline.push({
        ..._flatRowToTimelineMsg(row),
        _key: row._key || `msg_${timeline.length}`,
      });
      i += 1;
      continue;
    }
    const ctxKey = _agentCtxKey('subagent', row.agentNs);
    const agentNs = row.agentNs;
    const items = [];
    while (i < rows.length && _isAgentFlatRow(rows[i])) {
      const currentKey = _agentCtxKey(
        rows[i].source === 'subagent' ? 'subagent' : 'supervisor',
        rows[i].agentNs,
      );
      if (currentKey !== ctxKey) break;
      items.push(_flatRowToGroupItem(rows[i]));
      i += 1;
    }
    timeline.push({
      _key: `grp_${ctxKey}_${timeline.length}`,
      _ctxKey: ctxKey,
      role: 'agent_group',
      source: 'subagent',
      agentNs,
      items,
    });
  }
  return timeline;
}

watch(
  () => messages.value.filter((m) => m.role === 'agent_group').map((m) => m._key),
  (keys) => {
    keys.forEach((key) => {
      if (!expandedGroupKeys.value.includes(key)) {
        expandedGroupKeys.value.push(key);
      }
    });
  },
  { immediate: true },
);

function _resetChatState() {
  if (abortController) {
    abortController.abort();
    abortController = null;
  }
  _clearTokenQueue();
  streaming.value = false;
  expandedGroupKeys.value = [];
}

async function loadModels() {
  try {
    const res = await listCrawlerModels();
    modelOptions.value = res.data || [];
    if (modelOptions.value.length > 0 && !currentModelId.value) {
      currentModelId.value = modelOptions.value[0].modelId;
    }
  } catch (e) {
    modelOptions.value = [];
  }
}

function _parseMessageRemark(remark) {
  if (!remark) return {};
  try {
    const meta = JSON.parse(remark);
    if (meta?.source === 'subagent' && meta.agent_ns) {
      return { source: 'subagent', agentNs: meta.agent_ns };
    }
  } catch { /* ignore */ }
  return {};
}

async function loadMessages(sessionId) {
  try {
    const res = await listCrawlerMessages(sessionId, { pageNum: 1, pageSize: 200 });
    const flatRows = (res.rows || res.data || []).map((m) => {
      if (m.role === 'system' && m.content) {
        try {
          const parsed = JSON.parse(m.content);
          if (parsed && parsed.type && (parsed.current_url || parsed.choices)) {
            return {
              role: 'ai',
              type: 'user_choice',
              choiceData: parsed,
              content: parsed.title || '确认操作',
            };
          }
        } catch { /* 非 JSON 系统消息，不做特殊处理 */ }
      }
      if (m.role === 'tool') {
        return _parseStoredToolRow(m);
      }
      return {
        role: m.role,
        content: m.content,
        ..._parseMessageRemark(m.remark),
      };
    });
    messages.value = _rowsToTimeline(flatRows);
    await scrollToBottom();
  } catch (e) {
    messages.value = [];
  }
}

async function handleSendMessage() {
  const content = inputContent.value.trim();
  if (!content || streaming.value) return;

  messages.value.push({ role: 'human', content, _key: `human_${Date.now()}` });
  inputContent.value = '';
  streaming.value = true;
  await scrollToBottom();

  abortController = new AbortController();

  try {
    const response = await fetch(`${contentBase}/crawler/chat/${currentSessionId.value}/message`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + getToken(),
      },
      body: JSON.stringify({ content, modelId: currentModelId.value }),
      signal: abortController.signal,
    });

    await _readSseStream(response);
  } catch (e) {
    if (e.name !== 'AbortError') {
      console.error('[SSE] Stream connection error:', e);
      ElMessage.error('连接失败，请检查网络后重试');
    }
  } finally {
    _finalizeAllStreaming();
    streaming.value = false;
    await scrollToBottom();
    await loadTasks(currentSessionId.value);
  }
}

// ==================== SSE 消息解析 ====================

/** 读取 SSE 流并逐块解析 */
async function _readSseStream(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n\n');
    buffer = lines.pop() || '';
    for (const block of lines) {
      if (block.trim()) parseSseBlock(block);
    }
  }
}

function parseSseBlock(block) {
  const eventMatch = block.match(/event:\s*(.+)/);
  const dataMatch = block.match(/data:\s*(.+)/);
  if (!eventMatch || !dataMatch) return;

  const event = eventMatch[1].trim();
  let data;
  try { data = JSON.parse(dataMatch[1]); } catch { return; }

  const source = data.source || 'supervisor';
  const agentNs = data.agent_ns || null;

  if (event === 'token') {
    _appendToken(source, agentNs, data.content || '');
  } else if (event === 'tool_call') {
    _upsertToolCall(data, source, agentNs);
  } else if (event === 'ask_user') {
    _finalizeAllStreaming();
    messages.value.push({
      _key: `ai_${Date.now()}`,
      role: 'ai',
      content: data.content || '',
      streaming: false,
    });
  } else if (event === 'strategy') {
    _finalizeAllStreaming();
    messages.value.push({
      _key: `strategy_${Date.now()}`,
      role: 'ai',
      type: 'strategy',
      strategyConfig: data,
      content: '请确认爬取策略配置',
    });
  } else if (event === 'task_progress') {
    _finalizeAllStreaming();
    messages.value.push({
      _key: `task_${Date.now()}`,
      role: 'ai',
      type: 'task_progress',
      taskData: data,
      content: '',
    });
  } else if (event === 'done') {
    _finalizeAllStreaming();
  } else if (event === 'error') {
    _finalizeAllStreaming();
    ElMessage.error(data.message || 'Agent 执行出错');
    console.warn('[SSE] Agent error event:', data);
  } else if (event === 'user_choice') {
    _finalizeAllStreaming();
    messages.value.push({
      _key: `choice_${Date.now()}`,
      role: 'ai',
      type: 'user_choice',
      choiceData: data,
      choiceTextInput: '',
      content: data.title || '确认操作',
    });
  }
}

async function handleUserChoice(value, label, choiceData) {
  // 用户对确认类 interrupt 做出决策（value 由后端 choices 下发，如 approve/reject），原样回传
  await _resumeAgentStream(value, choiceData);
}

async function handleUserChoiceText(text, choiceData) {
  const value = (text || '').trim();
  if (!value) return;
  // 同时展示用户补充内容（敏感信息请注意会话权限）
  messages.value.push({ role: 'human', content: value });
  await _resumeAgentStream(value, choiceData);
}

function isChoiceInterrupt(choiceData) {
  if (!choiceData) return true;
  if (choiceData.input_mode === 'text') return false;
  if (choiceData.input_mode === 'choice') return true;
  return Array.isArray(choiceData.choices) && choiceData.choices.length > 0;
}

function isTextInterrupt(choiceData) {
  if (!choiceData) return false;
  if (choiceData.input_mode === 'text') return true;
  if (choiceData.type === 'ask_user' && (!choiceData.choices || choiceData.choices.length === 0)) return true;
  return false;
}

async function _resumeAgentStream(resumeValue, choiceData) {
  streaming.value = true;
  abortController = new AbortController();
  try {
    const response = await fetch(`${contentBase}/crawler/chat/${currentSessionId.value}/resume`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + getToken(),
      },
      body: JSON.stringify({ resumeValue, resumeUrl: (choiceData && choiceData.new_url) || '' }),
      signal: abortController.signal,
    });
    await _readSseStream(response);
  } catch (e) {
    if (e.name !== 'AbortError') {
      console.error('[SSE] Resume stream error:', e);
      ElMessage.error('连接失败，请检查网络后重试');
    }
  } finally {
    _finalizeAllStreaming();
    streaming.value = false;
    await scrollToBottom();
    await loadTasks(currentSessionId.value);
  }
}

function formatChoiceDesc(choiceData) {
  // 后台 description 可能包含 <br/> 标签，替换为换行以便 v-html 渲染
  return (choiceData.description || '请选择后续操作：').replace(/<br\s*\/?>/gi, '<br>');
}

function handleStopGeneration() {
  if (abortController) abortController.abort();
  _flushTokenQueue();
}

function handleInputKeydown(e) {
  // Windows/Linux: Alt+Enter；macOS: Option+Enter 或 Cmd+Enter
  if (e.key === 'Enter' && (e.altKey || e.metaKey)) {
    e.preventDefault();
    handleSendMessage();
  }
}

async function scrollToBottom() {
  await nextTick();
  if (messageAreaRef.value) {
    messageAreaRef.value.scrollTop = messageAreaRef.value.scrollHeight;
  }
}

// ==================== 策略确认 ====================
async function handleStrategyConfirm(config) {
  try {
    await confirmCrawlerStrategy(currentSessionId.value, { crawlConfig: config });
    ElMessage.success('策略已确认，任务已提交');
    await loadTasks(currentSessionId.value);
  } catch (e) {
    ElMessage.error('策略确认失败');
  }
}

async function handleRegenerate() {
  messages.value.push({ role: 'human', content: '请重新生成爬取策略' });
  inputContent.value = '请重新生成爬取策略';
  await handleSendMessage();
}

// ==================== 任务管理（会话内）====================
const taskList = ref([]);
let taskPollTimer = null;

// ==================== 可拖拽调整侧边栏宽度 ====================
const sidebarWidth = ref(220);
const minSidebarWidth = 160;
const maxSidebarWidth = 500;
const isResizing = ref(false);

function startResize(e) {
  isResizing.value = true;
  document.body.style.cursor = 'col-resize';
  document.body.style.userSelect = 'none';
}

function doResize(e) {
  if (!isResizing.value) return;
  const containerEl = document.querySelector('.crawler-container');
  if (!containerEl) return;
  const containerRect = containerEl.getBoundingClientRect();
  let newWidth = e.clientX - containerRect.left;
  if (newWidth < minSidebarWidth) newWidth = minSidebarWidth;
  if (newWidth > maxSidebarWidth) newWidth = maxSidebarWidth;
  sidebarWidth.value = newWidth;
}

function stopResize() {
  if (isResizing.value) {
    isResizing.value = false;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  }
}

onMounted(() => {
  useEventListener(document, 'mousemove', doResize);
  useEventListener(document, 'mouseup', stopResize);
  loadSessions();
});

async function loadTasks(sessionId) {
  // 会话-任务已解耦，不再通过会话查关联任务
  taskList.value = [];
}

function startTaskPolling() {
  stopTaskPolling();
  taskPollTimer = setInterval(async () => {
    const hasRunning = taskList.value.some(t => ['PENDING', 'RUNNING'].includes(t.status));
    if (hasRunning && currentSessionId.value) {
      for (const task of taskList.value) {
        if (['PENDING', 'RUNNING'].includes(task.status)) {
          try {
            const res = await getCrawlTask(task.taskId);
            if (res.data) Object.assign(task, res.data);
          } catch { /* ignore */ }
        }
      }
    }
  }, 5000);
}

function stopTaskPolling() {
  if (taskPollTimer) { clearInterval(taskPollTimer); taskPollTimer = null; }
}

function buildFixRetryMessage(task, taskId) {
  const lines = [
    '任务爬取失败，请分析失败原因并调整参数后重试。',
    `任务ID: ${task.taskId ?? taskId}`,
  ];
  if (task.targetUrl) lines.push(`目标URL: ${task.targetUrl}`);
  if (task.status) lines.push(`任务状态: ${task.status}`);
  if (task.errorCode) lines.push(`错误码: ${task.errorCode}`);
  if (task.errorMessage) lines.push(`错误信息: ${task.errorMessage}`);
  const successCount = task.successCount ?? 0;
  const failedCount = task.failedCount ?? 0;
  const totalCount = task.totalCount ?? 0;
  if (successCount || failedCount || totalCount) {
    lines.push(`成功/失败/总计: ${successCount}/${failedCount}/${totalCount}`);
  }
  return lines.join('\n');
}

async function handleTaskRetry(taskOrId) {
  try {
    let task = typeof taskOrId === 'object' && taskOrId ? taskOrId : null;
    const taskId = task?.taskId ?? taskOrId;
    if (!taskId) {
      ElMessage.error('缺少任务ID');
      return;
    }
    if (!task?.errorCode && !task?.errorMessage) {
      const res = await getCrawlTask(taskId);
      task = { ...(task || {}), ...(res.data || {}) };
    }

    pageTab.value = 'session';
    const res = await addCrawlerSession({});
    await loadSessions();
    const newSession = res.data;
    if (!newSession?.sessionId) {
      ElMessage.error('创建会话失败');
      return;
    }
    await handleSelectSession(newSession.sessionId);

    inputContent.value = buildFixRetryMessage(task || {}, taskId);
    ElMessage.success('已创建修复会话，请确认或编辑消息后发送');
  } catch (e) {
    const errMsg = e?.msg || e?.message || '打开修复会话失败';
    ElMessage.error(errMsg);
  }
}

async function handleTaskPause(taskId) {
  try {
    await pauseCrawlTask(taskId);
    ElMessage.success('已发送暂停指令');
    if (currentSessionId.value) {
      await loadTasks(currentSessionId.value);
    }
    if (pageTab.value === 'task') {
      await loadAllTasks();
    }
  } catch (e) {
    const errMsg = e?.msg || e?.message || '暂停失败';
    ElMessage.error(errMsg);
  }
}

async function handleTaskResume(taskId) {
  try {
    await resumeCrawlTask(taskId);
    ElMessage.success('已发送恢复指令');
    if (currentSessionId.value) {
      await loadTasks(currentSessionId.value);
    }
    if (pageTab.value === 'task') {
      await loadAllTasks();
    }
  } catch (e) {
    const errMsg = e?.msg || e?.message || '恢复失败';
    ElMessage.error(errMsg);
  }
}

async function handleTaskMerge(taskId) {
  try {
    await ElMessageBox.confirm(
      '确定要放弃失败的URL，将已成功爬取的页面写入知识库文档？',
      '确认入库',
      { type: 'warning', confirmButtonText: '确定入库', cancelButtonText: '取消' },
    );
    const res = await mergeCrawlResults(taskId);
    ElMessage.success(res.msg || '入库已提交');
    if (currentSessionId.value) {
      await loadTasks(currentSessionId.value);
    }
    if (pageTab.value === 'task') {
      await loadAllTasks();
    }
  } catch (e) {
    if (e === 'cancel') return;
    const errMsg = e?.msg || e?.message || '入库失败';
    ElMessage.error(errMsg);
  }
}

async function handleTaskDelete(taskId) {
  await ElMessageBox.confirm('确定删除该任务？', '确认删除', { type: 'warning' });
  await delCrawlTask(taskId);
  ElMessage.success('已删除任务');
  if (currentSessionId.value) {
    await loadTasks(currentSessionId.value);
  }
  if (pageTab.value === 'task') {
    await loadAllTasks();
  }
}

async function handleViewDetail(taskId) {
  taskDetailVisible.value = true;
  taskDetail.value = null;
  urlRecordList.value = [];
  urlRecordTotal.value = 0;
  urlRecordPageNum.value = 1;
  urlStatusFilter.value = '';
  detailTab.value = 'info';
  try {
    const res = await getCrawlTask(taskId);
    taskDetail.value = res.data;
  } catch (e) {
    ElMessage.error('获取任务详情失败');
    taskDetailVisible.value = false;
  }
}

function handleDetailTabChange(tabName) {
  if (tabName === 'urls') {
    loadUrlRecords();
  }
}

async function loadUrlRecords() {
  if (!taskDetail.value) return;
  urlRecordLoading.value = true;
  try {
    const res = await listCrawlUrlRecords(taskDetail.value.taskId, {
      pageNum: urlRecordPageNum.value,
      pageSize: urlRecordPageSize.value,
      status: urlStatusFilter.value || undefined,
    });
    urlRecordList.value = res.rows || res.data || [];
    urlRecordTotal.value = res.total || 0;
  } catch (e) {
    urlRecordList.value = [];
    urlRecordTotal.value = 0;
  } finally {
    urlRecordLoading.value = false;
  }
}

// ==================== 文档预览/下载 ====================
const previewVisible = ref(false);
const previewContent = ref('');
const filePickVisible = ref(false);
const filePickMode = ref('preview'); // preview | download
const filePickDocId = ref(null);
const filePickList = ref([]);
const filePickSingleId = ref(null);
const filePickSelected = ref([]);

async function openFilePick(docId, mode) {
  filePickDocId.value = docId;
  filePickMode.value = mode;
  filePickSingleId.value = null;
  filePickSelected.value = [];
  const res = await listDocumentFiles(docId);
  const files = res.data || res || [];
  filePickList.value = files;
  if (!files.length) {
    ElMessage.warning('该文档下没有文件');
    return;
  }
  if (files.length === 1) {
    if (mode === 'preview') {
      await doPreviewDoc(docId, files[0].id);
    } else {
      await doDownloadDoc(docId, { fileId: files[0].id });
    }
    return;
  }
  filePickVisible.value = true;
}

function onFilePickSelection(rows) {
  filePickSelected.value = rows || [];
}

async function confirmFilePick() {
  const docId = filePickDocId.value;
  if (filePickMode.value === 'preview') {
    if (!filePickSingleId.value) {
      ElMessage.warning('请选择一页预览');
      return;
    }
    filePickVisible.value = false;
    await doPreviewDoc(docId, filePickSingleId.value);
    return;
  }
  const ids = filePickSelected.value.map((r) => r.id);
  if (!ids.length) {
    ElMessage.warning('请至少选择一个文件，或使用全量下载');
    return;
  }
  filePickVisible.value = false;
  await doDownloadDoc(docId, { fileIds: ids.join(',') });
}

async function confirmFilePickDownload(all) {
  const docId = filePickDocId.value;
  filePickVisible.value = false;
  await doDownloadDoc(docId, { all: true });
}

async function handlePreviewDoc(docId) {
  try {
    await openFilePick(docId, 'preview');
  } catch (e) {
    ElMessage.error(e?.msg || e?.message || '预览失败');
  }
}

async function handleDownloadDoc(docId) {
  try {
    await openFilePick(docId, 'download');
  } catch (e) {
    ElMessage.error(e?.msg || e?.message || '下载失败');
  }
}

async function doPreviewDoc(docId, fileId) {
  try {
    const res = await previewDocument(docId, { fileId });
    previewContent.value = renderMarkdown(res.data || res);
    previewVisible.value = true;
  } catch (e) {
    ElMessage.error(e?.msg || e?.message || '预览失败');
  }
}

async function doDownloadDoc(docId, params) {
  try {
    const res = await downloadDocument(docId, params);
    const blob = new Blob([res.data || res]);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const multi = params?.all || (params?.fileIds && String(params.fileIds).includes(','));
    a.download = multi ? `document_${docId}.zip` : `document_${docId}.md`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    ElMessage.error(e?.msg || e?.message || '下载失败');
  }
}

// ==================== 页面级 Tab 切换（任务详情 / 文档信息）====================
const pageTab = ref('session');

// --- 全部任务 ---
const allTaskLoading = ref(false);
const allTaskList = ref([]);
const taskFilterStatus = ref('');
const taskFilterErrorCode = ref('');
const taskFilterCreateBy = ref('');
const taskStatusOptions = ref([]);
const taskErrorCodeOptions = ref([]);

// 从后端选项数组构建 {value: {label, type}} 映射
const taskStatusMap = computed(() => {
  const map = {};
  for (const opt of taskStatusOptions.value) {
    map[opt.value] = { label: opt.label, type: opt.type || 'info' };
  }
  return map;
});

// --- 任务详情弹框 ---
const taskDetailVisible = ref(false);
const taskDetail = ref(null);

const detailStatusLabel = computed(() => taskStatusMap.value[taskDetail.value?.status]?.label || taskDetail.value?.status || '-');
const detailStatusType = computed(() => taskStatusMap.value[taskDetail.value?.status]?.type || 'info');

const formattedConfig = computed(() => {
  if (!taskDetail.value?.crawlConfig) return '';
  try {
    const parsed = typeof taskDetail.value.crawlConfig === 'string'
      ? JSON.parse(taskDetail.value.crawlConfig)
      : taskDetail.value.crawlConfig;
    return JSON.stringify(parsed, null, 2);
  } catch {
    return taskDetail.value.crawlConfig;
  }
});

// --- URL记录 ---
const detailTab = ref('info');
const urlRecordList = ref([]);
const urlRecordLoading = ref(false);
const urlRecordTotal = ref(0);
const urlRecordPageNum = ref(1);
const urlRecordPageSize = ref(20);
const urlStatusFilter = ref('');

const filteredAllTasks = computed(() => {
  let list = allTaskList.value;
  if (taskFilterStatus.value) {
    list = list.filter(t => t.status === taskFilterStatus.value);
  }
  if (taskFilterErrorCode.value) {
    list = list.filter(t => t.errorCode === taskFilterErrorCode.value);
  }
  if (taskFilterCreateBy.value) {
    const keyword = taskFilterCreateBy.value.toLowerCase();
    list = list.filter(t => t.createBy && t.createBy.toLowerCase().includes(keyword));
  }
  return list;
});

async function loadEnumOptions() {
  try {
    const [statusRes, errorCodeRes] = await Promise.all([
      getTaskStatusOptions(),
      getTaskErrorCodeOptions(),
    ]);
    taskStatusOptions.value = statusRes.data || [];
    taskErrorCodeOptions.value = errorCodeRes.data || [];
  } catch (e) {
    taskStatusOptions.value = [];
    taskErrorCodeOptions.value = [];
  }
}

async function loadAllTasks() {
  allTaskLoading.value = true;
  try {
    const params = { pageNum: 1, pageSize: 200 };
    if (taskFilterStatus.value) params.status = taskFilterStatus.value;
    if (taskFilterCreateBy.value) params.createBy = taskFilterCreateBy.value;
    const res = await listCrawlTask(params);
    allTaskList.value = res.rows || res.data || [];
  } catch (e) {
    allTaskList.value = [];
  } finally {
    allTaskLoading.value = false;
  }
}

function resetTaskFilters() {
  taskFilterStatus.value = '';
  taskFilterErrorCode.value = '';
  taskFilterCreateBy.value = '';
  loadAllTasks();
}

// --- 全部文档 ---
const allDocLoading = ref(false);
const allDocList = ref([]);
const docFilterTitle = ref('');
const docFilterStatus = ref('');
const docFilterCreateBy = ref('');
const docFilterDelFlag = ref('');

// 文档状态选项
const docStatusOptions = [
  { value: 'CONVERTED', label: '已转换' },
  { value: 'CHUNKED', label: '已分块' },
  { value: 'VECTOR_STORED', label: '已入库' },
];

const docStatusLabel = (status) => {
  const opt = docStatusOptions.find(o => o.value === status);
  return opt ? opt.label : status;
};

const docStatusType = (status) => {
  const map = { CONVERTED: 'success', CHUNKED: 'warning', VECTOR_STORED: 'primary' };
  return map[status] || 'info';
};

const filteredAllDocs = computed(() => {
  return allDocList.value;
});

async function loadAllDocs() {
  allDocLoading.value = true;
  try {
    const params = { pageNum: 1, pageSize: 200 };
    if (docFilterTitle.value) params.docTitle = docFilterTitle.value;
    if (docFilterStatus.value) params.status = docFilterStatus.value;
    if (docFilterCreateBy.value) params.createBy = docFilterCreateBy.value;
    if (docFilterDelFlag.value) params.delFlag = docFilterDelFlag.value;
    const res = await listCrawlerDocument(params);
    allDocList.value = res.rows || res.data || [];
  } catch (e) {
    allDocList.value = [];
  } finally {
    allDocLoading.value = false;
  }
}

function resetDocFilters() {
  docFilterTitle.value = '';
  docFilterStatus.value = '';
  docFilterCreateBy.value = '';
  docFilterDelFlag.value = '';
  loadAllDocs();
}

function handlePageTabChange(tabName) {
  if (tabName === 'task') {
    loadAllTasks();
    loadAllSessions();
  } else if (tabName === 'document') {
    loadAllDocs();
    loadAllSessions();
  }
}

// ==================== Markdown 渲染 ====================
function renderMarkdown(text) {
  if (!text) return '';
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/\n/g, '<br>');
}

// ==================== 生命周期 ====================
onMounted(() => {
  loadEnumOptions();
  loadModels();
});
onBeforeUnmount(() => {
  stopTaskPolling();
  _clearTokenQueue();
});
</script>

<style scoped>
.crawler-container { height: calc(100vh - 84px); padding: 0; display: flex; flex-direction: column; }

/* 页面级 Tab 占满剩余高度 */
.page-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.page-tabs :deep(.el-tabs__header) {
  margin: 0 16px;
}
.page-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow: hidden;
}
.page-tabs :deep(.el-tab-pane) {
  height: 100%;
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

.chat-main { display: flex; flex-direction: column; padding: 0; }

/* 聊天区域标题 */
.chat-header { display: flex; align-items: center; gap: 8px; padding: 10px 16px; border-bottom: 1px solid #e4e7ed; background: #fff; flex-shrink: 0; }
.chat-header-title { font-size: 14px; font-weight: 600; color: #303133; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.message-area { flex: 1; overflow-y: auto; padding: 16px; background: #f0f2f5; }
.message-item { margin-bottom: 16px; }
.message-human { display: flex; justify-content: flex-end; }
.message-ai { display: flex; justify-content: flex-start; }
.message-system { display: flex; justify-content: center; }
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

/* 父图 / 子图统一消息框：外层折叠 */
.agent-group-collapse { max-width: 70%; margin-bottom: 8px; border-radius: 8px; overflow: hidden; }
.supervisor-group-collapse { border: 2px solid #409eff; background: linear-gradient(135deg, #f5f9ff 0%, #ecf5ff 100%); }
.supervisor-group-collapse :deep(.el-collapse-item__header) { background: transparent; border-bottom: 1px dashed #d0d5dd; padding: 10px 12px; height: auto; line-height: 1.5; }
.supervisor-group-body { padding: 4px 0; }

/* 子图分组消息框 */
.subagent-group-collapse { border: 2px solid #67c23a; background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%); }
.subagent-group-collapse :deep(.el-collapse-item__header) { background: transparent; border-bottom: 1px dashed #d0d5dd; padding: 10px 12px; height: auto; line-height: 1.5; }
.subagent-group-collapse :deep(.el-collapse-item__wrap) { background: transparent; border: none; }
.subagent-group-collapse :deep(.el-collapse-item__content) { padding: 12px; }
.supervisor-group-collapse :deep(.el-collapse-item__wrap) { background: transparent; border: none; }
.supervisor-group-collapse :deep(.el-collapse-item__content) { padding: 12px; }
.subagent-group-body { position: relative; }
.subagent-group-body::before { content: ''; position: absolute; left: -16px; top: 0; bottom: 0; width: 4px; background: #67c23a; border-radius: 4px 0 0 4px; }
.agent-ns-label { margin-left: 8px; font-size: 12px; color: #909399; font-family: monospace; background: #f5f7fa; padding: 2px 6px; border-radius: 4px; }

/* 组内 AI 文本：直接展示，由外层 agent_group 统一折叠 */
.ai-text-block { margin-bottom: 10px; font-size: 14px; line-height: 1.6; }
.ai-text-block:last-child { margin-bottom: 0; }
.ai-text-block.ai-text-streaming { border-left: 3px solid #409eff; padding-left: 10px; }
.subagent-group-body .ai-text-block.ai-text-streaming { border-left-color: #67c23a; }
.subagent-ai-text { font-size: 14px; line-height: 1.6; }
.supervisor-ai-text { font-size: 14px; line-height: 1.6; }

/* 子图工具卡片样式 */
.subagent-tool { border-color: #67c23a; background: linear-gradient(135deg, #fafafa 0%, #f0f9ff 100%); }
.tool-section { margin-bottom: 8px; }
.tool-section:last-child { margin-bottom: 0; }
.tool-section-label { font-size: 12px; font-weight: 600; color: #606266; margin-bottom: 4px; }
.tool-section-hint { font-size: 12px; color: #909399; font-style: italic; padding: 4px 0; }
.tool-content { font-size: 12px; max-height: 300px; overflow: auto; background: #f5f7fa; padding: 8px; border-radius: 4px; white-space: pre-wrap; word-break: break-all; }

/* 流式指示器内子图区域 */
.streaming-supervisor { margin-bottom: 10px; }
.subagent-streaming-section { margin-top: 10px; padding-top: 10px; border-top: 1px dashed #d0d5dd; }
.subagent-streaming-header { display: flex; align-items: center; margin-bottom: 6px; }
.subagent-streaming-content { font-size: 14px; color: #606266; white-space: pre-wrap; }

/* URL 路由审批卡片 */
.user-choice-card { max-width: 85%; }
.choice-title { font-size: 15px; font-weight: 600; color: #303133; margin-bottom: 8px; }
.choice-desc { font-size: 13px; color: #606266; margin-bottom: 10px; line-height: 1.6; }
.choice-urls { background: #f5f7fa; border-radius: 6px; padding: 8px 10px; margin-bottom: 10px; }
.url-row { display: flex; align-items: center; margin-bottom: 4px; font-size: 13px; }
.url-row:last-child { margin-bottom: 0; }
.url-text { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #409eff; font-size: 12px; }
.choice-cache { background: #f0f9eb; border-radius: 6px; padding: 8px 10px; margin-bottom: 10px; }
.cache-preview { font-size: 12px; color: #606266; margin-top: 4px; white-space: pre-wrap; word-break: break-all; max-height: 100px; overflow-y: auto; }
.choice-buttons { display: flex; gap: 8px; flex-wrap: wrap; }

.input-area { padding: 12px 16px; border-top: 1px solid #d0d5dd; background: #fff; box-shadow: 0 -2px 8px rgba(0,0,0,0.04); }
.input-toolbar { display: flex; align-items: center; margin-bottom: 8px; }
.input-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }

/* 欢迎页（无会话时） */
.welcome-screen { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: #909399; opacity: 0.8; }
.welcome-icon { background: #f5f7fa; border-radius: 50%; padding: 20px; margin-bottom: 20px; color: #409eff; }
.welcome-screen h2 { margin-bottom: 10px; font-weight: 500; font-size: 18px; color: #606266; }
.welcome-screen p { font-size: 14px; }

.task-list-area { padding: 16px; overflow-y: auto; flex: 1; }
.task-item { margin-bottom: 16px; }

.document-list-area { padding: 16px; overflow-y: auto; flex: 1; }

/* 任务详情页 */
.task-page, .document-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.task-header, .doc-header {
  padding: 12px 16px;
  border-bottom: 1px solid var(--el-border-color);
  flex-shrink: 0;
}

/* URL记录筛选行 */
.url-filter-row {
  margin-bottom: 12px;
}

/* URL记录分页 */
.url-pagination {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}

.streaming-indicator { animation: pulse 1.5s ease-in-out infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }

.doc-preview { max-height: 70vh; overflow-y: auto; padding: 16px; line-height: 1.8; }
.doc-preview :deep(pre) { background: #f5f7fa; padding: 12px; border-radius: 4px; overflow-x: auto; }

/* 可拖拽调整宽度的分隔条 */
.resize-handle {
  width: 8px;
  cursor: col-resize;
  position: relative;
  z-index: 20;
  flex-shrink: 0;
  background: var(--el-border-color);
  transition: background-color 0.15s;
}

.resize-handle::before {
  content: '';
  position: absolute;
  left: 3px;
  top: 50%;
  transform: translateY(-50%);
  width: 2px;
  height: 40px;
  border-radius: 2px;
  background: var(--el-border-color-extra-light, #dcdfe6);
  transition: background-color 0.15s;
  pointer-events: none;
}

.resize-handle:hover,
.resize-handle:active {
  background: var(--el-color-primary-light-5, #79bbff);
}

.resize-handle:hover::before,
.resize-handle:active::before {
  background: #fff;
}

/* 深色模式适配 */
html.dark .resize-handle {
  background: var(--el-border-color-darker, #555);
}
html.dark .resize-handle:hover,
html.dark .resize-handle:active {
  background: var(--el-color-primary-light-5);
}

/* 配置信息 */
.config-content { padding: 16px 0; }
.config-json {
  background: #f5f7fa;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  padding: 16px;
  font-size: 13px;
  line-height: 1.6;
  overflow: auto;
  max-height: 500px;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}
</style>
