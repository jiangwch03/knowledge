<template>
  <div class="app-container">
    <el-form
      :model="queryParams"
      ref="queryRef"
      :inline="true"
      v-show="showSearch"
    >
      <el-form-item label="模型编码" prop="modelCode">
        <el-input
          v-model="queryParams.modelCode"
          placeholder="请输入模型编码"
          clearable
          style="width: 200px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="提供商" prop="provider">
        <el-select
          v-model="queryParams.provider"
          placeholder="请选择提供商"
          clearable
          style="width: 200px"
          @keyup.enter="handleQuery"
        >
          <el-option
            v-for="dict in ai_provider_type"
            :key="dict.value"
            :label="dict.label"
            :value="dict.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="状态" prop="status">
        <el-select
          v-model="queryParams.status"
          placeholder="模型状态"
          clearable
          style="width: 240px"
        >
          <el-option
            v-for="dict in sys_normal_disable"
            :key="dict.value"
            :label="dict.label"
            :value="dict.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery"
          >搜索</el-button
        >
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
          v-hasPermi="['ai:model:add']"
          >新增</el-button
        >
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="success"
          plain
          icon="Edit"
          :disabled="single"
          @click="handleUpdate"
          v-hasPermi="['ai:model:edit']"
          >修改</el-button
        >
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="danger"
          plain
          icon="Delete"
          :disabled="multiple"
          @click="handleDelete"
          v-hasPermi="['ai:model:remove']"
          >删除</el-button
        >
      </el-col>
      <right-toolbar
        v-model:showSearch="showSearch"
        @queryTable="getList"
      ></right-toolbar>
    </el-row>

    <el-table
      v-loading="loading"
      :data="modelList"
      @selection-change="handleSelectionChange"
    >
      <el-table-column type="selection" width="55" align="center" />
      <el-table-column label="模型ID" align="center" prop="modelId" />
      <el-table-column label="模型编码" align="center" prop="modelCode" />
      <el-table-column label="模型类型" align="center" prop="modelType" width="130">
        <template #default="scope">
          <dict-tag :options="ai_model_type" :value="scope.row.modelType" />
        </template>
      </el-table-column>
      <el-table-column label="提供商" align="center" prop="provider">
        <template #default="scope">
          <dict-tag :options="ai_provider_type" :value="scope.row.provider" />
        </template>
      </el-table-column>
      <el-table-column label="支持推理" align="center" prop="supportReasoning">
        <template #default="scope">
          <dict-tag :options="sys_yes_no" :value="scope.row.supportReasoning" />
        </template>
      </el-table-column>
      <el-table-column label="支持图片" align="center" prop="supportImages">
        <template #default="scope">
          <dict-tag :options="sys_yes_no" :value="scope.row.supportImages" />
        </template>
      </el-table-column>
      <el-table-column label="工具调用" align="center" prop="supportToolCall">
        <template #default="scope">
          <dict-tag :options="sys_yes_no" :value="scope.row.supportToolCall" />
        </template>
      </el-table-column>
      <el-table-column label="结构化输出" align="center" prop="supportStructuredOutput">
        <template #default="scope">
          <dict-tag :options="sys_yes_no" :value="scope.row.supportStructuredOutput" />
        </template>
      </el-table-column>
      <el-table-column label="状态" align="center" prop="status">
        <template #default="scope">
          <dict-tag :options="sys_normal_disable" :value="scope.row.status" />
        </template>
      </el-table-column>
      <el-table-column
        label="创建时间"
        align="center"
        prop="createTime"
        width="180"
      >
        <template #default="scope">
          <span>{{ parseTime(scope.row.createTime) }}</span>
        </template>
      </el-table-column>
      <el-table-column
        label="操作"
        width="180"
        align="center"
        class-name="small-padding fixed-width"
      >
        <template #default="scope">
          <el-button
            link
            type="primary"
            icon="Edit"
            @click="handleUpdate(scope.row)"
            v-hasPermi="['ai:model:edit']"
            >修改</el-button
          >
          <el-button
            link
            type="primary"
            icon="Delete"
            @click="handleDelete(scope.row)"
            v-hasPermi="['ai:model:remove']"
            >删除</el-button
          >
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
    <el-dialog :title="title" v-model="open" width="1200px" append-to-body class="scrollbar">
      <el-form ref="modelRef" :model="form" :rules="rules" label-width="100px" class="model-form">
        <el-row :gutter="12">
          <el-col :span="6">
            <el-form-item label="模型编码" prop="modelCode">
              <el-input
                v-model="form.modelCode"
                placeholder="如 deepseek-r1"
              />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="模型名称" prop="modelName">
              <el-input v-model="form.modelName" placeholder="请输入模型名称" />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="提供商" prop="provider">
              <el-select
                v-model="form.provider"
                placeholder="请选择提供商"
                style="width: 100%"
              >
                <el-option
                  v-for="dict in ai_provider_type"
                  :key="dict.value"
                  :label="dict.label"
                  :value="dict.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="模型类型" prop="modelType">
              <el-select
                v-model="form.modelType"
                placeholder="请选择模型类型"
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
          </el-col>
          <el-col :span="24">
            <el-form-item label="API Key" prop="apiKey">
              <el-input
                v-model="form.apiKey"
                placeholder="请输入 API Key"
                type="password"
                show-password
              />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="Base URL" prop="baseUrl">
              <el-input v-model="form.baseUrl" placeholder="请输入 Base URL" />
            </el-form-item>
          </el-col>
          <el-col v-if="showProfile" :span="8">
            <el-form-item label="默认温度" prop="temperature">
              <el-input-number
                v-model="form.temperature"
                :min="0"
                :max="2"
                :step="0.1"
                controls-position="right"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="showProfile ? 8 : 12">
            <el-form-item label="排序" prop="modelSort">
              <el-input-number
                v-model="form.modelSort"
                :min="0"
                controls-position="right"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="showProfile ? 8 : 12">
            <el-form-item label="状态" prop="status">
              <el-radio-group v-model="form.status">
                <el-radio
                  v-for="dict in sys_normal_disable"
                  :key="dict.value"
                  :value="dict.value"
                >{{ dict.label }}</el-radio>
              </el-radio-group>
            </el-form-item>
          </el-col>
          <template v-if="showProfile">
            <el-col :span="24">
              <div class="profile-panel">
                <div class="profile-panel__header">
                  <span class="profile-panel__title">模型能力 Profile</span>
                  <el-button
                    type="primary"
                    link
                    :loading="profileLoading"
                    @click="handleFetchProfile"
                  >获取 Profile</el-button>
                </div>
                <div class="profile-panel__body">
                  <el-row :gutter="20">
                    <el-col :span="12">
                      <el-form-item label="最大输入" prop="maxInputTokens" label-width="110px">
                        <el-input-number
                          v-model="form.maxInputTokens"
                          :min="0"
                          controls-position="right"
                          style="width: 100%"
                          placeholder="最大输入 token（上下文窗口）"
                        />
                      </el-form-item>
                    </el-col>
                    <el-col :span="12">
                      <el-form-item label="最大输出" prop="maxTokens" label-width="110px">
                        <el-input-number
                          v-model="form.maxTokens"
                          :min="0"
                          controls-position="right"
                          style="width: 100%"
                          placeholder="最大输出 token"
                        />
                      </el-form-item>
                    </el-col>
                  </el-row>
                  <el-row :gutter="20" class="profile-flags">
                    <el-col
                      v-for="item in profileFlagFields"
                      :key="item.prop"
                      :span="8"
                    >
                      <el-form-item :label="item.label" :prop="item.prop" label-width="120px">
                        <el-switch
                          v-model="form[item.prop]"
                          active-value="Y"
                          inactive-value="N"
                          inline-prompt
                          active-text="是"
                          inactive-text="否"
                        />
                      </el-form-item>
                    </el-col>
                  </el-row>
                </div>
              </div>
            </el-col>
          </template>
          <el-col :span="24">
            <el-form-item label="备注" prop="remark">
              <el-input
                v-model="form.remark"
                type="textarea"
                :rows="2"
                placeholder="请输入内容"
              />
            </el-form-item>
          </el-col>
        </el-row>
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

