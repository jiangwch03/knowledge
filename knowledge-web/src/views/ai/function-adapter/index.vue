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
      <el-table-column label="业务功能点" prop="functionPoint" :show-overflow-tooltip="true" />
      <el-table-column label="参数ID" prop="paramId" width="160" :show-overflow-tooltip="true" />
      <el-table-column label="模型编码" prop="modelCode" width="160" />
      <el-table-column label="模型名称" prop="modelName" width="160" />
      <el-table-column label="创建时间" prop="createTime" width="160" align="center">
        <template #default="scope">
          <span>{{ parseTime(scope.row.createTime) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" align="center" width="150" class-name="small-padding fixed-width">
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
          <el-input v-model="form.paramId" placeholder="请输入参数ID，如 txt_to_markdown" />
        </el-form-item>
        <el-form-item label="选择模型" prop="modelId">
          <el-select
            v-model="form.modelId"
            placeholder="请选择模型"
            style="width: 100%"
            @change="handleModelChange"
          >
            <el-option
              v-for="model in modelOptions"
              :key="model.modelId"
              :label="model.modelName + ' (' + model.modelCode + ')'"
              :value="model.modelId"
            />
          </el-select>
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

const adapterList = ref([]);
const loading = ref(false);
const showSearch = ref(true);
const total = ref(0);
const open = ref(false);
const title = ref("");
const modelOptions = ref([]);

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
    modelId: [
      { required: true, message: "模型不能为空", trigger: "change" },
    ],
  },
});

const { queryParams, form, rules } = toRefs(data);

function getList() {
  loading.value = true;
  listAdapter(queryParams.value).then((response) => {
    adapterList.value = response.rows;
    total.value = response.total;
    loading.value = false;
  });
}

function loadModelOptions() {
  listModelAll().then((response) => {
    modelOptions.value = response.data || [];
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
    modelId: undefined,
    modelCode: undefined,
    modelName: undefined,
  };
  proxy.resetForm("adapterRef");
}

function handleModelChange(modelId) {
  const selected = modelOptions.value.find((item) => item.modelId === modelId);
  if (selected) {
    form.value.modelCode = selected.modelCode;
    form.value.modelName = selected.modelName;
  }
}

function handleAdd() {
  reset();
  open.value = true;
  title.value = "新增模型功能适配";
}

function handleUpdate(row) {
  reset();
  form.value = {
    adapterId: row.adapterId,
    functionPoint: row.functionPoint,
    paramId: row.paramId,
    modelId: row.modelId,
    modelCode: row.modelCode,
    modelName: row.modelName,
  };
  open.value = true;
  title.value = "修改模型功能适配";
}

function submitForm() {
  proxy.$refs["adapterRef"].validate((valid) => {
    if (!valid) return;
    if (form.value.adapterId != undefined) {
      updateAdapter(form.value.adapterId, form.value).then(() => {
        proxy.$modal.msgSuccess("修改成功");
        open.value = false;
        getList();
      });
    } else {
      addAdapter(form.value).then(() => {
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
