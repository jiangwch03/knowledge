<template>
  <div class="everyday-panel">
    <el-form :model="queryParams" ref="queryRef" :inline="true">
      <el-form-item label="日常词" prop="word">
        <el-input v-model="queryParams.word" placeholder="输入词搜索" clearable style="width: 220px" @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="语种" prop="lang">
        <el-select v-model="queryParams.lang" clearable placeholder="全部" style="width: 120px" @change="handleQuery">
          <el-option v-for="item in langOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="词类" prop="wordClass">
        <el-select v-model="queryParams.wordClass" clearable placeholder="全部" style="width: 140px" @change="handleQuery">
          <el-option v-for="item in classOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="来源" prop="source">
        <el-select v-model="queryParams.source" clearable placeholder="全部" style="width: 140px" @change="handleQuery">
          <el-option v-for="item in sourceOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button type="primary" plain icon="Plus" @click="handleAdd" v-hasPermi="['rag:everyday:add']">新增</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button type="warning" plain icon="Refresh" :loading="initLoading" @click="handleInit" v-hasPermi="['rag:everyday:init']">初始化</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="danger"
          plain
          icon="Delete"
          :disabled="selectedIds.length === 0"
          @click="handleRemove()"
          v-hasPermi="['rag:everyday:remove']"
        >剔除</el-button>
      </el-col>
    </el-row>

    <el-table v-loading="loading" :data="wordList" @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="50" align="center" />
      <el-table-column label="日常词" prop="word" min-width="200" show-overflow-tooltip />
      <el-table-column label="语种" prop="lang" width="100" align="center">
        <template #default="{ row }">{{ langLabel(row.lang) }}</template>
      </el-table-column>
      <el-table-column label="词类" prop="wordClass" width="120" align="center">
        <template #default="{ row }">{{ classLabel(row.wordClass) }}</template>
      </el-table-column>
      <el-table-column label="来源" prop="source" width="120" align="center">
        <template #default="{ row }">{{ sourceLabel(row.source) }}</template>
      </el-table-column>
      <el-table-column label="更新时间" prop="updateTime" width="180" align="center">
        <template #default="{ row }"><span>{{ parseTime(row.updateTime) }}</span></template>
      </el-table-column>
      <el-table-column label="操作" align="center" width="120">
        <template #default="{ row }">
          <el-button link type="danger" @click="handleRemove(row)" v-hasPermi="['rag:everyday:remove']">剔除</el-button>
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

    <el-dialog title="新增日常词" v-model="addOpen" width="480px" append-to-body>
      <el-form ref="addRef" :model="addForm" :rules="addRules" label-width="80px" @submit.prevent>
        <el-form-item label="日常词" prop="word">
          <el-input v-model="addForm.word" maxlength="64" placeholder="输入一个词" @keyup.enter="submitAdd" />
          <div class="add-hint">语种和词类会自动填上，来源记成手工录入。加上之后，下次抽词会把这个词丢掉。</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button type="primary" :loading="addLoading" @click="submitAdd">确 定</el-button>
        <el-button @click="addOpen = false">取 消</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="EverydayWord">
import { addEverydayWord, initEverydayWord, listEverydayWord, removeEverydayWord } from '@/api/content/everyday'

const { proxy } = getCurrentInstance()

const langOptions = [
  { value: 'zh', label: '中文' },
  { value: 'en', label: '英文' }
]

const classOptions = [
  { value: 'noun', label: '名词' },
  { value: 'verb', label: '动词' },
  { value: 'adj', label: '形容词' },
  { value: 'function', label: '虚词' },
  { value: 'other', label: '其他' }
]

const sourceOptions = [
  { value: 'zh_idf', label: '中文词频表' },
  { value: 'en_common', label: '常用英语' },
  { value: 'manual', label: '手工录入' }
]

const loading = ref(false)
const wordList = ref([])
const total = ref(0)
const selectedIds = ref([])
const queryParams = ref({
  pageNum: 1,
  pageSize: 10,
  word: undefined,
  lang: undefined,
  wordClass: undefined,
  source: undefined
})
const addOpen = ref(false)
const addLoading = ref(false)
const initLoading = ref(false)
const addForm = ref({ word: '' })
const addRules = {
  word: [{ required: true, message: '请填写日常词', trigger: 'blur' }]
}

function langLabel(value) {
  return langOptions.find((item) => item.value === value)?.label || '中文'
}

function classLabel(value) {
  return classOptions.find((item) => item.value === value)?.label || '其他'
}

function sourceLabel(value) {
  return sourceOptions.find((item) => item.value === value)?.label || '手工录入'
}

function getList() {
  loading.value = true
  listEverydayWord(queryParams.value).then((response) => {
    wordList.value = response.rows || []
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

function handleSelectionChange(rows) {
  selectedIds.value = rows.map((row) => row.wordId)
}

function handleAdd() {
  addForm.value = { word: '' }
  addOpen.value = true
  nextTick(() => proxy.$refs.addRef?.clearValidate())
}

function submitAdd() {
  proxy.$refs.addRef.validate((valid) => {
    if (!valid) return
    addLoading.value = true
    addEverydayWord(addForm.value.word.trim()).then(() => {
      proxy.$modal.msgSuccess('已加入日常词')
      addOpen.value = false
      handleQuery()
    }).finally(() => {
      addLoading.value = false
    })
  })
}

function handleInit() {
  proxy.$modal.confirm('初始化会清空日常词表，再按程序里的中文词频表和常用英语重新入库。页面上新增、剔除过的词都会回到初始状态。确认继续？').then(() => {
    initLoading.value = true
    return initEverydayWord()
  }).then((response) => {
    if (!response) return
    proxy.$modal.msgSuccess(response.msg || '已重新入库')
    selectedIds.value = []
    handleQuery()
  }).catch(() => {}).finally(() => {
    initLoading.value = false
  })
}

function handleRemove(row) {
  const wordIds = row ? [row.wordId] : selectedIds.value
  const label = row ? `「${row.word}」` : `选中的 ${wordIds.length} 个词`
  proxy.$modal.confirm(`确认剔除${label}？剔除后不再当作日常词，下次抽词会把它们留下来。`).then(() => {
    return removeEverydayWord(wordIds)
  }).then(() => {
    proxy.$modal.msgSuccess('已剔除')
    selectedIds.value = []
    getList()
  }).catch(() => {})
}

getList()
</script>

<style scoped>
.add-hint {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.5;
}
</style>
