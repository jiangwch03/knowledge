import request from "@/utils/request";
import { getToken } from "@/utils/auth";

const retrievalBase = import.meta.env.VITE_APP_RETRIEVAL_API || "/dev-retrieval-api";

// ==================== 会话管理 ====================

export function listQaSession(query) {
  return request({
    url: "/qa/session/list",
    method: "get",
    params: query,
    baseURL: retrievalBase,
  });
}

export function addQaSession(data) {
  return request({
    url: "/qa/session",
    method: "post",
    data: data,
    baseURL: retrievalBase,
  });
}

export function getQaSession(sessionId) {
  return request({
    url: "/qa/session/" + sessionId,
    method: "get",
    baseURL: retrievalBase,
  });
}

export function renameQaSession(sessionId, data) {
  return request({
    url: "/qa/session/" + sessionId + "/rename",
    method: "put",
    data: data,
    baseURL: retrievalBase,
  });
}

export function closeQaSession(sessionId) {
  return request({
    url: "/qa/session/" + sessionId + "/close",
    method: "put",
    baseURL: retrievalBase,
  });
}

export function delQaSession(sessionId) {
  return request({
    url: "/qa/session/" + sessionId,
    method: "delete",
    baseURL: retrievalBase,
  });
}

// ==================== 聊天 ====================

export function listQaModels() {
  return request({
    url: "/qa/chat/models",
    method: "get",
    baseURL: retrievalBase,
  });
}

export function listQaMessages(sessionId, query) {
  return request({
    url: "/qa/chat/" + sessionId + "/messages",
    method: "get",
    params: query,
    baseURL: retrievalBase,
  });
}

/** SSE 发送消息（fetch streaming） */
export async function sendQaMessageStream(sessionId, data, { signal } = {}) {
  const response = await fetch(`${retrievalBase}/qa/chat/${sessionId}/message`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer " + getToken(),
    },
    body: JSON.stringify(data),
    signal,
  });
  return response;
}

export function searchKnowledge(data) {
  return request({
    url: "/retrieval/search",
    method: "post",
    data: data,
    baseURL: retrievalBase,
  });
}
