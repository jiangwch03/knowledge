<template>
  <el-card class="strategy-card" shadow="hover">
    <template #header>
      <div class="card-header">
        <span>📋 爬取策略配置</span>
        <el-tag :type="confirmed ? 'success' : 'warning'" size="small">
          {{ confirmed ? '已确认' : '待确认' }}
        </el-tag>
      </div>
    </template>

    <div class="config-summary" v-if="config">
      <div v-for="(value, key) in config" :key="key" class="config-item">
        <span class="config-key">{{ formatKey(key) }}:</span>
        <span class="config-value">{{ formatValue(value) }}</span>
      </div>
    </div>
    <el-empty v-else description="暂无策略配置" :image-size="60" />

    <div class="card-actions" v-if="!confirmed">
      <el-button type="primary" @click="$emit('confirm', config)">确认配置</el-button>
      <el-button @click="$emit('regenerate')">重新生成</el-button>
    </div>
  </el-card>
</template>

<script setup>
defineProps({
  config: { type: Object, default: () => ({}) },
  sessionId: { type: Number, default: null },
});

defineEmits(['confirm', 'regenerate']);

const confirmed = false;

function formatKey(key) {
  const labels = {
    url_pattern: 'URL模式', max_pages: '最大页面数', max_depth: '最大深度',
    delay: '请求延迟(秒)', include_pattern: '包含路径', exclude_pattern: '排除路径',
    javascript_enabled: '启用JS', wait_for: '等待元素', css_selector: 'CSS选择器',
    word_count_threshold: '字数阈值',
  };
  return labels[key] || key;
}

function formatValue(value) {
  if (Array.isArray(value)) return value.join(', ');
  if (typeof value === 'boolean') return value ? '是' : '否';
  return String(value);
}
</script>

<style scoped>
.strategy-card { margin: 8px 0; max-width: 70%; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.config-summary { margin-bottom: 12px; }
.config-item { display: flex; padding: 4px 0; font-size: 13px; border-bottom: 1px dashed #ebeef5; }
.config-key { color: #606266; min-width: 120px; font-weight: 500; }
.config-value { color: #303133; word-break: break-all; }
.card-actions { display: flex; gap: 8px; margin-top: 12px; }
</style>
