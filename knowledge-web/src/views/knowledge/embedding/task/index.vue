<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch">
      <el-form-item label="任务状态" prop="status">
        <el-select v-model="queryParams.status" placeholder="请选择状态" clearable style="width: 160px">
          <el-option
            v-for="item in statusOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="来源" prop="sourceType">
        <el-select v-model="queryParams.sourceType" placeholder="请选择来源" clearable style="width: 140px">
          <el-option label="资料上传" value="0" />
          <el-option label="网页爬取" value="1" />
        </el-select>
      </el-form-item>
      <el-form-item label="文档 ID" prop="docId">
        <el-input
          v-model="queryParams.docId"
          placeholder="请输入文档 ID"
          clearable
          style="width: 140px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="文档标题" prop="docTitle">
        <el-input
          v-model="queryParams.docTitle"
          placeholder="请输入文档标题"
          clearable
          style="width: 200px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="创建时间" style="width: 308px">
        <el-date-picker
          v-model="dateRange"
          value-format="YYYY-MM-DD HH:mm:ss"
          type="daterange"
          range-separator="-"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          :default-time="[new Date(2000, 1, 1, 0, 0, 0), new Date(2000, 1, 1, 23, 59, 59)]"
        />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8">
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList" />
    </el-row>

    <el-table v-loading="loading" :data="taskList">
      <el-table-column label="任务 ID" prop="taskId" width="100" align="center" />
      <el-table-column label="文档标题" prop="docTitle" min-width="160" show-overflow-tooltip />
      <el-table-column label="来源" prop="sourceType" width="100" align="center">
        <template #default="{ row }">
          {{ sourceTypeLabel(row.sourceType) }}
        </template>
      </el-table-column>
      <el-table-column label="切分策略" prop="splitType" width="110" align="center">
        <template #default="{ row }">
          {{ splitTypeLabel(row.splitType) }}
        </template>
      </el-table-column>
      <el-table-column label="运行状态" prop="status" width="110" align="center">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="发布标签" prop="releaseTag" width="110" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.releaseTag || isArchivedRelease(row)" :type="releaseTagType(row.releaseTag, row)" size="small">
            {{ releaseTagLabel(row.releaseTag, row) }}
          </el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="进度" width="120" align="center">
        <template #default="{ row }">
          {{ row.embeddedCount ?? 0 }} / {{ row.chunkCount ?? 0 }}
        </template>
      </el-table-column>
      <el-table-column label="创建人" prop="createBy" width="110" show-overflow-tooltip />
      <el-table-column label="创建时间" prop="createTime" width="160" align="center">
        <template #default="{ row }">
          <span>{{ parseTime(row.createTime) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="更新时间" prop="updateTime" width="160" align="center">
        <template #default="{ row }">
          <span>{{ parseTime(row.updateTime) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="错误信息" prop="errorMessage" min-width="160" show-overflow-tooltip />
      <el-table-column label="操作" align="center" width="280" class-name="small-padding fixed-width">
        <template #default="{ row }">
          <el-button
            link
            type="primary"
            icon="View"
            @click="openDetail(row)"
            v-hasPermi="['rag:embedding:query']"
          >详情</el-button>
          <el-button
            link
            type="primary"
            icon="List"
            :disabled="!canViewSegments(row)"
            @click="openSegments(row)"
            v-hasPermi="['rag:embedding:query']"
          >切分效果</el-button>
          <el-button
            v-if="isFailedStatus(row.status)"
            link
            type="warning"
            icon="Refresh"
            @click="handleRetry(row)"
            v-hasPermi="['rag:embedding:retry']"
          >重试</el-button>
          <el-button
            v-if="canDelete(row)"
            link
            type="danger"
            icon="Delete"
            @click="handleDelete(row)"
            v-hasPermi="['rag:embedding:remove']"
          >删除</el-button>
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

    <!-- 任务详情弹框 -->
    <el-dialog v-model="detailOpen" title="Embedding 任务详情" width="520px" append-to-body>
      <el-descriptions v-if="detailData" :column="2" border label-width="90px" v-loading="detailLoading">
        <el-descriptions-item label="任务 ID">{{ detailData.taskId }}</el-descriptions-item>
        <el-descriptions-item label="文档 ID">{{ detailData.docId }}</el-descriptions-item>
        <el-descriptions-item label="文档标题" :span="2">{{ detailData.docTitle || "-" }}</el-descriptions-item>
        <el-descriptions-item label="来源">{{ sourceTypeLabel(detailData.sourceType) }}</el-descriptions-item>
        <el-descriptions-item label="切分策略">{{ splitTypeLabel(detailData.splitType) }}</el-descriptions-item>
        <el-descriptions-item label="运行状态">
          <el-tag :type="statusTagType(detailData.status)" size="small">{{ statusLabel(detailData.status) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="发布标签">
          <el-tag
            v-if="detailData.releaseTag || isArchivedRelease(detailData)"
            :type="releaseTagType(detailData.releaseTag, detailData)"
            size="small"
          >
            {{ releaseTagLabel(detailData.releaseTag, detailData) }}
          </el-tag>
          <span v-else>-</span>
        </el-descriptions-item>
        <el-descriptions-item label="进度">
          {{ detailData.embeddedCount ?? 0 }} / {{ detailData.chunkCount ?? 0 }}
        </el-descriptions-item>
        <el-descriptions-item label="模型">{{ detailData.embeddingModelCode || "-" }}</el-descriptions-item>
        <el-descriptions-item label="维度">{{ detailData.dimensions ?? "-" }}</el-descriptions-item>
        <el-descriptions-item label="创建人">{{ detailData.createBy || "-" }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ parseTime(detailData.createTime) }}</el-descriptions-item>
        <el-descriptions-item label="更新时间">{{ parseTime(detailData.updateTime) }}</el-descriptions-item>
        <el-descriptions-item label="切分参数" :span="2">
          <pre class="json-block">{{ formatSplitParams(detailData.splitParams) }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="错误信息" :span="2">
          <span class="error-text">{{ detailData.errorMessage || "-" }}</span>
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>

    <!-- 切分效果弹框 -->
    <el-dialog
      v-model="segmentOpen"
      :title="segmentTitle"
      width="1100px"
      top="5vh"
      append-to-body
      @closed="resetSegments"
    >
      <div class="segment-toolbar">
        <el-select v-model="segmentQuery.skipEmbedding" placeholder="是否需要向量化" clearable size="small" style="width: 160px" @change="loadSegments">
          <el-option label="需要向量化" :value="0" />
          <el-option label="不需要（父片）" :value="1" />
        </el-select>
      </div>
      <el-table v-loading="segmentLoading" :data="segmentList" stripe max-height="560">
        <el-table-column label="序号" prop="chunkOrder" width="70" align="center" />
        <el-table-column label="文本摘要" min-width="260" show-overflow-tooltip>
          <template #default="{ row }">
            {{ textPreview(row.text) }}
          </template>
        </el-table-column>
        <el-table-column label="长度" width="80" align="center">
          <template #default="{ row }">
            {{ row.text ? row.text.length : 0 }}
          </template>
        </el-table-column>
        <el-table-column label="分片角色" width="128" align="center">
          <template #default="{ row }">
            <el-tag :type="segmentRoleType(row)" size="small" :title="segmentRoleTip(row)">
              {{ segmentRoleLabel(row) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="需要向量化" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.skipEmbedding === 1 ? 'info' : 'success'" size="small">
              {{ row.skipEmbedding === 1 ? "否" : "是" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="入向量库" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="isVectorStored(row) ? 'success' : 'info'" size="small">
              {{ isVectorStored(row) ? "是" : "否" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="发布标签" prop="releaseTag" width="100" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.releaseTag" :type="releaseTagType(row.releaseTag)" size="small">
              {{ releaseTagLabel(row.releaseTag) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="元数据" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            {{ formatMetadata(row.metadata) }}
          </template>
        </el-table-column>
      </el-table>
      <pagination
        v-show="segmentTotal > 0"
        :total="segmentTotal"
        v-model:page="segmentQuery.pageNum"
        v-model:limit="segmentQuery.pageSize"
        @pagination="loadSegments"
      />
    </el-dialog>
  </div>
</template>

<script setup name="EmbeddingTask">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import {
  deleteEmbeddingTask,
  getEmbeddingStrategies,
  getEmbeddingTask,
  listEmbeddingSegments,
  listEmbeddingTasks,
  retryEmbeddingTask,
} from "@/api/content/embedding";

const { proxy } = getCurrentInstance();
const route = useRoute();

const loading = ref(false);
const showSearch = ref(true);
const taskList = ref([]);
const total = ref(0);
const dateRange = ref([]);
const queryParams = ref({
  pageNum: 1,
  pageSize: 10,
  status: undefined,
  sourceType: undefined,
  docId: undefined,
  docTitle: undefined,
});

const statusOptions = [
  { value: "PENDING", label: "等待中" },
  { value: "CHUNKING", label: "切分中" },
  { value: "EMBEDDING", label: "向量化中" },
  { value: "COMPLETED", label: "已完成" },
  { value: "CHUNK_FAILED", label: "切分失败" },
  { value: "EMBED_FAILED", label: "向量化失败" },
];

const FAILED_STATUSES = ["CHUNK_FAILED", "EMBED_FAILED"];
const IN_PROGRESS = ["PENDING", "CHUNKING", "EMBEDDING"];

/** code -> name，来自 /embedding/strategies（与配置页同源） */
const splitTypeMap = ref({});
let pollTimer = null;

const detailOpen = ref(false);
const detailLoading = ref(false);
const detailData = ref(null);

const segmentOpen = ref(false);
const segmentLoading = ref(false);
const segmentList = ref([]);
const segmentTotal = ref(0);
const currentSegmentTask = ref(null);
const segmentQuery = ref({
  pageNum: 1,
  pageSize: 10,
  skipEmbedding: undefined,
});

const segmentTitle = computed(() => {
  if (!currentSegmentTask.value) return "切分效果";
  return `切分效果 - 任务 #${currentSegmentTask.value.taskId}`;
});

const hasInProgressTasks = computed(() =>
  taskList.value.some((row) => IN_PROGRESS.includes(row.status))
);

function sourceTypeLabel(value) {
  if (value === "0" || value === 0) return "资料上传";
  if (value === "1" || value === 1) return "网页爬取";
  return value || "-";
}

function splitTypeLabel(code) {
  return splitTypeMap.value[code] || code || "-";
}

function statusLabel(status) {
  return statusOptions.find((o) => o.value === status)?.label || status || "-";
}

function statusTagType(status) {
  const map = {
    PENDING: "info",
    CHUNKING: "warning",
    EMBEDDING: "warning",
    COMPLETED: "success",
    CHUNK_FAILED: "danger",
    EMBED_FAILED: "danger",
  };
  return map[status] || "info";
}

function isFailedStatus(status) {
  return FAILED_STATUSES.includes(status);
}

/** 已完成且无 segment（分片已归档清理）→ 展示「已归档」 */
function isArchivedRelease(row) {
  return row?.status === "COMPLETED" && !row?.releaseTag;
}

function releaseTagLabel(tag, row) {
  if (isArchivedRelease(row)) return "已归档";
  const map = { canary: "灰度", prod: "发布", pending_delete: "待删除" };
  return map[tag] || tag || "-";
}

function releaseTagType(tag, row) {
  if (isArchivedRelease(row)) return "info";
  const map = { canary: "warning", prod: "success", pending_delete: "info" };
  return map[tag] || "info";
}

function canViewSegments(row) {
  return row.status !== "PENDING" && (row.chunkCount ?? 0) > 0;
}

/** 已发布 prod、已归档不可删；进行中 / 失败 / 未发布 canary 可删 */
function canDelete(row) {
  if (row.releaseTag === "prod") return false;
  if (isArchivedRelease(row)) return false;
  return true;
}

/** 超长段会保留父片全文（不入向量库），再切子片入向量库；普通段直接入向量库 */
function isSkipEmbedding(row) {
  return row?.skipEmbedding === true || row?.skipEmbedding === 1;
}

/** 是否已成功写入向量库（status=VECTOR_STORED） */
function isVectorStored(row) {
  return row?.status === "VECTOR_STORED";
}

function segmentRoleLabel(row) {
  if (isSkipEmbedding(row)) return "父片";
  if (row?.parentChunkId) return "子片";
  return "普通片";
}

function segmentRoleType(row) {
  if (isSkipEmbedding(row)) return "warning";
  if (row?.parentChunkId) return "";
  return "success";
}

function segmentRoleTip(row) {
  if (isSkipEmbedding(row)) return "超长段的完整原文，仅作检索回查上下文，不写入向量库";
  if (row?.parentChunkId) return `按长度切出的子片，将写入向量库；父片 ID: ${row.parentChunkId}`;
  return "长度未超限，整段写入向量库";
}

function textPreview(text) {
  if (!text) return "";
  const normalized = String(text).replace(/\s+/g, " ").trim();
  return normalized.length > 120 ? `${normalized.slice(0, 120)}...` : normalized;
}

function formatMetadata(metadata) {
  if (!metadata) return "";
  if (typeof metadata === "string") {
    try {
      metadata = JSON.parse(metadata);
    } catch {
      return metadata;
    }
  }
  if (typeof metadata !== "object") return String(metadata);
  const keys = ["title", "subtitle", "headerLevel", "fileName", "sourceUrl"];
  const parts = keys
    .filter((k) => metadata[k] != null && metadata[k] !== "")
    .map((k) => `${k}: ${metadata[k]}`);
  return parts.length ? parts.join("；") : JSON.stringify(metadata);
}

function formatSplitParams(params) {
  if (!params) return "-";
  if (typeof params === "string") {
    try {
      return JSON.stringify(JSON.parse(params), null, 2);
    } catch {
      return params;
    }
  }
  return JSON.stringify(params, null, 2);
}

function getList() {
  loading.value = true;
  const params = proxy.addDateRange({ ...queryParams.value }, dateRange.value);
  if (params.docId === "" || params.docId == null) {
    delete params.docId;
  }
  listEmbeddingTasks(params)
    .then((response) => {
      taskList.value = response.rows || [];
      total.value = response.total || 0;
    })
    .finally(() => {
      loading.value = false;
      syncPolling();
    });
}

function applyRouteFilters() {
  const { docId, docTitle } = route.query;
  if (docId != null && docId !== "") {
    queryParams.value.docId = String(docId);
  }
  if (docTitle != null && docTitle !== "") {
    queryParams.value.docTitle = String(docTitle);
  }
}

function handleQuery() {
  queryParams.value.pageNum = 1;
  getList();
}

function resetQuery() {
  dateRange.value = [];
  proxy.resetForm("queryRef");
  handleQuery();
}

function openDetail(row) {
  detailOpen.value = true;
  detailData.value = null;
  detailLoading.value = true;
  getEmbeddingTask(row.taskId)
    .then((res) => {
      detailData.value = res.data;
    })
    .finally(() => {
      detailLoading.value = false;
    });
}

function openSegments(row) {
  currentSegmentTask.value = row;
  segmentQuery.value.pageNum = 1;
  segmentOpen.value = true;
  loadSegments();
}

function resetSegments() {
  currentSegmentTask.value = null;
  segmentList.value = [];
  segmentTotal.value = 0;
  segmentQuery.value = { pageNum: 1, pageSize: 10, skipEmbedding: undefined };
}

function loadSegments() {
  if (!currentSegmentTask.value) return;
  segmentLoading.value = true;
  const params = { ...segmentQuery.value };
  if (params.skipEmbedding === undefined || params.skipEmbedding === "") {
    delete params.skipEmbedding;
  }
  listEmbeddingSegments(currentSegmentTask.value.taskId, params)
    .then((res) => {
      segmentList.value = res.rows || [];
      segmentTotal.value = res.total || 0;
    })
    .finally(() => {
      segmentLoading.value = false;
    });
}

function handleRetry(row) {
  const tip =
    row.status === "EMBED_FAILED"
      ? "将保留切分结果，从向量化阶段续跑。"
      : "将跳过已切分文件，从未完成文件继续切分。";
  proxy.$modal
    .confirm(`确认重试任务 #${row.taskId} 吗？按原切分参数执行：${tip}`)
    .then(() => retryEmbeddingTask(row.taskId))
    .then(() => {
      proxy.$modal.msgSuccess("重试任务已提交");
      getList();
    })
    .catch(() => {});
}

function handleDelete(row) {
  proxy.$modal
    .confirm(`确认删除任务 #${row.taskId} 吗？将清理其切分与未发布向量，删除后才可对该文档新建 Embedding 任务。`)
    .then(() => deleteEmbeddingTask(row.taskId))
    .then(() => {
      proxy.$modal.msgSuccess("删除成功");
      getList();
    })
    .catch(() => {});
}

function syncPolling() {
  // 暂不自动轮询，避免进行中任务反复刷新列表
  stopPolling();
}

function startPolling() {
  // disabled: 手动搜索/刷新即可
  return;
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

onMounted(() => {
  applyRouteFilters();
  loadSplitTypeMap();
  getList();
});

async function loadSplitTypeMap() {
  try {
    const res = await getEmbeddingStrategies();
    const list = res.data || [];
    splitTypeMap.value = Object.fromEntries(list.map((s) => [s.code, s.name]));
  } catch {
    splitTypeMap.value = {};
  }
}

onBeforeUnmount(() => {
  stopPolling();
});
</script>

<style scoped>
.mb8 {
  margin-bottom: 8px;
}
.json-block {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 12px;
  line-height: 1.5;
  background: #f5f7fa;
  padding: 8px;
  border-radius: 4px;
}
.error-text {
  color: #f56c6c;
  white-space: pre-wrap;
  word-break: break-all;
}
.segment-toolbar {
  margin-bottom: 12px;
}
</style>
