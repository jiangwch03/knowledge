<template>
  <div class="app-container">
    <el-tabs v-model="pageTab">
    <el-tab-pane label="主题" name="topic">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch">
      <el-form-item label="主题名称" prop="topicName">
        <el-input v-model="queryParams.topicName" placeholder="主题名称" clearable style="width: 200px" @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button type="primary" plain icon="Plus" @click="handleAdd" v-hasPermi="['rag:topic:add']">新建主题</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList" />
    </el-row>

    <el-table v-loading="loading" :data="topicList">
      <el-table-column label="ID" prop="topicId" width="90" align="center" />
      <el-table-column label="主题名称" prop="topicName" min-width="160" show-overflow-tooltip />
      <el-table-column label="描述" prop="description" min-width="180" show-overflow-tooltip />
      <el-table-column label="切分任务" min-width="240" show-overflow-tooltip>
        <template #default="{ row }">{{ taskLabel(row) }}</template>
      </el-table-column>
      <el-table-column label="状态" prop="status" width="110" align="center">
        <template #default="{ row }">
          <el-tooltip v-if="row.status === 'FAILED' && row.errorMessage" :content="row.errorMessage" placement="top">
            <el-tag type="danger" size="small">失败</el-tag>
          </el-tooltip>
          <el-tag v-else :type="statusTag(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="关键词数" prop="keywordCount" width="100" align="center" />
      <el-table-column label="创建时间" prop="createTime" width="170" align="center">
        <template #default="{ row }"><span>{{ parseTime(row.createTime) }}</span></template>
      </el-table-column>
      <el-table-column label="操作" align="center" width="280">
        <template #default="{ row }">
          <el-button link type="primary" @click="openKeywords(row)" v-hasPermi="['rag:topic:query']">关键词</el-button>
          <el-button link type="primary" @click="handleEdit(row)" v-hasPermi="['rag:topic:edit']" :disabled="row.status === 'GENERATING'">修改</el-button>
          <el-button v-if="row.status === 'FAILED'" link type="warning" icon="Refresh" @click="handleRetry(row)" v-hasPermi="['rag:topic:retry']">重试</el-button>
          <el-button link type="primary" @click="handleDelete(row)" v-hasPermi="['rag:topic:remove']">删除</el-button>
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

    <el-dialog :title="dialogTitle" v-model="formOpen" width="560px" append-to-body>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-form-item label="主题名称" prop="topicName">
          <el-input v-model="form.topicName" :disabled="isEdit" maxlength="64" placeholder="主题名称" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input
            v-model="form.description"
            type="textarea"
            maxlength="1000"
            show-word-limit
            :rows="4"
            placeholder="关键词没命中时，这段描述会交给主题模型判断"
          />
        </el-form-item>
        <el-form-item label="切分任务" prop="taskId">
          <el-select
            v-model="form.taskId"
            filterable
            remote
            clearable
            placeholder="选择已完成的切分任务"
            :remote-method="searchTasks"
            :loading="taskLoading"
            style="width: 100%"
          >
            <el-option v-for="item in taskOptions" :key="item.taskId" :label="taskLabel(item)" :value="item.taskId" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="isEdit" label="旧关键词" prop="keepKeywords">
          <el-radio-group v-model="form.keepKeywords">
            <el-radio :value="true">保留</el-radio>
            <el-radio :value="false">清理</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button type="primary" :loading="submitLoading" @click="submitForm">确 定</el-button>
        <el-button @click="formOpen = false">取 消</el-button>
      </template>
    </el-dialog>

    <el-dialog title="关键词" v-model="keywordOpen" width="640px" append-to-body>
      <div v-loading="keywordLoading" class="keyword-box">
        <el-empty v-if="!keywordLoading && keywordList.length === 0" description="暂无关键词" />
        <el-tag v-for="item in keywordList" :key="item.keyword" class="keyword-tag" type="info">
          {{ item.keyword }}
        </el-tag>
      </div>
    </el-dialog>
    </el-tab-pane>
    <el-tab-pane v-if="canEveryday" label="日常词" name="everyday" lazy>
      <everyday-word />
    </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup name="RetrieveTopic">
import { onBeforeUnmount } from 'vue'
import auth from '@/plugins/auth'
import { listEmbeddingTasks } from '@/api/content/embedding'
import { addTopic, deleteTopic, getTopic, listTopic, retryTopic, updateTopic } from '@/api/content/topic'
import EverydayWord from '../everyday/index.vue'

const { proxy } = getCurrentInstance()
const pageTab = ref('topic')
const canEveryday = auth.hasPermi('rag:everyday:list')

const loading = ref(false)
const showSearch = ref(true)
const topicList = ref([])
const total = ref(0)
const queryParams = ref({ pageNum: 1, pageSize: 10, topicName: undefined })
let pollTimer = null

