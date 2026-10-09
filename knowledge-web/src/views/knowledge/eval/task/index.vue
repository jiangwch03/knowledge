<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch">
      <el-form-item label="名称" prop="name">
        <el-input v-model="queryParams.name" placeholder="任务名称" clearable style="width: 180px" @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="状态" prop="status">
        <el-select v-model="queryParams.status" placeholder="全部" clearable style="width: 140px">
          <el-option label="进行中" value="OPEN" />
          <el-option label="已归档" value="ARCHIVED" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button type="primary" plain icon="Plus" @click="handleAdd" v-hasPermi="['rag:eval:task:create']">创建任务</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList" />
    </el-row>

    <el-table v-loading="loading" :data="taskList">
      <el-table-column label="ID" prop="evalTaskId" width="90" align="center" />
      <el-table-column label="名称" prop="name" min-width="160" show-overflow-tooltip />
      <el-table-column label="文档" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">
          <div v-if="row.docTitle" class="eval-bind-name">{{ row.docTitle }}</div>
          <div class="eval-bind-id">ID {{ row.docId }}</div>
        </template>
      </el-table-column>
      <el-table-column label="测评集" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          <div v-if="row.datasetName" class="eval-bind-name">{{ row.datasetName }}</div>
          <div class="eval-bind-id">ID {{ row.datasetId }}</div>
        </template>
      </el-table-column>
      <el-table-column label="向量化任务" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          <div v-if="row.embeddingSplitLabel" class="eval-bind-name">{{ row.embeddingSplitLabel }}</div>
          <div class="eval-bind-id">ID {{ row.embeddingTaskId }}</div>
        </template>
      </el-table-column>
      <el-table-column label="状态" prop="status" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.status === 'OPEN' ? 'success' : 'info'" size="small">{{ row.status === 'OPEN' ? '进行中' : '已归档' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="发布时间" prop="publishTime" width="170" align="center">
        <template #default="{ row }"><span>{{ parseTime(row.publishTime) }}</span></template>
      </el-table-column>
      <el-table-column label="操作" align="center" width="320">
        <template #default="{ row }">
          <el-button link type="primary" @click="handleSwap(row)" v-hasPermi="['rag:eval:task:create']" :disabled="row.status !== 'OPEN'">换测评集</el-button>
          <el-button link type="primary" @click="handleRun(row)" v-hasPermi="['rag:eval:task:run']" :disabled="row.status !== 'OPEN'">跑测评</el-button>
          <el-button link type="primary" @click="openRuns(row)" v-hasPermi="['rag:eval:task:query']">执行记录</el-button>
          <el-button link type="primary" @click="handlePublish(row)" v-hasPermi="['rag:eval:task:publish']" :disabled="row.status !== 'OPEN'">发布</el-button>
        </template>
      </el-table-column>
    </el-table>
    <pagination
      v-show="total > 0"
      :total="total"
      v-model:page="queryParams.pageNum"
      v-model:limit="queryParams.pageSize"
      @pagination="getList"
    />

    <el-dialog title="创建测评任务" v-model="createOpen" width="640px" append-to-body>
      <el-form ref="createRef" :model="createForm" :rules="createRules" label-width="110px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="createForm.name" placeholder="任务名称" maxlength="128" />
        </el-form-item>
        <el-form-item label="测评集" prop="datasetId">
          <el-select
            v-model="createForm.datasetId"
            filterable
            remote
            clearable
            placeholder="搜索已生成题目的测评集"
            :remote-method="searchDatasets"
            :loading="datasetLoading"
            style="width: 100%"
            @change="onDatasetChange"
          >
            <el-option
              v-for="item in datasetOptions"
              :key="item.datasetId"
              :label="datasetLabel(item)"
              :value="item.datasetId"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="向量化任务" prop="embeddingTaskId">
          <el-select
            v-model="createForm.embeddingTaskId"
            filterable
            remote
            clearable
            automatic-dropdown
            placeholder="搜索同一文档的向量化任务"
            no-data-text="没有可绑定的向量化任务"
            popper-class="eval-task-select-popper"
            :remote-method="searchEmbeddingTasks"
            :loading="embeddingLoading"
            style="width: 100%"
          >
            <el-option
              v-for="item in embeddingOptions"
              :key="item.taskId"
              :label="embeddingLabel(item)"
              :value="item.taskId"
              :disabled="!isBindableEmbedding(item)"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button type="primary" :loading="submitLoading" @click="submitCreate">确 定</el-button>
        <el-button @click="createOpen = false">取 消</el-button>
      </template>
    </el-dialog>

    <el-dialog title="更换测评集" v-model="swapOpen" width="640px" append-to-body>
      <el-form ref="swapRef" :model="swapForm" :rules="swapRules" label-width="110px">
        <el-form-item label="任务">
          <span>{{ swapTask.name || swapTask.evalTaskId }}</span>
        </el-form-item>
        <el-form-item label="测评集" prop="datasetId">
          <el-select
            v-model="swapForm.datasetId"
            filterable
            remote
            placeholder="搜索同一文档下已生成题目的测评集"
            :remote-method="searchSwapDatasets"
            :loading="swapDatasetLoading"
            style="width: 100%"
          >
            <el-option
              v-for="item in swapDatasetOptions"
              :key="item.datasetId"
              :label="datasetLabel(item)"
              :value="item.datasetId"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button type="primary" :loading="swapSubmitLoading" @click="submitSwap">确 定</el-button>
        <el-button @click="swapOpen = false">取 消</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="EvalTask">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listEmbeddingTasks } from '@/api/content/embedding'
