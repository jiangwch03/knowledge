<template>
  <div class="app-container">
    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button icon="Back" @click="handleClose">返回</el-button>
      </el-col>
      <el-col :span="12" class="eval-page-title">{{ pageTitle }}</el-col>
    </el-row>

    <el-row v-if="chartCategories.length" :gutter="16" class="eval-trend-row">
      <el-col v-for="item in trendCharts" :key="item.key" :span="12">
        <MetricChart
          type="line"
          :height="220"
          :title="item.name"
          :color="item.color"
          :categories="chartCategories"
          :series="[{ name: item.name, data: item.data }]"
        />
      </el-col>
    </el-row>
    <el-empty v-else-if="!loading" description="还没有分数" :image-size="72" />

    <el-table v-loading="loading" :data="runList">
      <el-table-column label="执行 ID" prop="runId" width="90" align="center" />
      <el-table-column label="状态" prop="status" width="100" align="center">
        <template #default="{ row }">{{ runStatusLabel(row.status) }}</template>
      </el-table-column>
      <el-table-column label="进度" width="90" align="center">
        <template #default="{ row }">{{ formatProgress(row.summaryMetrics) }}</template>
      </el-table-column>
      <el-table-column
        v-for="(label, key) in metricLabels"
        :key="key"
        :label="label"
        width="100"
        align="center"
      >
        <template #default="{ row }">{{ formatMetric(row.summaryMetrics, key) }}</template>
      </el-table-column>
      <el-table-column label="失败原因" prop="errorMessage" min-width="180" show-overflow-tooltip />
      <el-table-column label="开始时间" prop="startedAt" width="170" align="center">
        <template #default="{ row }"><span>{{ parseTime(row.startedAt) }}</span></template>
      </el-table-column>
      <el-table-column label="操作" width="80" align="center">
        <template #default="{ row }">
          <el-button link type="primary" @click="openReport(row)">明细</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup name="EvalTaskRuns">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { listEvalRuns } from '@/api/knowledge/evalTask'
import MetricChart from './MetricChart.vue'
import { formatMetric, formatProgress, hasMetric, metricLabels, metricNumber, runStatusLabel } from './metrics'

const { proxy } = getCurrentInstance()
const route = useRoute()
const router = useRouter()

const loading = ref(false)
const runList = ref([])
let runPollTimer = null

const pageTitle = computed(() => {
  const name = route.query.name
  return name ? `执行记录 - ${name}` : '执行记录'
})

const trendColors = ['#409EFF', '#67C23A', '#E6A23C', '#F56C6C']
const trendRuns = computed(() => runList.value.filter((row) => hasMetric(row.summaryMetrics)).slice(0, 4).reverse())
const chartCategories = computed(() => trendRuns.value.map((row) => `执行 ${row.runId}`))
const trendCharts = computed(() => Object.entries(metricLabels).map(([key, name], index) => ({
  key,
  name,
  color: trendColors[index],
  data: trendRuns.value.map((row) => metricNumber(row.summaryMetrics, key))
})))

function syncTabTitle() {
  proxy.$tab.updatePage({
    path: route.path,
    title: pageTitle.value,
    meta: { ...route.meta, title: pageTitle.value }
  })
}

function loadRuns(silent) {
  if (!silent) loading.value = true
  listEvalRuns(route.params.evalTaskId, { pageNum: 1, pageSize: 20 }).then((response) => {
    runList.value = response.rows || []
  }).finally(() => {
    if (!silent) loading.value = false
  })
}

function startPoll() {
  stopPoll()
  runPollTimer = setInterval(() => {
    if (!runList.value.some((item) => item.status === 'RUNNING' || item.status === 'PENDING')) {
      return
    }
    loadRuns(true)
  }, 5000)
}

function stopPoll() {
  if (runPollTimer) {
    clearInterval(runPollTimer)
    runPollTimer = null
  }
}

function openReport(row) {
  router.push({
    path: `/knowledge/eval-task-run/report/${row.runId}`,
    query: {
      taskId: route.params.evalTaskId,
      name: route.query.name || ''
    }
  })
}

function handleClose() {
  proxy.$tab.closeOpenPage({ path: '/knowledge/eval-task' })
}

onMounted(() => {
  syncTabTitle()
  loadRuns(false)
  startPoll()
})

onUnmounted(stopPoll)
</script>

<style scoped>
.eval-page-title {
  line-height: 32px;
  font-size: 16px;
  font-weight: 600;
}

.eval-trend-row {
  margin-bottom: 8px;
}
</style>