const formOpen = ref(false)
const isEdit = ref(false)
const submitLoading = ref(false)
const form = ref(emptyForm())
const taskOptions = ref([])
const taskLoading = ref(false)
const rules = {
  topicName: [{ required: true, message: '请填写主题名称', trigger: 'blur' }],
  taskId: [{ required: true, message: '请选择切分任务', trigger: 'change' }],
  keepKeywords: [{ required: true, message: '请选择旧关键词是清理还是保留', trigger: 'change' }]
}

const keywordOpen = ref(false)
const keywordLoading = ref(false)
const keywordList = ref([])

const dialogTitle = computed(() => (isEdit.value ? '修改主题' : '新建主题'))

function emptyForm() {
  return { topicId: undefined, topicName: '', description: '', taskId: undefined, keepKeywords: undefined }
}

function taskLabel(item) {
  const title = item.docTitle || '未命名文档'
  return `${title}（任务 ${item.taskId}）`
}

function statusLabel(status) {
  if (status === 'GENERATING') return '生成中'
  if (status === 'FAILED') return '失败'
  return '已完成'
}

function statusTag(status) {
  if (status === 'GENERATING') return 'warning'
  if (status === 'FAILED') return 'danger'
  return 'success'
}

function schedulePoll() {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
  if (topicList.value.some((row) => row.status === 'GENERATING')) {
    pollTimer = setTimeout(() => getList(true), 3000)
  }
}

function getList(silent = false) {
  if (!silent) {
    loading.value = true
  }
  listTopic(queryParams.value).then((response) => {
    topicList.value = response.rows || []
    total.value = response.total || 0
  }).finally(() => {
    loading.value = false
    schedulePoll()
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

function searchTasks(keyword) {
  taskLoading.value = true
  const params = { pageNum: 1, pageSize: 50, status: 'COMPLETED' }
  const text = (keyword || '').trim()
  if (text && !/^\d+$/.test(text)) {
    params.docTitle = text
  }
  listEmbeddingTasks(params).then((response) => {
    let rows = response.rows || []
    if (text && /^\d+$/.test(text)) {
      rows = rows.filter((item) => String(item.taskId).includes(text))
    }
    const selected = taskOptions.value.find((item) => item.taskId === form.value.taskId)
    if (selected && !rows.some((item) => item.taskId === selected.taskId)) {
      rows.unshift(selected)
    }
    taskOptions.value = rows
  }).finally(() => {
    taskLoading.value = false
  })
}

function handleAdd() {
  isEdit.value = false
  form.value = emptyForm()
  formOpen.value = true
  searchTasks('')
}

function handleEdit(row) {
  isEdit.value = true
  form.value = {
    topicId: row.topicId,
    topicName: row.topicName,
    description: row.description || '',
    taskId: row.taskId,
    keepKeywords: undefined
  }
  taskOptions.value = [{ taskId: row.taskId, docTitle: row.docTitle }]
  formOpen.value = true
  searchTasks('')
}

function submitForm() {
  proxy.$refs.formRef.validate((valid) => {
    if (!valid) {
      return
    }
    submitLoading.value = true
    const request = isEdit.value
      ? updateTopic(form.value.topicId, {
          taskId: form.value.taskId,
          description: form.value.description,
          keepKeywords: form.value.keepKeywords
        })
      : addTopic({
          topicName: form.value.topicName,
          description: form.value.description,
          taskId: form.value.taskId
        })
    request.then(() => {
    proxy.$modal.msgSuccess(isEdit.value ? '已开始重新生成关键词' : '已开始生成关键词')
      formOpen.value = false
      getList()
    }).finally(() => {
      submitLoading.value = false
    })
  })
}

function handleRetry(row) {
  proxy.$modal.confirm(`确认重试主题「${row.topicName}」？将按上次的切分任务和关键词选项重新生成。`).then(() => retryTopic(row.topicId)).then(() => {
    proxy.$modal.msgSuccess('已开始重新生成关键词')
    getList()
  }).catch(() => {})
}

function handleDelete(row) {
  proxy.$modal.confirm(`确认删除主题「${row.topicName}」？`).then(() => deleteTopic(row.topicId)).then(() => {
    proxy.$modal.msgSuccess('删除成功')
    getList()
  }).catch(() => {})
}

function openKeywords(row) {
  keywordOpen.value = true
  keywordLoading.value = true
  keywordList.value = []
  getTopic(row.topicId).then((response) => {
    keywordList.value = response.data?.keywords || []
  }).finally(() => {
    keywordLoading.value = false
  })
}

getList()

onBeforeUnmount(() => {
  if (pollTimer) {
    clearTimeout(pollTimer)
  }
})
</script>

<style scoped>
.keyword-box {
  max-height: 420px;
  overflow: auto;
}

.keyword-tag {
  margin: 0 8px 8px 0;
}
</style>