<script setup name="AiModel">
import {
  listModel,
  addModel,
  delModel,
  getModel,
  updateModel,
  getModelProfile,
} from "@/api/ai/model";

const { proxy } = getCurrentInstance();
const { ai_provider_type, sys_normal_disable, sys_yes_no, ai_model_type } = proxy.useDict(
  "ai_provider_type",
  "sys_normal_disable",
  "sys_yes_no",
  "ai_model_type",
);

const NO_PROFILE_MODEL_TYPES = ["embedding", "rerank"];
const showProfile = computed(() => !NO_PROFILE_MODEL_TYPES.includes(form.value.modelType));
const profileLoading = ref(false);
const profileFlagFields = [
  { prop: "supportTextInputs", label: "支持文本输入" },
  { prop: "supportImages", label: "支持图像输入" },
  { prop: "supportAudioInputs", label: "支持音频输入" },
  { prop: "supportVideoInputs", label: "支持视频输入" },
  { prop: "supportTextOutputs", label: "支持文本输出" },
  { prop: "supportImageOutputs", label: "支持图像输出" },
  { prop: "supportAudioOutputs", label: "支持音频输出" },
  { prop: "supportVideoOutputs", label: "支持视频输出" },
  { prop: "supportReasoning", label: "支持推理" },
  { prop: "supportToolCall", label: "支持工具调用" },
  { prop: "supportStructuredOutput", label: "支持结构化输出" },
  { prop: "supportImageUrlInputs", label: "支持图像URL输入" },
  { prop: "supportPdfInputs", label: "支持PDF输入" },
  { prop: "supportPdfToolMessage", label: "支持PDF工具消息" },
  { prop: "supportImageToolMessage", label: "支持图像工具消息" },
  { prop: "supportToolChoice", label: "支持工具选择" },
];

