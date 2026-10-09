<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch">
      <el-form-item label="名称" prop="name">
        <el-input v-model="queryParams.name" placeholder="测评集名称" clearable style="width: 180px" @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="文档 ID" prop="docId">
        <el-input v-model="queryParams.docId" placeholder="文档 ID" clearable style="width: 140px" @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="状态" prop="status">
        <el-select v-model="queryParams.status" placeholder="全部" clearable style="width: 160px">
          <el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button type="primary" plain icon="Plus" @click="handleAdd" v-hasPermi="['rag:eval:dataset:create']">创建测评集</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList" />
    </el-row>

    <el-table v-loading="loading" :data="datasetList">
      <el-table-column label="ID" prop="datasetId" width="90" align="center" />
      <el-table-column label="名称" prop="name" min-width="160" show-overflow-tooltip />
      <el-table-column label="文档 ID" prop="docId" width="100" align="center" />
      <el-table-column label="状态" prop="status" width="140" align="center">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row)" size="small">{{ statusLabel(row) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="题目数" width="110" align="center">
        <template #default="{ row }">{{ row.itemCount ?? 0 }} / {{ row.questionCount ?? 0 }}</template>
      </el-table-column>
      <el-table-column label="创建人" prop="createBy" width="110" show-overflow-tooltip />
      <el-table-column label="创建时间" prop="createTime" width="170" align="center">
        <template #default="{ row }"><span>{{ parseTime(row.createTime) }}</span></template>
      </el-table-column>
      <el-table-column label="备注" prop="remark" min-width="160" show-overflow-tooltip />
      <el-table-column label="操作" align="center" width="120">
        <template #default="{ row }">
          <el-button link type="primary" icon="View" @click="openItems(row)" v-hasPermi="['rag:eval:dataset:query']">题目</el-button>
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

    <el-dialog title="创建测评集" v-model="createOpen" width="520px" append-to-body>
      <el-form ref="createRef" :model="createForm" :rules="createRules" label-width="110px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="createForm.name" placeholder="测评集名称" maxlength="128" />
        </el-form-item>
        <el-form-item label="文档" prop="docId">
          <el-select
            v-model="createForm.docId"
            filterable
            remote
            clearable
            placeholder="选择已完成向量化、分段仍在的文档"
            :remote-method="searchDocuments"
            :loading="docLoading"
            style="width: 100%"
          >
            <el-option
              v-for="item in docOptions"
              :key="item.docId"
              :label="documentLabel(item)"
              :value="item.docId"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="题目数量" prop="questionCount">
          <el-input-number v-model="createForm.questionCount" :min="50" :max="200" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="createForm.description" type="textarea" :rows="3" maxlength="500" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button type="primary" :loading="submitLoading" @click="submitCreate">确 定</el-button>
        <el-button @click="createOpen = false">取 消</el-button>
      </template>
    </el-dialog>

  </div>
</template>

<script setup name="EvalDataset">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listDocumentOptions } from '@/api/content/document'
import { addEvalDataset, listEvalDataset } from '@/api/knowledge/evalDataset'

const { proxy } = getCurrentInstance()
const router = useRouter()

const statusOptions = [
  { value: 'INIT', label: '初始化' },
  { value: 'MATERIAL_DONE', label: '圈资料完成' },
  { value: 'SIMPLE_DONE', label: '简单题完成' },
  { value: 'MULTI_DONE', label: '多跳题完成' },
  { value: 'READY', label: '可测评' },
  { value: 'MATERIAL_FAILED', label: '圈资料失败' },
  { value: 'SIMPLE_FAILED', label: '简单题失败' },
  { value: 'MULTI_FAILED', label: '多跳题失败' },
  { value: 'CUSTOM_FAILED', label: '自写题失败' }
]

const loading = ref(false)
const showSearch = ref(true)
const datasetList = ref([])
const total = ref(0)
const queryParams = ref({ pageNum: 1, pageSize: 10, name: undefined, docId: undefined, status: undefined })

const createOpen = ref(false)
const submitLoading = ref(false)
const createForm = ref({ name: '', docId: undefined, questionCount: 50, description: '' })
const docOptions = ref([])
const docLoading = ref(false)
const createRules = {
  name: [{ required: true, message: '请填写名称', trigger: 'blur' }],
  docId: [{ required: true, message: '请选择文档', trigger: 'change' }],
  questionCount: [{ required: true, message: '请填写题目数量', trigger: 'change' }]
}

let pollTimer = null

const activeStatuses = new Set([
  'INIT',
  'MATERIAL_DONE',
  'SIMPLE_DONE',
  'MULTI_DONE',
  'MATERIAL_FAILED',
  'SIMPLE_FAILED',
  'MULTI_FAILED',
  'CUSTOM_FAILED'
])

function statusLabel(row) {
  return statusOptions.find((item) => item.value === row.status)?.label || row.status || '-'
}

function statusTagType(row) {
  if (row.status === 'READY') {
    return 'success'
  }
  if (String(row.status || '').endsWith('FAILED')) {
    return 'danger'
  }
  if (String(row.status || '').endsWith('DONE')) {
    return 'warning'
  }
  return 'info'
}

function getList() {
  loading.value = true
  const params = { ...queryParams.value }
  if (params.docId === '' || params.docId == null) {
    delete params.docId
  }
  listEvalDataset(params).then((response) => {
    datasetList.value = response.rows || []
    total.value = response.total || 0
  }).finally(() => {
    loading.value = false
    syncPolling()
  })
}

function syncPolling() {
  const generating = datasetList.value.some((row) => activeStatuses.has(row.status))
  if (generating && !pollTimer) {
    pollTimer = setInterval(getList, 5000)
  }
  if (!generating && pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function handleQuery() {
  queryParams.value.pageNum = 1
  getList()
}

function resetQuery() {
  proxy.resetForm('queryRef')
  handleQuery()
}

function documentLabel(item) {
  return item.docTitle
}

function searchDocuments(keyword) {
  docLoading.value = true
  listDocumentOptions(keyword || undefined).then((response) => {
    docOptions.value = response.data || []
  }).finally(() => {
    docLoading.value = false
  })
}

function handleAdd() {
  createForm.value = { name: '', docId: undefined, questionCount: 50, description: '' }
  createOpen.value = true
  searchDocuments('')
}

function submitCreate() {
  proxy.$refs.createRef.validate((valid) => {
    if (!valid) return
    submitLoading.value = true
    addEvalDataset({
      name: createForm.value.name,
      docId: createForm.value.docId,
      questionCount: createForm.value.questionCount,
      description: createForm.value.description || undefined
    }).then(() => {
      proxy.$modal.msgSuccess('创建成功，正在出题')
      createOpen.value = false
      getList()
    }).finally(() => {
      submitLoading.value = false
    })
  })
}

function openItems(row) {
  router.push({
    path: `/knowledge/eval-dataset-item/index/${row.datasetId}`,
    query: { name: row.name || '' }
  })
}

onMounted(getList)
onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>
