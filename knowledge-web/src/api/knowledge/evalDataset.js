import request from '@/utils/request'

export function listEvalDataset(query) {
  return request({
    url: '/rag/eval/dataset/list',
    method: 'get',
    params: query
  })
}

export function addEvalDataset(data) {
  return request({
    url: '/rag/eval/dataset',
    method: 'post',
    data
  })
}

export function getEvalDataset(datasetId) {
  return request({
    url: '/rag/eval/dataset/' + datasetId,
    method: 'get'
  })
}

export function listEvalDatasetItems(datasetId, query) {
  return request({
    url: '/rag/eval/dataset/' + datasetId + '/items',
    method: 'get',
    params: query
  })
}

export function updateEvalDatasetItem(itemId, data) {
  return request({
    url: '/rag/eval/dataset/item/' + itemId,
    method: 'put',
    data
  })
}