const modelList = ref([]);
const open = ref(false);
const loading = ref(true);
const showSearch = ref(true);
const ids = ref([]);
const single = ref(true);
const multiple = ref(true);
const total = ref(0);
const title = ref("");

const data = reactive({
  form: {},
  queryParams: {
    pageNum: 1,
    pageSize: 10,
    modelCode: undefined,
    provider: undefined,
    status: undefined,
  },
  rules: {
    modelCode: [
      { required: true, message: "模型编码不能为空", trigger: "blur" },
    ],
    provider: [
      { required: true, message: "提供商不能为空", trigger: "change" },
    ],
    modelSort: [
      { required: true, message: "模型排序不能为空", trigger: "blur" },
    ],
  },
});

const { queryParams, form, rules } = toRefs(data);

/** 查询列表 */
function getList() {
  loading.value = true;
  listModel(queryParams.value).then((response) => {
    modelList.value = response.rows;
    total.value = response.total;
    loading.value = false;
  });
}

/** 取消按钮 */
function cancel() {
  open.value = false;
  reset();
}

/** 表单重置 */
function reset() {
  form.value = {
    modelId: undefined,
    modelCode: undefined,
    modelName: undefined,
    provider: undefined,
    modelSort: 0,
    apiKey: undefined,
    baseUrl: undefined,
    maxTokens: undefined,
    temperature: undefined,
    supportReasoning: "N",
    supportImages: "N",
    supportTextInputs: "N",
    supportAudioInputs: "N",
    supportVideoInputs: "N",
    supportTextOutputs: "N",
    supportImageOutputs: "N",
    supportAudioOutputs: "N",
    supportVideoOutputs: "N",
    supportToolCall: "N",
    supportToolChoice: "N",
    supportStructuredOutput: "N",
    supportImageUrlInputs: "N",
    supportPdfInputs: "N",
    supportPdfToolMessage: "N",
    supportImageToolMessage: "N",
    maxInputTokens: undefined,
    modelType: undefined,
    status: "0",
    remark: undefined,
  };
  proxy.resetForm("modelRef");
}

/** 搜索按钮操作 */
function handleQuery() {
  queryParams.value.pageNum = 1;
  getList();
}

/** 重置按钮操作 */
function resetQuery() {
  proxy.resetForm("queryRef");
  handleQuery();
}

/** 多选框选中数据 */
function handleSelectionChange(selection) {
  ids.value = selection.map((item) => item.modelId);
  single.value = selection.length != 1;
  multiple.value = !selection.length;
}

/** 新增按钮操作 */
function handleAdd() {
  reset();
  open.value = true;
  title.value = "添加模型";
}

