import request from "@/utils/request";

const contentBase = import.meta.env.VITE_APP_CONTENT_API || "/dev-content-api";

/** 获取切分策略元数据 */
export function getEmbeddingStrategies() {
  return request({
    url: "/embedding/strategies",
    method: "get",
    baseURL: contentBase,
  });
}

/** 获取 Embedding 模型信息（只读） */
export function getEmbeddingModelInfo() {
  return request({
    url: "/embedding/model-info",
    method: "get",
    baseURL: contentBase,
  });
}

/** 切分效果预览（不落库） */
export function previewEmbedding(data) {
  return request({
    url: "/embedding/preview",
    method: "post",
    data,
    baseURL: contentBase,
  });
}

/** 创建 Embedding 任务 */
export function createEmbeddingTask(data) {
  return request({
    url: "/embedding/tasks",
    method: "post",
    data,
    baseURL: contentBase,
  });
}

/** 分页查询 Embedding 任务 */
export function listEmbeddingTasks(query) {
  return request({
    url: "/embedding/tasks",
    method: "get",
    params: query,
    baseURL: contentBase,
  });
}

/** 获取 Embedding 任务详情 */
export function getEmbeddingTask(taskId) {
  return request({
    url: "/embedding/tasks/" + taskId,
    method: "get",
    baseURL: contentBase,
  });
}

/** 分页查询任务切分片段 */
export function listEmbeddingSegments(taskId, query) {
  return request({
    url: "/embedding/tasks/" + taskId + "/segments",
    method: "get",
    params: query,
    baseURL: contentBase,
  });
}

/** 重试失败的 Embedding 任务 */
export function retryEmbeddingTask(taskId) {
  return request({
    url: "/embedding/tasks/" + taskId + "/retry",
    method: "post",
    baseURL: contentBase,
  });
}

/** 删除 Embedding 任务（进行中/失败/未发布 canary） */
export function deleteEmbeddingTask(taskId) {
  return request({
    url: "/embedding/tasks/" + taskId,
    method: "delete",
    baseURL: contentBase,
  });
}
