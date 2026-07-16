import request from "@/utils/request";

const contentBase = import.meta.env.VITE_APP_CONTENT_API || "/dev-content-api";

// ==================== 会话管理 ====================

// 查询会话列表（仅查本人）
export function listCrawlerSession(query) {
  return request({
    url: "/crawler/session/list",
    method: "get",
    params: query,
    baseURL: contentBase,
  });
}

// 查询会话列表（数据权限范围）
export function listAllCrawlerSession(query) {
  return request({
    url: "/crawler/session/list-all",
    method: "get",
    params: query,
    baseURL: contentBase,
  });
}

// 创建会话
export function addCrawlerSession(data) {
  return request({
    url: "/crawler/session",
    method: "post",
    data: data,
    baseURL: contentBase,
  });
}

// 获取会话详情
export function getCrawlerSession(sessionId) {
  return request({
    url: "/crawler/session/" + sessionId,
    method: "get",
    baseURL: contentBase,
  });
}

// 重命名会话
export function renameCrawlerSession(sessionId, data) {
  return request({
    url: "/crawler/session/" + sessionId + "/rename",
    method: "put",
    data: data,
    baseURL: contentBase,
  });
}

// 关闭会话
export function closeCrawlerSession(sessionId) {
  return request({
    url: "/crawler/session/" + sessionId + "/close",
    method: "put",
    baseURL: contentBase,
  });
}

// 删除会话
export function delCrawlerSession(sessionId) {
  return request({
    url: "/crawler/session/" + sessionId,
    method: "delete",
    baseURL: contentBase,
  });
}

// ==================== 聊天交互 ====================

// 获取网页爬取Agent可用模型列表
export function listCrawlerModels() {
  return request({
    url: "/crawler/chat/models",
    method: "get",
    baseURL: contentBase,
  });
}

// 发送聊天消息（SSE 流式响应）
export function sendCrawlerMessage(sessionId, data) {
  return request({
    url: "/crawler/chat/" + sessionId + "/message",
    method: "post",
    data: data,
    baseURL: contentBase,
    responseType: "stream",
  });
}

// 恢复中断（SSE 流式响应）- 用户对中断弹框做出决策后调用
export function resumeCrawlerSession(sessionId, data) {
  return request({
    url: "/crawler/chat/" + sessionId + "/resume",
    method: "post",
    data: data,
    baseURL: contentBase,
    responseType: "stream",
  });
}

// 确认策略配置
export function confirmCrawlerStrategy(sessionId, data) {
  return request({
    url: "/crawler/chat/" + sessionId + "/confirm",
    method: "post",
    data: data,
    baseURL: contentBase,
  });
}

// 获取历史消息列表
export function listCrawlerMessages(sessionId, query) {
  return request({
    url: "/crawler/chat/" + sessionId + "/messages",
    method: "get",
    params: query,
    baseURL: contentBase,
  });
}

// ==================== 任务管理 ====================

// 查询任务列表
export function listCrawlTask(query) {
  return request({
    url: "/crawler/task/list",
    method: "get",
    params: query,
    baseURL: contentBase,
  });
}

// 获取任务详情
export function getCrawlTask(taskId) {
  return request({
    url: "/crawler/task/" + taskId,
    method: "get",
    baseURL: contentBase,
  });
}

// 获取失败URL列表
export function listCrawlFailedUrls(taskId, query) {
  return request({
    url: "/crawler/task/" + taskId + "/failed-urls",
    method: "get",
    params: query,
    baseURL: contentBase,
  });
}

// 获取任务URL记录列表（支持按状态过滤）
export function listCrawlUrlRecords(taskId, query) {
  return request({
    url: "/crawler/task/" + taskId + "/url-records",
    method: "get",
    params: query,
    baseURL: contentBase,
  });
}

// 删除任务
export function delCrawlTask(taskId) {
  return request({
    url: "/crawler/task/" + taskId,
    method: "delete",
    baseURL: contentBase,
  });
}

// 暂停任务
export function pauseCrawlTask(taskId) {
  return request({
    url: "/crawler/task/" + taskId + "/pause",
    method: "post",
    baseURL: contentBase,
  });
}

// 合并已爬内容（放弃失败URL，将成功页面合入文档）
export function mergeCrawlResults(taskId) {
  return request({
    url: "/crawler/task/" + taskId + "/merge",
    method: "post",
    baseURL: contentBase,
  });
}

// 恢复暂停的任务
export function resumeCrawlTask(taskId) {
  return request({
    url: "/crawler/task/" + taskId + "/resume",
    method: "post",
    baseURL: contentBase,
  });
}

// 获取会话关联任务
export function listCrawlTasksBySession(sessionId) {
  return request({
    url: "/crawler/task/session/" + sessionId,
    method: "get",
    baseURL: contentBase,
  });
}

// 获取任务状态选项
export function getTaskStatusOptions() {
  return request({
    url: "/crawler/task/status-options",
    method: "get",
    baseURL: contentBase,
  });
}

// 获取错误码选项
export function getTaskErrorCodeOptions() {
  return request({
    url: "/crawler/task/error-code-options",
    method: "get",
    baseURL: contentBase,
  });
}

// ==================== 文档管理 ====================

// 查询爬取文档列表
export function listCrawlerDocument(query) {
  return request({
    url: "/crawler/document/list",
    method: "get",
    params: query,
    baseURL: contentBase,
  });
}

// 预览爬取文档
export function previewCrawlerDocument(docId) {
  return request({
    url: "/crawler/document/" + docId + "/preview",
    method: "get",
    baseURL: contentBase,
    responseType: "text",
  });
}

// 下载爬取文档
export function downloadCrawlerDocument(docId) {
  return request({
    url: "/crawler/document/" + docId + "/download",
    method: "get",
    baseURL: contentBase,
    responseType: "blob",
  });
}