/** 修改按钮操作 */
function handleUpdate(row) {
  reset();
  const modelId = row.modelId || ids.value;
  getModel(modelId).then((response) => {
    form.value = response.data;
    open.value = true;
    title.value = "修改模型";
  });
}

/** 提交按钮 */
function submitForm() {
  proxy.$refs["modelRef"].validate((valid) => {
    if (valid) {
      if (form.value.modelId != undefined) {
        updateModel(form.value).then((response) => {
          proxy.$modal.msgSuccess("修改成功");
          open.value = false;
          getList();
        });
      } else {
        addModel(form.value).then((response) => {
          proxy.$modal.msgSuccess("新增成功");
          open.value = false;
          getList();
        });
      }
    }
  });
}

/** 删除按钮操作 */
function handleDelete(row) {
  const modelIds = row.modelId || ids.value;
  proxy.$modal
    .confirm('是否确认删除模型编号为"' + modelIds + '"的数据项？')
    .then(function () {
      return delModel(modelIds);
    })
    .then(() => {
      getList();
      proxy.$modal.msgSuccess("删除成功");
    })
    .catch(() => {});
}

/** 获取模型Profile */
function handleFetchProfile() {
  if (!form.value.modelCode || !form.value.provider) {
    proxy.$modal.msgWarning("请先填写模型编码和提供商");
    return;
  }
  profileLoading.value = true;
  getModelProfile(form.value.modelCode, form.value.provider, form.value.modelType)
    .then((response) => {
      const profile = response.data;
      if (!profile || Object.values(profile).every((v) => v === null || v === undefined)) {
        proxy.$modal.msgWarning("未获取到模型 Profile，请手动填写");
        return;
      }
      // token：有值才覆盖；能力开关：一律强制回填（null/false → N，true → Y）
      if (profile.maxTokens != null) form.value.maxTokens = profile.maxTokens;
      if (profile.maxInputTokens != null) form.value.maxInputTokens = profile.maxInputTokens;
      const toYN = (v) => (v === "Y" || v === true ? "Y" : "N");
      profileFlagFields.forEach(({ prop }) => {
        form.value[prop] = toYN(profile[prop]);
      });
      proxy.$modal.msgSuccess("Profile 获取成功");
    })
    .catch(() => {
      proxy.$modal.msgWarning("未获取到模型 Profile，请手动填写");
    })
    .finally(() => {
      profileLoading.value = false;
    });
}

/** 模型类型切换时清空Chat/Profile专用字段 */
function handleModelTypeChange(val) {
  if (NO_PROFILE_MODEL_TYPES.includes(val)) {
    form.value.temperature = undefined;
    form.value.maxTokens = undefined;
    form.value.maxInputTokens = undefined;
    form.value.supportReasoning = "N";
    form.value.supportImages = "N";
    form.value.supportToolCall = "N";
    form.value.supportToolChoice = "N";
    form.value.supportStructuredOutput = "N";
    form.value.supportTextInputs = "N";
    form.value.supportAudioInputs = "N";
    form.value.supportVideoInputs = "N";
    form.value.supportTextOutputs = "N";
    form.value.supportImageOutputs = "N";
    form.value.supportAudioOutputs = "N";
    form.value.supportVideoOutputs = "N";
    form.value.supportImageUrlInputs = "N";
    form.value.supportPdfInputs = "N";
    form.value.supportPdfToolMessage = "N";
    form.value.supportImageToolMessage = "N";
  }
}

getList();
</script>

<style scoped>
.model-form :deep(.el-form-item) {
  margin-bottom: 14px;
}
.model-form :deep(.el-radio) {
  margin-right: 12px;
}
.profile-panel {
  margin-bottom: 6px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  background: var(--el-fill-color-blank);
  overflow: hidden;
}
.profile-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-light);
}
.profile-panel__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.profile-panel__body {
  max-height: 260px;
  overflow-y: auto;
  padding: 14px 14px 2px;
}
.profile-flags :deep(.el-form-item) {
  margin-bottom: 10px;
}
.profile-flags :deep(.el-form-item__content) {
  justify-content: flex-start;
}
.profile-flags :deep(.el-form-item__label) {
  white-space: nowrap;
}
</style>
