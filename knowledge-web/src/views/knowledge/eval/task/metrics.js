export const metricLabels = {
  context_recall: '召回率',
  context_precision: '精确度',
  faithfulness: '忠实度',
  answer_relevancy: '相关性'
}

export function parseSummary(raw) {
  if (!raw) return null
  if (typeof raw === 'object') return raw
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export function formatProgress(raw) {
  const summary = parseSummary(raw)
  if (!summary) return '-'
  const total = summary.item_total ?? summary.itemTotal
  const done = summary.item_done ?? summary.itemDone
  if (total == null) return '-'
  return `${done || 0}/${total}`
}

export function metricNumber(raw, key) {
  const summary = parseSummary(raw)
  if (!summary || summary[key] == null || summary[key] === '') return null
  const value = Number(summary[key])
  return Number.isFinite(value) ? value : null
}

export function formatMetric(raw, key) {
  const value = metricNumber(raw, key)
  return value == null ? '-' : value.toFixed(3)
}

export function hasMetric(raw) {
  return Object.keys(metricLabels).some((key) => metricNumber(raw, key) != null)
}

export function runStatusLabel(status) {
  const map = { PENDING: '待执行', RUNNING: '执行中', SUCCESS: '成功', FAILED: '失败' }
  return map[status] || status || '-'
}
