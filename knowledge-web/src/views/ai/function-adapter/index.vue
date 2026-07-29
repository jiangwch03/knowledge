<template>
  <div class="app-container">
    <el-form
      :model="queryParams"
      ref="queryRef"
      :inline="true"
      v-show="showSearch"
    >
      <el-form-item label="业务功能点" prop="functionPoint">
        <el-input
          v-model="queryParams.functionPoint"
          placeholder="请输入业务功能点"
          clearable
          style="width: 200px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="参数ID" prop="paramId">
        <el-input
          v-model="queryParams.paramId"
          placeholder="请输入参数ID"
          clearable
          style="width: 200px"
          @keyup.enter="handleQuery"
        />
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
          icon="Plus"
          @click="handleAdd"
          v-hasPermi="['ai:model:function-adapter:add']"
        >新增</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
    </el-row>

    <el-table v-loading="loading" :data="adapterList">
      <el-table-column label="适配ID" prop="adapterId" width="80" align="center" />
      <el-table-column
        label="业务功能点"
        prop="functionPoint"
        min-width="120"
        :show-overflow-tooltip="true"
      />
      <el-table-column
        label="参数ID"
        prop="paramId"
        min-width="140"
        :show-overflow-tooltip="true"
      />
      <el-table-column
        label="模型编码"
        prop="modelCode"
        min-width="130"
        :show-overflow-tooltip="true"
      />
      <el-table-column
        label="模型名称"
        prop="modelName"
        min-width="130"
        :show-overflow-tooltip="true"
      />
      <el-table-column label="模型类型" prop="modelType" min-width="140" align="center">
        <template #default="scope">
          <dict-tag :options="ai_model_type" :value="normalizeModelType(scope.row.modelType)" />
        </template>
      </el-table-column>
      <el-table-column label="向量维度" prop="dimensions" width="90" align="center" />
      <el-table-column label="创建时间" prop="createTime" width="160" align="center">
        <template #default="scope">
          <span>{{ parseTime(scope.row.createTime) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" align="center" width="140" class-name="small-padding fixed-width">
        <template #default="scope">
          <el-button
            link
            type="primary"
            icon="Edit"
            @click="handleUpdate(scope.row)"
            v-hasPermi="['ai:model:function-adapter:edit']"
          >修改</el-button>
          <el-button
            link
            type="danger"
            icon="Delete"
            @click="handleDelete(scope.row)"
            v-hasPermi="['ai:model:function-adapter:remove']"
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

    <!-- 添加或修改对话框 -->
    <el-dialog :title="title" v-model="open" width="600px" append-to-body>
      <el-form ref="adapterRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="业务功能点" prop="functionPoint">
          <el-input v-model="form.functionPoint" placeholder="请输入业务功能点" />
        </el-form-item>
        <el-form-item label="参数ID" prop="paramId">
          <el-input
            v-model="form.paramId"
            placeholder="请输入参数ID，如 txt_to_markdown"
            @change="proxy.$refs['adapterRef']?.validateField?.('dimensions')"
          />
        </el-form-item>
        <el-form-item label="模型类型" prop="modelType">
          <el-select
            v-model="form.modelType"
            placeholder="请先选择模型类型"
            clearable
            style="width: 100%"
            @change="handleModelTypeChange"
          >
            <el-option
              v-for="dict in ai_model_type"
              :key="dict.value"
              :label="dict.label"
              :value="dict.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="选择模型" prop="modelId">
          <el-select
            v-model="form.modelId"
            multiple
            popper-class="adapter-model-popper"
            :placeholder="form.modelType ? '请选择模型' : '请先选择模型类型'"
            :disabled="!form.modelType"
            style="width: 100%"
            @change="handleModelChange"
          >
            <el-option
              v-for="model in filteredModelOptions"
              :key="model.modelId"
              :label="model.modelName + ' (' + model.modelCode + ')'"
              :value="model.modelId"
            />
          </el-select>
        </el-form-item>
        <el-form-item
          v-if="isEmbeddingType"
          label="向量维度"
          prop="dimensions"
          required
        >
          <el-input-number
            v-model="form.dimensions"
            :min="1"
            :step="1"
            controls-position="right"
            placeholder="如千问 text-embedding-v4 默认 1024"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button type="primary" @click="submitForm">确 定</el-button>
          <el-button @click="cancel">取 消</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="FunctionAdapter">
import {
  listAdapter,
  addAdapter,
  updateAdapter,
  delAdapter,
} from "@/api/ai/function-adapter";
import { listModelAll } from "@/api/ai/model";

const { proxy } = getCurrentInstance();
const { ai_model_type } = proxy.useDict("ai_model_type");

const adapterList = ref([]);
const loading = ref(false);
const showSearch = ref(true);
const total = ref(0);
const open = ref(false);
const title = ref("");
const allModelOptions = ref([]);

const data = reactive({
  form: {},
  queryParams: {
    pageNum: 1,
    pageSize: 10,
    functionPoint: undefined,
    paramId: undefined,
  },
  rules: {
    functionPoint: [
      { required: true, message: "业务功能点不能为空", trigger: "blur" },
    ],
    paramId: [
      { required: true, message: "参数ID不能为空", trigger: "blur" },
    ],
    modelType: [
      { required: true, message: "模型类型不能为空", trigger: "change" },
    ],
    modelId: [
      { required: true, message: "模型不能为空", trigger: "change" },
    ],
    dimensions: [
      {
        validator: (_rule, value, callback) => {
          if (isEmbeddingType.value) {
            if (value === undefined || value === null || value <= 0) {
              callback(new Error("Embedding 类型须配置大于 0 的向量维度"));
              return;
            }
          }
          callback();
        },
        trigger: "blur",
      },
    ],
  },
});

const { queryParams, form, rules } = toRefs(data);

const isEmbeddingType = computed(
  () => normalizeModelType(form.value.modelType) === "embedding"
);

const filteredModelOptions = computed(() => {
  const selectedType = normalizeModelType(form.value.modelType);
  if (!selectedType) {
    return [];
  }
  return allModelOptions.value.filter(
    (item) => normalizeModelType(item.modelType) === selectedType
  );
});

function normalizeModelType(type) {
  const normalized = (type || "").trim().toLowerCase();
  // 历史 chat 与 LLM 同义，统一归到 llm
  if (normalized === "chat") {
    return "llm";
  }
  return normalized;
}

function getList() {
  loading.value = true;
  listAdapter(queryParams.value).then((response) => {
    adapterList.value = response.rows;
    total.value = response.total;
    loading.value = false;
  });
}

function loadModelOptions() {
  return listModelAll().then((response) => {
    allModelOptions.value = response.data || [];
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

function cancel() {
  open.value = false;
  reset();
}

function reset() {
  form.value = {
    adapterId: undefined,
    functionPoint: undefined,
    paramId: undefined,
    modelType: undefined,
    modelId: [],
    dimensions: undefined,
    modelCode: undefined,
    modelName: undefined,
  };
  proxy.resetForm("adapterRef");
}

function handleModelTypeChange() {
  form.value.modelId = [];
  form.value.modelCode = undefined;
  form.value.modelName = undefined;
  if (!isEmbeddingType.value) {
    form.value.dimensions = undefined;
  }
  proxy.$refs["adapterRef"]?.clearValidate?.(["modelId", "dimensions"]);
}

function handleModelChange(modelIdArr) {
  if (Array.isArray(modelIdArr) && modelIdArr.length > 0) {
    const selected = filteredModelOptions.value.find(
      (item) => item.modelId === modelIdArr[modelIdArr.length - 1]
    );
    if (selected) {
      form.value.modelCode = selected.modelCode;
      form.value.modelName = selected.modelName;
    }
  }
}

function resolveModelTypeByIds(modelIds) {
  if (!Array.isArray(modelIds) || modelIds.length === 0) {
    return undefined;
  }
  const first = allModelOptions.value.find((item) => item.modelId === modelIds[0]);
  return first?.modelType ? normalizeModelType(first.modelType) : undefined;
}

function handleAdd() {
  reset();
  open.value = true;
  title.value = "新增模型功能适配";
}

async function handleUpdate(row) {
  reset();
  if (!allModelOptions.value.length) {
    await loadModelOptions();
  }
  // modelId 存储为管道符分隔的字符串（如 "3" 或 "3|5|8"）
  // 拆分为数字数组，与 el-select multiple 的 v-model 类型匹配
  const rawModelId = row.modelId;
  const modelIds = rawModelId
    ? String(rawModelId)
        .split("|")
        .map((id) => parseInt(id.trim(), 10))
        .filter((id) => !isNaN(id))
    : [];
  form.value = {
    adapterId: row.adapterId,
    functionPoint: row.functionPoint,
    paramId: row.paramId,
    modelType: resolveModelTypeByIds(modelIds),
    modelId: modelIds,
    dimensions: row.dimensions,
    modelCode: row.modelCode,
    modelName: row.modelName,
  };
  open.value = true;
  title.value = "修改模型功能适配";
}

function submitForm() {
  proxy.$refs["adapterRef"].validate((valid) => {
    if (!valid) return;
    // 将多选的 modelId 数组转为管道符分隔的字符串提交后端；modelType 仅前端筛选用
    const submitData = { ...form.value };
    delete submitData.modelType;
    if (Array.isArray(submitData.modelId)) {
      submitData.modelId = submitData.modelId.join("|");
    }
    if (!isEmbeddingType.value) {
      submitData.dimensions = undefined;
    }
    if (form.value.adapterId != undefined) {
      updateAdapter(form.value.adapterId, submitData).then(() => {
        proxy.$modal.msgSuccess("修改成功");
        open.value = false;
        getList();
      });
    } else {
      addAdapter(submitData).then(() => {
        proxy.$modal.msgSuccess("新增成功");
        open.value = false;
        getList();
      });
    }
  });
}

function handleDelete(row) {
  proxy.$modal
    .confirm('是否确认删除适配ID为"' + row.adapterId + '"的数据项？')
    .then(() => delAdapter(row.adapterId))
    .then(() => {
      proxy.$modal.msgSuccess("删除成功");
      getList();
    })
    .catch(() => {});
}

getList();
loadModelOptions();
</script>

<style scoped>
.adapter-model-popper {
  min-width: 420px !important;
}
</style>
