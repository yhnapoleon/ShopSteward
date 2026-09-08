<script setup lang="ts">
import { init, use, graphic, type EChartsCoreOption } from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, MarkLineComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'
import { money } from '~/utils/presentation'
use([BarChart, LineChart, GridComponent, TooltipComponent, MarkLineComponent, SVGRenderer])
const props = defineProps<{
  kind: 'cash' | 'sales'
  points: { id: string; label: string; value: number; detail?: string }[]
  monetary?: boolean
  floor?: number
  label: string
}>()
const emit = defineEmits<{ select: [index: number] }>()
const root = ref<HTMLElement>()
let chart: ReturnType<typeof init> | undefined
let observer: ResizeObserver | undefined
let media: MediaQueryList | undefined
let focusIndex = -1
const valueLabel = (v: number) =>
  props.kind === 'cash' || props.monetary ? money(v) : `${v.toLocaleString('zh-CN')} 件`
function draw() {
  if (!chart) return
  const cash = props.kind === 'cash'
  const scale = cash || props.monetary ? 100 : 1
  const data = props.points.map((p) => p.value / scale)
  const maximum = Math.max(...data, 1, (cash ? props.floor || 0 : 0) / scale)
  const magnitude = 10 ** Math.floor(Math.log10(maximum))
  const normalized = maximum / magnitude
  const top = magnitude * (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10)
  const option: EChartsCoreOption = {
    animation: !media?.matches,
    animationDuration: 550,
    animationDurationUpdate: 220,
    animationEasing: 'cubicOut',
    animationEasingUpdate: 'cubicOut',
    textStyle: {
      fontFamily: '-apple-system, BlinkMacSystemFont, PingFang SC, Microsoft YaHei, sans-serif',
      color: '#626d77',
    },
    grid: { left: 4, right: cash ? 24 : 12, top: 25, bottom: 10, containLabel: true },
    tooltip: {
      trigger: 'axis',
      renderMode: 'richText',
      confine: true,
      backgroundColor: 'rgba(252,254,255,.97)',
      borderColor: 'rgba(211,222,235,.85)',
      borderWidth: 1,
      padding: [12, 16],
      textStyle: { color: '#28343e', fontSize: 14, lineHeight: 23 },
      shadowBlur: 24,
      shadowColor: 'rgba(53,79,109,.12)',
      shadowOffsetY: 6,
      axisPointer: { type: 'line', lineStyle: { color: 'rgba(45,125,206,.24)', type: 'solid' } },
      formatter: (params: unknown) => {
        const p = (params as { dataIndex: number }[])[0]
        const point = p && props.points[p.dataIndex]
        return point ? `${point.detail || point.label}\n${valueLabel(point.value)}` : ''
      },
    },
    xAxis: {
      type: 'category',
      data: props.points.map((p) => p.label),
      boundaryGap: !cash,
      axisLine: { show: !cash, lineStyle: { color: '#d9e1e8' } },
      axisTick: { show: false },
      axisLabel: {
        color: '#667785',
        fontSize: 13,
        margin: 16,
        hideOverlap: true,
        interval: 'auto',
      },
      axisPointer: { snap: true },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: top,
      minInterval: props.monetary ? undefined : 1,
      splitNumber: 2,
      axisLabel: {
        fontSize: 13,
        color: '#778592',
        formatter: (v: number) => (v >= 10000 ? `${v / 10000}万` : v.toLocaleString('zh-CN')),
      },
      splitLine: {
        lineStyle: {
          color: cash ? 'rgba(88,119,144,.075)' : 'rgba(88,119,144,.1)',
          type: 'dashed',
        },
      },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: cash
      ? [
          {
            type: 'line',
            step: 'middle',
            data,
            connectNulls: false,
            symbol: 'circle',
            symbolSize: props.points.length === 1 ? 9 : 6,
            label: {
              show: true,
              position: 'top',
              color: '#57738b',
              fontSize: 13,
              distance: 9,
              formatter: (p: { value: unknown }) => Number(p.value).toLocaleString('zh-CN'),
            },
            showSymbol: true,
            lineStyle: {
              width: 3.5,
              color: new graphic.LinearGradient(0, 0, 1, 0, [
                { offset: 0, color: '#3fbfc6' },
                { offset: 1, color: '#367ee1' },
              ]),
              shadowColor: 'rgba(65,168,219,.2)',
              shadowBlur: 10,
            },
            itemStyle: { color: '#398cce', borderColor: '#f5fcff', borderWidth: 2 },
            areaStyle: {
              color: new graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: 'rgba(57,177,211,.22)' },
                { offset: 1, color: 'rgba(92,170,236,0)' },
              ]),
            },
            emphasis: {
              scale: 1.8,
              itemStyle: { shadowBlur: 14, shadowColor: 'rgba(44,143,230,.4)' },
            },
            markLine:
              props.floor == null
                ? undefined
                : {
                    symbol: 'none',
                    silent: true,
                    data: [{ yAxis: props.floor / 100 }],
                    label: { show: false },
                    lineStyle: { color: '#a7b8b9', type: 'dashed', width: 1 },
                  },
          },
        ]
      : [
          {
            type: 'bar',
            data,
            barMaxWidth: 36,
            barCategoryGap: '55%',
            itemStyle: {
              borderRadius: [5, 5, 0, 0],
              color: new graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: '#60d5e2' },
                { offset: 0.48, color: '#4aa9ed' },
                { offset: 1, color: '#356eda' },
              ]),
              decal: {
                symbol: 'rect',
                symbolSize: 1,
                dashArrayX: [1, 0],
                dashArrayY: [1, 7],
                rotation: -Math.PI / 4,
                color: 'rgba(255,255,255,.22)',
              },
              shadowBlur: 10,
              shadowColor: 'rgba(60,143,220,.12)',
            },
            emphasis: {
              focus: 'self',
              itemStyle: { shadowBlur: 18, shadowColor: 'rgba(47,138,232,.28)' },
            },
          },
        ],
  }
  chart.setOption(option, { notMerge: true })
}
function keyboard(e: KeyboardEvent) {
  if (!props.points.length) return
  if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) {
    e.preventDefault()
    focusIndex =
      e.key === 'Home'
        ? 0
        : e.key === 'End'
          ? props.points.length - 1
          : Math.max(
              0,
              Math.min(props.points.length - 1, focusIndex + (e.key === 'ArrowLeft' ? -1 : 1)),
            )
    chart?.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: focusIndex })
  } else if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    emit('select', focusIndex < 0 ? props.points.length - 1 : focusIndex)
  } else if (e.key === 'Escape') chart?.dispatchAction({ type: 'hideTip' })
}
onMounted(() => {
  if (!root.value) return
  media = matchMedia('(prefers-reduced-motion: reduce)')
  chart = init(root.value, undefined, { renderer: 'svg' })
  chart.on('click', (params) => {
    if (params.componentType === 'series' && typeof params.dataIndex === 'number')
      emit('select', params.dataIndex)
  })
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(root.value)
  media.addEventListener('change', draw)
  draw()
})
watch(() => [props.points, props.monetary, props.floor], draw, { deep: true })
onUnmounted(() => {
  observer?.disconnect()
  media?.removeEventListener('change', draw)
  chart?.dispose()
})
</script>
<template>
  <div
    ref="root"
    class="overview-chart"
    :class="`overview-chart--${kind}`"
    role="group"
    :aria-label="label + '。左右方向键选择，回车查看明细。'"
    tabindex="0"
    @keydown="keyboard"
  />
</template>
