<template>
  <div class="app-container">
    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button icon="Back" @click="handleClose">返回</el-button>
      </el-col>
      <el-col :span="16" class="eval-page-title">{{ pageTitle }}</el-col>
    </el-row>
    <div class="eval-report-head">进度 {{ progressText }}</div>
    <MetricChart v-if="showChart" type="line" :categories="chartCategories" :series="chartSeries" />
    <el-empty v-else-if="!loading" description="还没有分数" :image-size="72" />

    <el-table v-loading="loading" :data="reportItems">
      <el-table-column label="顺序" prop="sortOrder" width="70" align="center" />
      <el-table-column label="问题" prop="question" min-width="280" show-overflow-tooltip />
      <el-table-column
        v-for="(label, key) in metricLabels"
        :key="key"
        :label="label"
        width="100"
        align="center"
      >
        <template #default="{ row }">{{ formatMetric(row.metrics, key) }}</template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup name="EvalTaskReport">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getEvalRunReport } from '@/api/knowledge/evalTask'
import MetricChart from './MetricChart.vue'
import { formatMetric, formatProgress, hasMetric, metricLabels, metricNumber } from './metrics'

const { proxy } = getCurrentInstance()
const route = useRoute()

const loading = ref(false)
const reportItems = ref([])
const summary = ref(null)

const pageTitle = computed(() => `逐题得分 - 执行 ${route.params.runId}`)
const progressText = computed(() => formatProgress(summary.value))
const chartCategories = computed(() => reportItems.value.map((row, index) => String(row.sortOrder ?? index)))
const chartSeries = computed(() => Object.entries(metricLabels).map(([key, name]) => ({
  name,
  data: reportItems.value.map((row) => metricNumber(row.metrics, key))
})))
const showChart = computed(() => reportItems.value.some((row) => hasMetric(row.metrics)))

function syncTabTitle() {
  proxy.$tab.updatePage({
    path: route.path,
    title: pageTitle.value,
    meta: { ...route.meta, title: pageTitle.value }
  })
}

function loadReport() {
  loading.value = true
  getEvalRunReport(route.params.runId).then((response) => {
    const data = response.data || {}
    reportItems.value = data.items || []
    summary.value = data.summary || null
  }).finally(() => {
    loading.value = false
  })
}

function handleClose() {
  const taskId = route.query.taskId
  if (taskId) {
    proxy.$tab.closeOpenPage({
      path: `/knowledge/eval-task-run/index/${taskId}`,
      query: { name: route.query.name || '' }
    })
    return
  }
  proxy.$tab.closeOpenPage({ path: '/knowledge/eval-task' })
}

onMounted(() => {
  syncTabTitle()
  loadReport()
})
</script>

<style scoped>
.eval-page-title {
  line-height: 32px;
  font-size: 16px;
  font-weight: 600;
}

.eval-report-head {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 12px;
  color: var(--el-text-color-regular);
  line-height: 22px;
}
</style>