import { listEvalDataset } from '@/api/knowledge/evalDataset'
import { addEvalTask, listEvalTask, publishEvalTask, startEvalRun, swapEvalTaskDataset } from '@/api/knowledge/evalTask'

const { proxy } = getCurrentInstance()
const router = useRouter()

const loading = ref(false)
const showSearch = ref(true)
const taskList = ref([])
const total = ref(0)
const queryParams = ref({ pageNum: 1, pageSize: 10, name: undefined, status: undefined })

const createOpen = ref(false)
const submitLoading = ref(false)
const datasetLoading = ref(false)
const embeddingLoading = ref(false)
const datasetOptions = ref([])
const embeddingOptions = ref([])
const createForm = ref({ name: '', datasetId: undefined, embeddingTaskId: undefined })
const createRules = {
  name: [{
    required: true,
    trigger: 'blur',
    validator: (_rule, value, callback) => {
      if (!value || !String(value).trim()) {
        callback(new Error('请填写名称'))
        return
      }
      callback()
    }
  }],
  datasetId: [{ required: true, message: '请选择测评集', trigger: 'change' }],
  embeddingTaskId: [{ required: true, message: '请选择向量化任务', trigger: 'change' }]
}

const swapOpen = ref(false)
const swapSubmitLoading = ref(false)
const swapDatasetLoading = ref(false)
const swapDatasetOptions = ref([])
const swapTask = ref({})
const swapForm = ref({ datasetId: undefined })
const swapRules = {
  datasetId: [{
    required: true,
    trigger: 'change',
    validator: (_rule, value, callback) => {
      if (value == null || value === '') {
        callback(new Error('请选择测评集'))
        return
      }
      if (Number(value) === Number(swapTask.value.datasetId)) {
        callback(new Error('请选择另一个测评集'))
        return
      }
      callback()
    }
  }]
}

function getList() {
  loading.value = true
  listEvalTask(queryParams.value).then((response) => {
    taskList.value = response.rows || []
    total.value = response.total || 0
  }).finally(() => {
    loading.value = false
  })
}

function handleQuery() {
  queryParams.value.pageNum = 1
  getList()
}

function resetQuery() {
  proxy.resetForm('queryRef')
  handleQuery()
}

function datasetLabel(item) {
  return `${item.name || '未命名'}（ID ${item.datasetId}，文档 ${item.docId}）`
}

function isBindableEmbedding(item) {
  return String(item.status || '').toUpperCase() === 'COMPLETED'
    && String(item.releaseTag || '').toLowerCase() === 'canary'
}

function embeddingLabel(item) {
  const title = item.docTitle || '未命名文档'
  const base = `${title}（任务 ${item.taskId}`
  if (isBindableEmbedding(item)) {
    return `${base}，待发布）`
  }
  const tag = String(item.releaseTag || '').toLowerCase()
  if (String(item.status || '').toUpperCase() !== 'COMPLETED') {
    return `${base}，未完成）`
  }
  if (tag && tag !== 'canary') {
    return `${base}，已发布）`
  }
  return `${base}）`
}

function selectedDataset() {
  return datasetOptions.value.find((item) => item.datasetId === createForm.value.datasetId)
}

