<template>
  <div class="app-container">
    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button icon="Back" @click="handleClose">返回</el-button>
      </el-col>
      <el-col :span="12" class="dataset-title">{{ pageTitle }}</el-col>
    </el-row>

    <el-form :model="query" ref="queryRef" :inline="true">
      <el-form-item label="问题" prop="question">
        <el-input v-model="query.question" placeholder="问题" clearable style="width: 220px" @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="题目类型" prop="difficulty">
        <el-select v-model="query.difficulty" placeholder="全部" clearable style="width: 140px">
          <el-option v-for="item in questionTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="计入测评" prop="enabled">
        <el-select v-model="query.enabled" placeholder="全部" clearable style="width: 120px">
          <el-option label="计入" :value="1" />
          <el-option label="排除" :value="0" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-table v-loading="loading" :data="itemList">
      <el-table-column label="问题" prop="question" min-width="280" show-overflow-tooltip />
      <el-table-column label="标准答案" prop="groundTruth" min-width="280" show-overflow-tooltip />
      <el-table-column label="题目类型" width="110" align="center">
        <template #default="{ row }">
          <span>{{ questionTypeLabel(row.difficulty) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="计入测评" width="110" align="center">
        <template #default="{ row }">
          <el-tag :type="row.enabled === 1 ? 'success' : 'info'" size="small">{{ row.enabled === 1 ? '计入' : '排除' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="90" align="center">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)" v-hasPermi="['rag:eval:dataset:edit']">改题</el-button>
        </template>
      </el-table-column>
    </el-table>
    <pagination
      v-show="total > 0"
      :total="total"
      v-model:page="query.pageNum"
      v-model:limit="query.pageSize"
      @pagination="loadItems"
    />

    <el-dialog title="改题" v-model="editOpen" width="640px" append-to-body>
      <el-form :model="editForm" label-width="100px">
        <el-form-item label="问题">
          <el-input v-model="editForm.question" type="textarea" :rows="4" />
        </el-form-item>
        <el-form-item label="标准答案">
          <el-input v-model="editForm.groundTruth" type="textarea" :rows="4" />
        </el-form-item>
        <el-form-item label="计入测评">
          <el-switch v-model="editForm.enabled" :active-value="1" :inactive-value="0" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button type="primary" :loading="submitLoading" @click="submitEdit">保 存</el-button>
        <el-button @click="editOpen = false">取 消</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="EvalDatasetItems">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { listEvalDatasetItems, updateEvalDatasetItem } from '@/api/knowledge/evalDataset'

const { proxy } = getCurrentInstance()
const route = useRoute()

const loading = ref(false)
const submitLoading = ref(false)
const itemList = ref([])
const total = ref(0)
const query = ref({ pageNum: 1, pageSize: 10, question: undefined, difficulty: undefined, enabled: undefined })
const editOpen = ref(false)
const editForm = ref({ itemId: undefined, question: '', groundTruth: '', enabled: 1 })

const questionTypeOptions = [
  { value: 'simple', label: '简单题' },
  { value: 'multi_hop', label: '多跳题' },
  { value: 'comprehensive', label: '综合题' },
  { value: 'vague', label: '模糊题' },
  { value: 'adversarial', label: '对抗题' }
]

const questionTypeLabels = {
  simple: '简单题',
  single_hop_specific_query_synthesizer: '简单题',
  multi_hop: '多跳题',
  multi_hop_specific_query_synthesizer: '多跳题',
  multi_hop_abstract_query_synthesizer: '多跳题',
  comprehensive: '综合题',
  vague: '模糊题',
  adversarial: '对抗题'
}

const pageTitle = computed(() => {
  const name = route.query.name
  return name ? `题目 - ${name}` : '测评集题目'
})

function questionTypeLabel(value) {
  if (!value) {
    return '-'
  }
  return questionTypeLabels[value] || value
}

function syncTabTitle() {
  proxy.$tab.updatePage({
    path: route.path,
    title: pageTitle.value,
    meta: { ...route.meta, title: pageTitle.value }
  })
}

function loadItems() {
  loading.value = true
  const params = { ...query.value }
  if (!params.question) {
    delete params.question
  }
  if (!params.difficulty) {
    delete params.difficulty
  }
  if (params.enabled === '' || params.enabled == null) {
    delete params.enabled
  }
  listEvalDatasetItems(route.params.datasetId, params).then((response) => {
    itemList.value = response.rows || []
    total.value = response.total || 0
  }).finally(() => {
    loading.value = false
  })
}

function handleQuery() {
  query.value.pageNum = 1
  loadItems()
}

function resetQuery() {
  proxy.resetForm('queryRef')
  handleQuery()
}

function openEdit(row) {
  editForm.value = {
    itemId: row.itemId,
    question: row.question || '',
    groundTruth: row.groundTruth || '',
    enabled: row.enabled === 0 ? 0 : 1
  }
  editOpen.value = true
}

function submitEdit() {
  submitLoading.value = true
  updateEvalDatasetItem(editForm.value.itemId, {
    question: editForm.value.question,
    groundTruth: editForm.value.groundTruth,
    enabled: editForm.value.enabled
  }).then(() => {
    proxy.$modal.msgSuccess('已保存')
    editOpen.value = false
    loadItems()
  }).finally(() => {
    submitLoading.value = false
  })
}

function handleClose() {
  proxy.$tab.closeOpenPage({ path: '/knowledge/eval-dataset' })
}

onMounted(() => {
  syncTabTitle()
  loadItems()
})
</script>

<style scoped>
.dataset-title {
  line-height: 32px;
  font-size: 16px;
  font-weight: 600;
}
</style>
