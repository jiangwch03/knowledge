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

// 删除上传记录
export function delDocumentRecord(recordId) {
  return request({
    url: "/document-parse/" + recordId,
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

// 获取上传记录下的所有解析任务
export function getParseTasksByRecord(recordId) {
  return request({
    url: "/document-parse/" + recordId + "/parse-tasks",
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

// 预览文档
export function previewDocument(docId) {
  return request({
    url: "/document/" + docId + "/preview",
    method: "get",
    baseURL: contentBase,
    responseType: "text",
  });
}

// 下载文档
export function downloadDocument(docId) {
  return request({
    url: "/document/" + docId + "/download",
    method: "get",
    baseURL: contentBase,
    responseType: "blob",
  });
}
