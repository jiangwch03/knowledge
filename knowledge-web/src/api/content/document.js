import request from "@/utils/request";

const contentBase = import.meta.env.VITE_APP_CONTENT_API || "/dev-content-api";

// 获取文档状态选项
export function getDocumentStatusOptions() {
  return request({
    url: "/document-parse/status-options",
    method: "get",
    baseURL: contentBase,
  });
}

// 获取文档下一版本号
export function getNextVersion(docTitle) {
  return request({
    url: "/document-parse/next-version",
    method: "get",
    params: { doc_title: docTitle },
    baseURL: contentBase,
  });
}

// 上传文档
export function uploadDocument(data) {
  return request({
    url: "/document-parse/upload",
    method: "post",
    data: data,
    baseURL: contentBase,
    headers: { "Content-Type": "multipart/form-data" },
  });
}

// 查询文档上传记录列表
export function listDocumentRecord(query) {
  return request({
    url: "/document-parse/list",
    method: "get",
    params: query,
    baseURL: contentBase,
  });
}

// 删除上传任务
export function delDocumentRecord(taskId) {
  return request({
    url: "/document-parse/" + taskId,
    method: "delete",
    baseURL: contentBase,
  });
}

// TXT 转 Markdown
export function txtToMarkdown(data) {
  return request({
    url: "/document/txt/convert",
    method: "post",
    data: data,
    baseURL: contentBase,
  });
}

// 获取解析任务详情
export function getParseTask(parseTaskId) {
  return request({
    url: "/document-parse/parse-task/" + parseTaskId,
    method: "get",
    baseURL: contentBase,
  });
}

// 获取解析任务分段明细
export function getParseTaskDetails(parseTaskId) {
  return request({
    url: "/document-parse/parse-task/" + parseTaskId + "/details",
    method: "get",
    baseURL: contentBase,
  });
}

// 获取上传任务下的所有解析任务
export function getParseTasksByRecord(taskId) {
  return request({
    url: "/document-parse/" + taskId + "/parse-tasks",
    method: "get",
    baseURL: contentBase,
  });
}

// 用户决策
export function handleParseDecision(parseTaskId, data) {
  return request({
    url: "/document-parse/parse-task/" + parseTaskId + "/decision",
    method: "post",
    data: data,
    baseURL: contentBase,
  });
}

// 预览文档（上传可省略 fileId；爬取须传 fileId）
export function previewDocument(docId, params = {}) {
  return request({
    url: "/document/" + docId + "/preview",
    method: "get",
    params,
    baseURL: contentBase,
    responseType: "text",
  });
}

// 下载文档（单文件 / 多 fileIds / all）
export function downloadDocument(docId, params = {}) {
  return request({
    url: "/document/" + docId + "/download",
    method: "get",
    params,
    baseURL: contentBase,
    responseType: "blob",
  });
}

// 文档文件列表（选页预览/下载）
export function listDocumentFiles(docId) {
  return request({
    url: "/document/" + docId + "/files",
    method: "get",
    baseURL: contentBase,
  });
}