function searchDatasets(keyword) {
  datasetLoading.value = true
  const params = { pageNum: 1, pageSize: 20, status: 'READY' }
  const text = (keyword || '').trim()
  if (text) {
    params.name = text
  }
  listEvalDataset(params).then((response) => {
    const rows = response.rows || []
    const selected = datasetOptions.value.find((item) => item.datasetId === createForm.value.datasetId)
    if (selected && !rows.some((item) => item.datasetId === selected.datasetId)) {
      rows.unshift(selected)
    }
    datasetOptions.value = rows
  }).finally(() => {
    datasetLoading.value = false
  })
}

function searchEmbeddingTasks(keyword) {
  embeddingLoading.value = true
  const params = { pageNum: 1, pageSize: 50, status: 'COMPLETED' }
  const dataset = selectedDataset()
  if (dataset?.docId != null) {
    params.docId = dataset.docId
  }
  const text = (keyword || '').trim()
  if (text && !/^\d+$/.test(text)) {
    params.docTitle = text
  }
  listEmbeddingTasks(params).then((response) => {
    let rows = response.rows || []
    if (text && /^\d+$/.test(text)) {
      rows = rows.filter((item) => String(item.taskId).includes(text))
    }
    const selected = embeddingOptions.value.find((item) => item.taskId === createForm.value.embeddingTaskId)
    if (selected && !rows.some((item) => item.taskId === selected.taskId)) {
      rows.unshift(selected)
    }
    embeddingOptions.value = rows
  }).finally(() => {
    embeddingLoading.value = false
  })
}

function onDatasetChange() {
  createForm.value.embeddingTaskId = undefined
  searchEmbeddingTasks('')
}

function handleAdd() {
  createForm.value = { name: '', datasetId: undefined, embeddingTaskId: undefined }
  datasetOptions.value = []
  embeddingOptions.value = []
  createOpen.value = true
  searchDatasets('')
  searchEmbeddingTasks('')
}

function submitCreate() {
  proxy.$refs.createRef.validate((valid) => {
    if (!valid) return
    submitLoading.value = true
    addEvalTask({
      name: createForm.value.name.trim(),
      datasetId: Number(createForm.value.datasetId),
      embeddingTaskId: Number(createForm.value.embeddingTaskId)
    }).then(() => {
      proxy.$modal.msgSuccess('创建成功')
      createOpen.value = false
      getList()
    }).finally(() => {
      submitLoading.value = false
    })
  })
}

function searchSwapDatasets(keyword) {
  swapDatasetLoading.value = true
  const params = { pageNum: 1, pageSize: 20, status: 'READY', docId: swapTask.value.docId }
  const text = (keyword || '').trim()
  if (text) {
    params.name = text
  }
  listEvalDataset(params).then((response) => {
    const rows = response.rows || []
    const selected = swapDatasetOptions.value.find((item) => item.datasetId === swapForm.value.datasetId)
    if (selected && !rows.some((item) => item.datasetId === selected.datasetId)) {
      rows.unshift(selected)
    }
    swapDatasetOptions.value = rows
  }).finally(() => {
    swapDatasetLoading.value = false
  })
}

function handleSwap(row) {
  swapTask.value = row
  swapForm.value = { datasetId: row.datasetId }
  swapDatasetOptions.value = row.datasetId == null ? [] : [{
    datasetId: row.datasetId,
    name: row.datasetName,
    docId: row.docId
  }]
  swapOpen.value = true
  searchSwapDatasets('')
}

function submitSwap() {
  proxy.$refs.swapRef.validate((valid) => {
    if (!valid) return
    swapSubmitLoading.value = true
    swapEvalTaskDataset(swapTask.value.evalTaskId, {
      datasetId: Number(swapForm.value.datasetId)
    }).then(() => {
      proxy.$modal.msgSuccess('已更换测评集')
      swapOpen.value = false
      getList()
    }).finally(() => {
      swapSubmitLoading.value = false
    })
  })
}

function handleRun(row) {
  startEvalRun(row.evalTaskId).then((response) => {
    proxy.$modal.msgSuccess(response.msg || '评测已启动')
  })
}

function handlePublish(row) {
  proxy.$modal.confirm('确认发布该向量化任务并归档？').then(() => publishEvalTask(row.evalTaskId)).then(() => {
    proxy.$modal.msgSuccess('发布成功')
    getList()
  }).catch(() => {})
}

function openRuns(row) {
  router.push({
    path: `/knowledge/eval-task-run/index/${row.evalTaskId}`,
    query: { name: row.name || '' }
  })
}

onMounted(getList)
</script>

<style>
.eval-task-select-popper {
  z-index: 5000 !important;
}

.eval-bind-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 20px;
}

.eval-bind-id {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 18px;
}
</style>
