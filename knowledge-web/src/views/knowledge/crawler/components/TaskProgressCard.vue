<template>
  <el-card class="task-card" shadow="hover">
    <template #header>
      <div class="card-header">
        <span>🚀 爬取任务</span>
        <el-tag :type="statusType" size="small">{{ statusLabel }}</el-tag>
      </div>
    </template>

    <div class="task-info">
      <div class="info-row">
        <span class="label">目标URL:</span>
        <el-link :href="task.targetUrl" target="_blank" type="primary" class="url-link">{{ task.targetUrl }}</el-link>
        <span class="label step-label" v-if="task.currentStep">当前步骤:</span>
        <span v-if="task.currentStep" class="step-value">{{ task.currentStep }}</span>
        <span class="label step-label">操作用户:</span>
        <span>{{ task.createBy || '-' }}</span>
      </div>

      <div class="info-row">
        <span class="label">错误码:</span>
        <el-tag v-if="task.errorCode" type="danger" size="small">{{ task.errorCode }}</el-tag>
        <span v-else>-</span>
        <span class="label info-label">错误信息:</span>
        <el-alert v-if="task.errorMessage" :title="task.errorMessage" type="error" :closable="false" show-icon class="error-alert-inline" />
        <span v-else>-</span>
      </div>

      <!-- 进度条 -->
      <div class="progress-row">
        <el-progress :percentage="task.progress || 0" :status="progressStatus" />
      </div>

      <!-- 统计数据 -->
      <div class="stats-row">
        <el-tag type="success" size="small">成功: {{ task.successCount || 0 }}</el-tag>
        <el-tag type="danger" size="small" v-if="task.failedCount > 0">失败: {{ task.failedCount }}</el-tag>
        <el-tag size="small">总计: {{ task.totalCount || 0 }}</el-tag>
      </div>

      <!-- 操作按钮 -->
      <div class="task-actions">
        <el-button type="info" size="small" @click="$emit('view-detail', task.taskId)">查看详情</el-button>
        <el-button v-if="task.status === 'RUNNING'" type="warning" size="small" @click="$emit('pause-task', task.taskId)">暂停</el-button>
        <el-button v-if="task.status === 'PAUSED'" type="primary" size="small" @click="$emit('resume-task', task.taskId)">恢复</el-button>
        <el-button v-if="showActions" type="primary" size="small" @click="$emit('retry', task)">会话调参修复</el-button>
        <el-button v-if="task.status === 'FAILED' || task.status === 'USER_DECISION' || task.status === 'PAUSED' || task.status === 'CONVERT_FAILED'" type="success" size="small" @click="$emit('merge', task.taskId)">合并已爬内容</el-button>
        <el-button v-if="canDelete" type="danger" size="small" plain @click="$emit('delete-task', task.taskId)">删除任务</el-button>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  task: { type: Object, default: () => ({}) },
  statusOptions: { type: Array, default: () => [] },
});

defineEmits(['retry', 'view-detail', 'delete-task', 'pause-task', 'resume-task', 'merge']);

// 执行中 / 已进入合并链路（含已转换）均不可删，与后端 delete_task 守卫一致
const DELETE_BLOCKED_STATUSES = ['PENDING', 'RUNNING', 'COMPLETED', 'CONVERTING', 'CONVERTED'];

// 从后端选项数组构建 {value: {label, type}} 映射
const statusMap = computed(() => {
  const map = {};
  for (const opt of props.statusOptions) {
    map[opt.value] = { label: opt.label, type: opt.type || 'info' };
  }
  return map;
});

const statusLabel = computed(() => statusMap.value[props.task.status]?.label || props.task.status);
const statusType = computed(() => statusMap.value[props.task.status]?.type || 'info');

const progressStatus = computed(() => {
  if (['COMPLETED', 'CONVERTED'].includes(props.task.status)) return 'success';
  if (['FAILED', 'CONVERT_FAILED'].includes(props.task.status)) return 'exception';
  return '';
});

const showActions = computed(() => ['FAILED', 'USER_DECISION'].includes(props.task.status));
const canDelete = computed(() => !DELETE_BLOCKED_STATUSES.includes(props.task.status));
</script>

<style scoped>
.task-card { margin-bottom: 12px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.task-info { font-size: 13px; }
.info-row { display: flex; align-items: center; margin-bottom: 8px; gap: 8px; }
.label { color: #606266; min-width: 80px; flex-shrink: 0; }
.url-link { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex-shrink: 1; }
.step-label { min-width: auto; margin-left: 8px; flex-shrink: 0; }
.step-value { flex-shrink: 0; }
.info-label { min-width: auto; }
.progress-row { margin: 12px 0; }
.stats-row { display: flex; gap: 8px; margin-bottom: 8px; }
.error-alert-inline { flex: 1; min-width: 0; }
.task-actions { display: flex; gap: 8px; margin-top: 12px; }
</style>
