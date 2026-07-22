<template>
  <div class="app-container">
    <el-form
      :model="queryParams"
      ref="queryRef"
      :inline="true"
      v-show="showSearch"
    >
      <el-form-item label="文档标题" prop="docTitle">
        <el-input
          v-model="queryParams.docTitle"
          placeholder="请输入文档标题"
          clearable
          style="width: 200px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="文档格式" prop="docType">
        <el-select
          v-model="queryParams.docType"
          placeholder="请选择文档格式"
          clearable
          style="width: 160px"
          @keyup.enter="handleQuery"
        >
          <el-option label="PDF" value="pdf" />
          <el-option label="DOC" value="doc" />
          <el-option label="DOCX" value="docx" />
          <el-option label="XLSX" value="xlsx" />
          <el-option label="MD" value="md" />
        </el-select>
      </el-form-item>
      <el-form-item label="状态" prop="status">
        <el-select
          v-model="queryParams.status"
          placeholder="请选择状态"
          clearable
          style="width: 160px"
        >
          <el-option
            v-for="dict in document_status"
            :key="dict.value"
            :label="dict.label"
            :value="dict.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button
          type="primary"
          plain
          icon="Upload"
          @click="handleUpload"
          v-hasPermi="['rag:document:upload']"
        >上传文件</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="success"
          plain
          icon="Edit"
          @click="handleConvert"
        >Markdown 转换</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
    </el-row>

    <el-table v-loading="loading" :data="recordList">
      <el-table-column label="文档标题" prop="docTitle" :show-overflow-tooltip="true" />
      <el-table-column label="文档描述" prop="docDesc" :show-overflow-tooltip="true" min-width="120" />
      <el-table-column label="文档格式" prop="docType" width="100" align="center" />
      <el-table-column label="版本" prop="docVersion" width="80" align="center" />
      <el-table-column label="版本说明" prop="versionRemark" :show-overflow-tooltip="true" min-width="120" />
      <el-table-column label="状态" prop="status" width="130" align="center">
        <template #default="scope">
          <dict-tag :options="document_status" :value="scope.row.status" />
        </template>
      </el-table-column>
      <el-table-column label="创建时间" prop="createTime" width="160" align="center">
        <template #default="scope">
          <span>{{ parseTime(scope.row.createTime) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="更新时间" prop="updateTime" width="160" align="center">
        <template #default="scope">
          <span>{{ parseTime(scope.row.updateTime) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="错误信息" prop="errorMessage" :show-overflow-tooltip="true" min-width="160" />
      <el-table-column label="操作" align="center" width="380" class-name="small-padding fixed-width">
        <template #default="scope">
          <el-button
            v-if="scope.row.parseTaskId"
            link
            type="info"
            icon="InfoFilled"
            @click="openTaskDetail(scope.row)"
          >详情</el-button>
          <el-button
            v-if="canEmbedding(scope.row)"
            link
            type="success"
            icon="Connection"
            @click="handleEmbedding(scope.row)"
            v-hasPermi="['rag:embedding:create']"
          >Embedding</el-button>
          <el-button
            link
            type="primary"
            icon="View"
            @click="handlePreview(scope.row)"
            v-hasPermi="['rag:document:preview']"
          >预览</el-button>
          <el-button
            link
            type="primary"
            icon="Download"
            @click="handleDownload(scope.row)"
            v-hasPermi="['rag:document:download']"
          >下载</el-button>
          <el-button
            v-if="scope.row.status === 'USER_DECISION'"
            link
            type="warning"
            icon="Refresh"
            @click="handleDecision(scope.row, 'retry')"
          >重试</el-button>
          <el-button
            v-if="scope.row.status === 'USER_DECISION'"
            link
            type="danger"
            icon="Delete"
            @click="handleDecision(scope.row, 'delete')"
          >删除</el-button>
          <el-button
            v-if="canDelete(scope.row)"
            link
            type="danger"
            icon="Delete"
            @click="handleDelete(scope.row)"
            v-hasPermi="['rag:document:remove']"
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

    <!-- 上传文件弹框 -->
    <el-dialog title="上传文档" v-model="uploadOpen" width="600px" append-to-body>
      <el-form ref="uploadRef" :model="uploadForm" :rules="uploadRules" label-width="100px">
        <el-form-item label="文档标题" prop="docTitle">
          <el-input v-model="uploadForm.docTitle" placeholder="请输入文档标题" @input="onDocTitleInput" />
        </el-form-item>
        <el-form-item label="版本号" v-if="uploadForm.docVersion">
          <el-tag type="info">{{ uploadForm.docVersion }}</el-tag>
        </el-form-item>
        <el-form-item label="文档描述" prop="docDesc">
          <el-input v-model="uploadForm.docDesc" type="textarea" placeholder="请输入文档描述" />
        </el-form-item>
        <el-form-item label="版本说明" prop="versionRemark">
          <el-input v-model="uploadForm.versionRemark" placeholder="请输入版本说明" />
        </el-form-item>
        <el-form-item label="解析模式" prop="parseMode">
          <el-radio-group v-model="uploadForm.parseMode">
            <el-radio value="document">文档解析</el-radio>
            <el-radio value="html">HTML 解析</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="公式识别" prop="enableFormula">
          <el-radio-group v-model="uploadForm.enableFormula">
            <el-radio value="1">开启</el-radio>
            <el-radio value="0">关闭</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="表格识别" prop="enableTable">
          <el-radio-group v-model="uploadForm.enableTable">
            <el-radio value="1">开启</el-radio>
            <el-radio value="0">关闭</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="OCR" prop="isOcr">
          <el-radio-group v-model="uploadForm.isOcr">
            <el-radio value="1">开启</el-radio>
            <el-radio value="0">关闭</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="文档语言" prop="language">
          <el-select v-model="uploadForm.language" placeholder="请选择文档语言" style="width: 100%">
            <el-option label="中文" value="ch" />
            <el-option label="英文" value="en" />
            <el-option label="自动识别" value="auto" />
          </el-select>
        </el-form-item>
        <el-form-item label="上传文件" prop="file">
          <el-upload
            ref="contentUploadRef"
            :action="uploadAction"
            :headers="uploadHeaders"
            :data="uploadData"
            :before-upload="handleBeforeUpload"
            :on-success="handleUploadSuccess"
            :on-error="handleUploadError"
            :on-change="handleUploadChange"
            :on-remove="handleUploadRemove"
            :on-exceed="handleExceed"
            :limit="1"
            :auto-upload="false"
            :file-list="uploadFileList"
            accept=".pdf,.doc,.docx,.xlsx,.md"
          >
            <el-button type="primary" :disabled="!!selectedUploadFile">选取文件</el-button>
            <template #tip>
              <div class="el-upload__tip">支持 PDF/DOC/DOCX/XLSX/MD，单个文件不超过 100MB</div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button type="primary" @click="submitUpload">确 定</el-button>
          <el-button @click="cancelUpload">取 消</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- Markdown 转换弹框 -->
    <el-dialog title="TXT 转 Markdown" v-model="convertOpen" width="900px" append-to-body>
      <el-form ref="convertRef" :model="convertForm" :rules="convertRules" label-width="100px">
        <el-form-item label="输入方式" prop="inputType">
          <el-radio-group v-model="convertForm.inputType">
            <el-radio value="paste">文本粘贴</el-radio>
            <el-radio value="file">文件读取</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="convertForm.inputType === 'file'" label="选择文件">
          <el-upload
            ref="txtUploadRef"
            :auto-upload="false"
            :on-change="handleTxtFileChange"
            :limit="1"
            accept=".txt"
          >
            <el-button type="primary">选取 TXT 文件</el-button>
          </el-upload>
        </el-form-item>
        <el-form-item label="文本内容" prop="content">
          <el-input
            v-model="convertForm.content"
            type="textarea"
            :rows="10"
            placeholder="请粘贴 UTF-8 文本内容，大小不超过 512KB"
          />
        </el-form-item>
        <el-form-item label="转换结果" v-if="convertResult">
          <el-input
            v-model="convertResult"
            type="textarea"
            :rows="10"
            readonly
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button type="primary" @click="submitConvert" :loading="convertLoading">开始转换</el-button>
          <el-button v-if="convertResult" @click="downloadConvertResult">下载 MD</el-button>
          <el-button @click="cancelConvert">关 闭</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 解析任务详情弹框 -->
    <el-dialog title="解析任务详情" v-model="taskOpen" width="700px" append-to-body>
      <!-- 多任务切换 -->
      <div v-if="taskList.length > 1" class="mb8">
        <span style="font-weight:bold; margin-right:8px;">任务列表：</span>
        <el-tag
          v-for="t in taskList"
          :key="t.parseTaskId"
          :type="selectedTaskId === t.parseTaskId ? 'primary' : 'info'"
          style="cursor:pointer; margin-right:6px;"
          @click="switchTask(t.parseTaskId)"
        >
          任务 #{{ t.parseTaskId }}
        </el-tag>
      </div>
      <el-descriptions :column="1" border v-if="taskDetail">
        <el-descriptions-item label="任务 ID">{{ taskDetail.parseTaskId }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <dict-tag :options="taskStatusOptions" :value="taskDetail.status" />
        </el-descriptions-item>
        <el-descriptions-item label="解析模式">{{ taskDetail.parseMode }}</el-descriptions-item>
        <el-descriptions-item label="批次 ID">{{ taskDetail.batchId }}</el-descriptions-item>
        <el-descriptions-item label="错误码">{{ taskDetail.errorCode }}</el-descriptions-item>
        <el-descriptions-item label="错误信息" class-name="task-error-message">
          {{ taskDetail.errorMessage }}
        </el-descriptions-item>
      </el-descriptions>
      <el-table :data="taskDetailList" class="mt10" v-loading="taskDetailLoading">
        <el-table-column label="分段序号" prop="sequenceNumber" width="90" align="center" />
        <el-table-column label="页码范围" prop="pageRanges" width="120" align="center" />
        <el-table-column label="状态" prop="state" width="120" align="center">
          <template #default="scope">
            <el-tag :type="detailStateType(scope.row.state)">{{ detailStateLabel(scope.row.state) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="错误信息" prop="errMsg" min-width="200" :show-overflow-tooltip="true" />
      </el-table>
    </el-dialog>

    <!-- 预览弹框 -->
    <el-dialog title="文档预览" v-model="previewOpen" width="900px" append-to-body>
      <div class="markdown-preview">
        <pre>{{ previewContent }}</pre>
      </div>
    </el-dialog>
  </div>
</template>

<script setup name="Document">
import {
  listDocumentRecord,
  delDocumentRecord,
  downloadDocument,
  previewDocument,
  uploadDocument,
  txtToMarkdown,
  getParseTask,
  getParseTaskDetails,
  getParseTasksByRecord,
  handleParseDecision,
  getDocumentStatusOptions,
  getNextVersion,
} from "@/api/content/document";
import { getToken } from "@/utils/auth";
import { useRouter } from "vue-router";

const router = useRouter();
const { proxy } = getCurrentInstance();

// 文档状态选项（上传记录状态，从后端接口获取）
const document_status = ref([]);

// 加载状态选项
async function loadStatusOptions() {
  try {
    const res = await getDocumentStatusOptions();
    document_status.value = res.data || [];
  } catch (e) {
    console.error("加载文档状态选项失败", e);
  }
}

const recordList = ref([]);
const loading = ref(false);
const showSearch = ref(true);
const total = ref(0);
const queryParams = ref({
  pageNum: 1,
  pageSize: 10,
  docTitle: undefined,
  docType: undefined,
  status: undefined,
});

const contentUploadRef = ref(null);
const uploadOpen = ref(false);
const uploadFileList = ref([]);
const selectedUploadFile = ref(null);
const uploadForm = reactive({
  docTitle: undefined,
  docDesc: undefined,
  docVersion: undefined,
  versionRemark: undefined,
  parseMode: "document",
  enableFormula: "1",
  enableTable: "1",
  isOcr: "0",
  language: "ch",
});
const uploadRules = {
  docTitle: [{ required: true, message: "文档标题不能为空", trigger: "blur" }],
};
const uploadAction = import.meta.env.VITE_APP_CONTENT_API + "/document-parse/upload";
const uploadHeaders = { Authorization: "Bearer " + getToken() };

const convertOpen = ref(false);
const convertLoading = ref(false);
const convertResult = ref("");
const convertForm = reactive({
  inputType: "paste",
  content: "",
});
const convertRules = {
  content: [{ required: true, message: "文本内容不能为空", trigger: "blur" }],
};

const taskOpen = ref(false);
const taskDetail = ref(null);
const taskDetailList = ref([]);
const taskDetailLoading = ref(false);
const taskList = ref([]);
const selectedTaskId = ref(null);
let taskTimer = null;

const previewOpen = ref(false);
const previewContent = ref("");

function getList() {
  loading.value = true;
  listDocumentRecord(queryParams.value).then((response) => {
    recordList.value = response.rows;
    total.value = response.total;
    loading.value = false;
  });
}

function handleQuery() {
  queryParams.value.pageNum = 1;
  getList();
}

function resetQuery() {
  proxy.resetForm("queryRef");
  handleQuery();
}

function canDelete(row) {
  return row.status !== "CONVERTED" && row.status !== "USER_DECISION";
}

function canEmbedding(row) {
  return !!row.docId;
}

function handleEmbedding(row) {
  router.push({
    path: "/knowledge/embedding-config",
    query: { docId: String(row.docId), sourceType: "0" },
  });
}

function handleUpload() {
  resetUpload();
  uploadOpen.value = true;
}

function resetUpload() {
  uploadForm.docTitle = undefined;
  uploadForm.docDesc = undefined;
  uploadForm.docVersion = undefined;
  uploadForm.versionRemark = undefined;
  uploadForm.parseMode = "document";
  uploadForm.enableFormula = "1";
  uploadForm.enableTable = "1";
  uploadForm.isOcr = "0";
  uploadForm.language = "ch";
  uploadFileList.value = [];
  selectedUploadFile.value = null;
  contentUploadRef.value?.clearFiles()
  proxy.resetForm("uploadRef");
}

function onDocTitleInput(value) {
  if (!value || !value.trim()) {
    uploadForm.docVersion = undefined;
    return;
  }
  getNextVersion(value.trim()).then((res) => {
    uploadForm.docVersion = res.data?.docVersion;
  }).catch(() => {
    uploadForm.docVersion = undefined;
  });
}

function cancelUpload() {
  uploadOpen.value = false;
  resetUpload();
}

function handleBeforeUpload(file) {
  const allowed = ["pdf", "doc", "docx", "xlsx", "md"];
  const ext = file.name.split(".").pop().toLowerCase();
  if (!allowed.includes(ext)) {
    proxy.$modal.msgError("仅支持 PDF/DOC/DOCX/XLSX/MD 格式文件");
    return false;
  }
  if (file.size / 1024 / 1024 > 100) {
    proxy.$modal.msgError("文件大小不能超过 100MB");
    return false;
  }
  return true;
}

function handleUploadSuccess(res) {
  proxy.$modal.closeLoading();
  if (res.code === 200) {
    proxy.$modal.msgSuccess("上传成功");
    uploadOpen.value = false;
    resetUpload();
    getList();
  } else {
    proxy.$modal.msgError(res.msg || "上传失败");
  }
}

function handleUploadChange(uploadFile) {
  selectedUploadFile.value = uploadFile.raw || uploadFile;
  uploadFileList.value = [{
    name: uploadFile.name,
    raw: selectedUploadFile.value,
  }];
}

function handleUploadRemove() {
  selectedUploadFile.value = null;
  uploadFileList.value = [];
}

function handleExceed() {
  proxy.$modal.msgWarning("已有一个文件，请先移除后再选择新文件");
}

function handleUploadError() {
  proxy.$modal.closeLoading();
  proxy.$modal.msgError("上传失败");
}

function submitUpload() {
  proxy.$refs["uploadRef"].validate((valid) => {
    if (!valid) return;
    if (!selectedUploadFile.value) {
      proxy.$modal.msgError("请选择要上传的文件");
      return;
    }
    const file = selectedUploadFile.value;
    const allowed = ["pdf", "doc", "docx", "xlsx", "md"];
    const ext = file.name.split(".").pop().toLowerCase();
    if (!allowed.includes(ext)) {
      proxy.$modal.msgError("仅支持 PDF/DOC/DOCX/XLSX/MD 格式文件");
      return;
    }
    if (file.size / 1024 / 1024 > 100) {
      proxy.$modal.msgError("文件大小不能超过 100MB");
      return;
    }
    const formData = new FormData();
    formData.append("file", file);
    formData.append("doc_title", uploadForm.docTitle);
    formData.append("doc_desc", uploadForm.docDesc || "");
    formData.append("version_remark", uploadForm.versionRemark || "");
    formData.append("parse_mode", uploadForm.parseMode);
    formData.append("enable_formula", uploadForm.enableFormula);
    formData.append("enable_table", uploadForm.enableTable);
    formData.append("is_ocr", uploadForm.isOcr);
    formData.append("language", uploadForm.language);
    proxy.$modal.loading("正在上传，请稍候...");
    uploadDocument(formData)
      .then((res) => {
        proxy.$modal.closeLoading();
        if (res.code === 200) {
          proxy.$modal.msgSuccess("上传成功");
          uploadOpen.value = false;
          resetUpload();
          getList();
        } else {
          proxy.$modal.msgError(res.msg || "上传失败");
        }
      })
      .catch((error) => {
        proxy.$modal.closeLoading();
        const data = error?.response?.data;
        const detail = data?.detail;
        if (detail && Array.isArray(detail)) {
          const msg = detail.map(d => {
            const loc = d.loc ? d.loc.join('.') : '';
            return loc ? `[${loc}] ${d.msg}` : (d.msg || JSON.stringify(d));
          }).join('; ');
          proxy.$modal.msgError(`上传失败: ${msg}`);
        } else if (typeof detail === 'string') {
          proxy.$modal.msgError(`上传失败: ${detail}`);
        } else if (data?.msg) {
          proxy.$modal.msgError(`上传失败: ${data.msg}`);
        } else {
          proxy.$modal.msgError("上传失败，请查看浏览器控制台获取详情");
          console.error('[uploadDocument error]', error?.response?.data || error);
        }
      });
  });
}

const uploadData = computed(() => {
  return {
    docTitle: uploadForm.docTitle,
    docVersion: uploadForm.docVersion,
    docDesc: uploadForm.docDesc || "",
    versionRemark: uploadForm.versionRemark || "",
    parseMode: uploadForm.parseMode,
    enableFormula: uploadForm.enableFormula,
    enableTable: uploadForm.enableTable,
    isOcr: uploadForm.isOcr,
    language: uploadForm.language,
  };
});

function handleConvert() {
  convertForm.inputType = "paste";
  convertForm.content = "";
  convertResult.value = "";
  convertOpen.value = true;
}

function handleTxtFileChange(file) {
  const reader = new FileReader();
  reader.onload = (e) => {
    convertForm.content = e.target.result;
  };
  reader.readAsText(file.raw, "UTF-8");
}

function submitConvert() {
  proxy.$refs["convertRef"].validate((valid) => {
    if (!valid) return;
    if (convertForm.content.length > 524288) {
      proxy.$modal.msgError("文本内容大小不能超过 512KB");
      return;
    }
    convertLoading.value = true;
    txtToMarkdown({ content: convertForm.content })
      .then((response) => {
        convertResult.value = response.data;
        proxy.$modal.msgSuccess("转换成功");
      })
      .finally(() => {
        convertLoading.value = false;
      });
  });
}

function downloadConvertResult() {
  const blob = new Blob([convertResult.value], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "converted.md";
  link.click();
  URL.revokeObjectURL(url);
}

function cancelConvert() {
  convertOpen.value = false;
}

function handleDecision(row, action) {
  if (action === "delete") {
    proxy.$modal
      .confirm("确认删除该记录吗？")
      .then(() => handleParseDecision(row.parseTaskId, { action: "delete" }))
      .then(() => {
        proxy.$modal.msgSuccess("删除成功");
        getList();
      })
      .catch(() => {});
  } else {
    handleParseDecision(row.parseTaskId, { action: "retry" }).then(() => {
      proxy.$modal.msgSuccess("已发起重试");
      getList();
    });
  }
}

function handlePreview(row) {
  if (!row.docId) {
    proxy.$modal.msgInfo("文档尚未生成，无法预览");
    return;
  }
  previewDocument(row.docId).then((response) => {
    previewContent.value = response;
    previewOpen.value = true;
  });
}

function handleDownload(row) {
  if (!row.docId) {
    proxy.$modal.msgInfo("文档尚未生成，无法下载");
    return;
  }
  downloadDocument(row.docId).then((response) => {
    proxy.$download.saveAs(response, row.docName + ".md");
  });
}

function handleDelete(row) {
  proxy.$modal
    .confirm('确认删除该记录吗？')
    .then(() => delDocumentRecord(row.taskId))
    .then(() => {
      proxy.$modal.msgSuccess("删除成功");
      getList();
    })
    .catch(() => {});
}

function openTaskDetail(row) {
  if (!row.parseTaskId) return;
  taskOpen.value = true;
  taskDetail.value = null;
  taskDetailList.value = [];
  taskList.value = [];
  selectedTaskId.value = row.parseTaskId;
  // 加载该任务下的所有解析任务列表
  if (row.taskId) {
    getParseTasksByRecord(row.taskId).then((response) => {
      taskList.value = response.data || [];
    });
  }
  loadTaskDetail(row.parseTaskId);
  if (taskTimer) clearInterval(taskTimer);
  taskTimer = setInterval(() => {
    if (!taskOpen.value) {
      clearInterval(taskTimer);
      return;
    }
    if (selectedTaskId.value) {
      loadTaskDetail(selectedTaskId.value);
    }
  }, 10000);
}

function switchTask(parseTaskId) {
  selectedTaskId.value = parseTaskId;
  taskDetail.value = null;
  taskDetailList.value = [];
  loadTaskDetail(parseTaskId);
}

function loadTaskDetail(parseTaskId) {
  taskDetailLoading.value = true;
  getParseTask(parseTaskId).then((response) => {
    taskDetail.value = response.data;
  });
  getParseTaskDetails(parseTaskId).then((response) => {
    taskDetailList.value = response.data || [];
    taskDetailLoading.value = false;
  });
}

function detailStateType(state) {
  if (state === "PARSED") return "success";
  if (["UPLOAD_FAILED", "PARSE_FAILED"].includes(state)) return "danger";
  if (state === "PARSING") return "primary";
  if (state === "WAITING_UPLOAD") return "warning";
  return "info";
}

const detailStateMap = {
  WAITING_UPLOAD: "待上传",
  UPLOAD_FAILED: "上传失败",
  PARSING: "解析中",
  PARSED: "解析完成",
  PARSE_FAILED: "解析失败",
  RETRIED: "已重试",
};

function detailStateLabel(state) {
  return detailStateMap[state] || state;
}

// 任务状态选项：在文档状态基础上补充 FAILED（任务专用）
const taskStatusOptions = computed(() => {
  const options = [...(document_status.value || [])];
  if (!options.some(o => o.value === 'FAILED')) {
    options.push({ value: 'FAILED', label: '解析失败' });
  }
  return options;
});

onBeforeUnmount(() => {
  if (taskTimer) clearInterval(taskTimer);
});

// 页面初始化：加载状态选项和列表数据
loadStatusOptions();
getList();
</script>

<style scoped>
.mt10 {
  margin-top: 10px;
}
.markdown-preview {
  max-height: 600px;
  overflow: auto;
  background: #f5f7fa;
  padding: 16px;
  border-radius: 4px;
}
.markdown-preview pre {
  white-space: pre-wrap;
  word-wrap: break-word;
  margin: 0;
}
:deep(.task-error-message) {
  word-break: break-all;
  white-space: pre-wrap;
  line-height: 1.6;
}
</style>
