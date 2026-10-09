import request from '@/utils/request'

const contentBase = import.meta.env.VITE_APP_CONTENT_API || '/dev-content-api'

export function listTopic(query) {
  return request({
    url: '/topic/list',
    method: 'get',
    params: query,
    baseURL: contentBase
  })
}

export function getTopic(topicId) {
  return request({
    url: '/topic/' + topicId,
    method: 'get',
    baseURL: contentBase
  })
}

export function addTopic(data) {
  return request({
    url: '/topic',
    method: 'post',
    data,
    baseURL: contentBase
  })
}

export function updateTopic(topicId, data) {
  return request({
    url: '/topic/' + topicId,
    method: 'put',
    data,
    baseURL: contentBase
  })
}

export function retryTopic(topicId) {
  return request({
    url: '/topic/' + topicId + '/retry',
    method: 'post',
    baseURL: contentBase
  })
}

export function deleteTopic(topicId) {
  return request({
    url: '/topic/' + topicId,
    method: 'delete',
    baseURL: contentBase
  })
}
