import request from "@/utils/request";

// 查询模型功能适配列表
export function listAdapter(query) {
  return request({
    url: "/ai/model/function-adapter/list",
    method: "get",
    params: query,
  });
}

// 新增模型功能适配
export function addAdapter(data) {
  return request({
    url: "/ai/model/function-adapter",
    method: "post",
    data: data,
  });
}

// 修改模型功能适配
export function updateAdapter(adapterId, data) {
  return request({
    url: "/ai/model/function-adapter/" + adapterId,
    method: "put",
    data: data,
  });
}

// 删除模型功能适配
export function delAdapter(adapterId) {
  return request({
    url: "/ai/model/function-adapter/" + adapterId,
    method: "delete",
  });
}

// 根据参数ID获取模型配置
export function getAdapterConfig(paramId) {
  return request({
    url: "/ai/model/function-adapter/" + paramId + "/model",
    method: "get",
  });
}
