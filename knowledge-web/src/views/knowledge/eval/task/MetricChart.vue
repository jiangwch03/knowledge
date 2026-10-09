<template>
  <div ref="el" class="eval-metric-chart" :style="{ height: `${height}px` }" />
</template>

<script setup>
import * as echarts from 'echarts'
import { onMounted, onUnmounted, ref, watch } from 'vue'

const props = defineProps({
  categories: { type: Array, default: () => [] },
  series: { type: Array, default: () => [] },
  type: { type: String, default: 'bar' },
  title: { type: String, default: '' },
  color: { type: String, default: '' },
  height: { type: Number, default: 320 }
})

const el = ref(null)
let chart
let observer

const colors = ['#409EFF', '#67C23A', '#E6A23C', '#F56C6C']

function option() {
  const isBar = props.type !== 'line'
  const showLegend = props.series.length > 1
  return {
    color: props.color ? [props.color] : colors,
    title: props.title
      ? { text: props.title, left: 8, top: 0, textStyle: { fontSize: 14, fontWeight: 600 } }
      : undefined,
    tooltip: {
      trigger: 'axis',
      valueFormatter: (value) => (value == null || value === '' ? '-' : Number(value).toFixed(3))
    },
    legend: showLegend ? { top: 0 } : { show: false },
    grid: { left: 48, right: 16, top: props.title || showLegend ? 36 : 16, bottom: props.categories.length > 12 ? 64 : 28 },
    xAxis: {
      type: 'category',
      data: props.categories,
      axisTick: { alignWithLabel: true }
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 1,
      axisLabel: { formatter: (value) => Number(value).toFixed(1) }
    },
    dataZoom: props.categories.length > 12 ? [{ type: 'slider', bottom: 8, height: 18 }] : [],
    series: props.series.map((item) => ({
      name: item.name,
      type: isBar ? 'bar' : 'line',
      data: item.data,
      barMaxWidth: 22,
      showSymbol: !isBar,
      connectNulls: false
    }))
  }
}

function render() {
  if (!el.value) return
  if (!chart) chart = echarts.init(el.value)
  chart.setOption(option(), true)
}

onMounted(() => {
  render()
  observer = new ResizeObserver(() => chart && chart.resize())
  observer.observe(el.value)
})

watch(() => [props.categories, props.series, props.type, props.title, props.color, props.height], render, { deep: true })

onUnmounted(() => {
  observer && observer.disconnect()
  chart && chart.dispose()
  chart = null
})
</script>

<style scoped>
.eval-metric-chart {
  width: 100%;
}
</style>
