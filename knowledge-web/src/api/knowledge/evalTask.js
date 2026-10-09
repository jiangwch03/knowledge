import request from '@/utils/request'

export function listEvalTask(query) {
  return request({
    url: '/rag/eval/task/list',
    method: 'get',
    params: query
  })
}

export function addEvalTask(data) {
  return request({
    url: '/rag/eval/task',
    method: 'post',
    data
  })
}

export function swapEvalTaskDataset(evalTaskId, data) {
  return request({
    url: '/rag/eval/task/' + evalTaskId + '/dataset',
    method: 'put',
    data
  })
}

export function startEvalRun(evalTaskId) {
  return request({
    url: '/rag/eval/task/' + evalTaskId + '/run',
    method: 'post'
  })
}

export function listEvalRuns(evalTaskId, query) {
  return request({
    url: '/rag/eval/task/' + evalTaskId + '/runs',
    method: 'get',
    params: query
  })
}

export function getEvalRunReport(runId) {
  return request({
    url: '/rag/eval/task/run/' + runId + '/report',
    method: 'get'
  })
}

export function publishEvalTask(evalTaskId) {
  return request({
    url: '/rag/eval/task/' + evalTaskId + '/publish',
    method: 'post'
  })
}
