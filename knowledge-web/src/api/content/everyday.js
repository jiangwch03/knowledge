import request from '@/utils/request'

const contentBase = import.meta.env.VITE_APP_CONTENT_API || '/dev-content-api'

export function listEverydayWord(query) {
  return request({
    url: '/everyday-word/list',
    method: 'get',
    params: query,
    baseURL: contentBase
  })
}

export function addEverydayWord(word) {
  return request({
    url: '/everyday-word/add',
    method: 'post',
    data: { word },
    baseURL: contentBase
  })
}

export function initEverydayWord() {
  return request({
    url: '/everyday-word/init',
    method: 'post',
    baseURL: contentBase,
    timeout: 180000
  })
}

export function removeEverydayWord(wordIds) {
  return request({
    url: '/everyday-word/remove',
    method: 'post',
    data: { wordIds },
    baseURL: contentBase
  })
}
