<script setup lang="ts">
import { money } from '~/utils/presentation'
const props = defineProps<{ open: boolean }>(),
  emit = defineEmits<{ close: []; start: []; quote: [] }>()
const { s, stock, offer, product, mission } = useShop()
const layer = ref<HTMLDialogElement>(),
  main = ref<HTMLElement>(),
  anchor = ref<HTMLElement>()
const echoes = ref<HTMLElement>()
let origin: HTMLElement | null = null,
  animations: Animation[] = []
let serial = 0
async function close() {
  const n = ++serial
  const d = layer.value
  if (!d?.open) return
  animations.forEach((a) => a.cancel())
  animations = []
  if (main.value) {
    const r = main.value.getBoundingClientRect(),
      o = origin?.getBoundingClientRect()
    const duration = matchMedia('(prefers-reduced-motion:reduce)').matches ? 0 : 350
    const a = main.value.animate(
      [
        { opacity: 1, transform: 'none' },
        {
          opacity: 0,
          transform: o
            ? `translate(${o.left - r.left}px,${o.top - r.top}px) scale(${o.width / r.width},.1)`
            : 'scale(.94)',
        },
      ],
      { duration, easing: 'ease-in', fill: 'forwards' },
    )
    await a.finished.catch(() => {})
    if (n !== serial) return
    a.cancel()
  }
  d.close()
  origin?.isConnected && origin.focus({ preventScroll: true })
  emit('close')
}
watch(
  () => props.open,
  async (open) => {
    if (!open) {
      if (layer.value?.open) void close()
      return
    }
    const n = ++serial
    await nextTick()
    origin = document.activeElement as HTMLElement
    layer.value?.showModal()
    if (!main.value) return
    const o = origin.getBoundingClientRect(),
      r = main.value.getBoundingClientRect()
    if (anchor.value)
      Object.assign(anchor.value.style, {
        left: o.left + 'px',
        top: o.top + 'px',
        width: o.width + 'px',
        height: o.height + 'px',
      })
    if (echoes.value)
      Object.assign(echoes.value.style, {
        right: 'auto',
        left: Math.max(16, Math.min(innerWidth - 252, o.right - 236)) + 'px',
        top: Math.max(16, Math.min(innerHeight - 184, o.bottom + 20)) + 'px',
      })
    const reduced = matchMedia('(prefers-reduced-motion:reduce)').matches
    main.value.inert = true
    const a = main.value.animate(
      [
        {
          opacity: 0,
          transform: `translate(${o.left - r.left}px,${o.top - r.top}px) scale(${o.width / r.width},.12)`,
        },
        { opacity: 1, transform: 'none' },
      ],
      { duration: reduced ? 100 : 720, easing: 'cubic-bezier(.22,1,.36,1)', fill: 'both' },
    )
    animations = [a]
    await a.finished.catch(() => {})
    if (n === serial && main.value) {
      main.value.inert = false
      main.value.focus({ preventScroll: true })
    }
  },
)
onUnmounted(() => animations.forEach((a) => a.cancel()))
async function start() {
  await close()
  emit('start')
}
async function quote() {
  await close()
  emit('quote')
}
</script>
<template>
  <dialog ref="layer" class="goal-deck" aria-labelledby="deck-title" @cancel.prevent="close">
    <div class="deck-scrim" @click="close" />
    <button ref="anchor" class="deck-anchor" aria-label="收回委托入口" @click="close">
      <AppIcon name="x" />交给我一件事
    </button>
    <div ref="echoes" class="deck-echoes" aria-hidden="true">
      <div class="deck-echo">
        <AppIcon name="file-text" /><span>报价资料整理<small>单位、包装与来源</small></span>
      </div>
      <div class="deck-echo">
        <AppIcon name="orbit" /><span>活动备货跟进<small>每笔采购由你确认</small></span>
      </div>
    </div>
    <section ref="main" class="deck-main" tabindex="-1">
      <div class="deck-topline">
        <span class="tag">当前可使用的两件事</span
        ><button class="icon-btn" aria-label="收起委托卡片" @click="close">
          <AppIcon name="x" />
        </button>
      </div>
      <h2 id="deck-title">把这次备货交代清楚。</h2>
      <p>确认下面的范围后建立跟进委托。开始跟进不会自动采购。</p>
      <div class="intake-scope">
        <div class="detail-row">
          <span>商品</span><b>{{ product?.name || '请先选择示例店铺' }}</b>
        </div>
        <div class="detail-row"><span>目标</span><b>比较活动备货方案，跟进到货与需求变化</b></div>
        <div class="detail-row">
          <span>现金底线</span><b>{{ money(mission?.policy.cash_floor_minor ?? 30000) }}</b>
        </div>
        <div class="detail-row">
          <span>当前条件</span
          ><b
            >现金{{ money(s.dashboard?.state.available_cash_minor) }}、库存{{
              stock?.on_hand
            }}件、预计需求{{ stock?.remaining_demand }}件</b
          >
        </div>
        <div class="detail-row">
          <span>检查安排</span
          ><b>每{{ mission?.schedule.interval_seconds ?? 30 }}秒检查计划，经营事件后复查</b>
        </div>
      </div>
      <p class="channel-note">当前连接合成经营环境。每次采购仍需确认；进展在应用内查看。</p>
      <div class="modal-actions">
        <button class="secondary" @click="quote">我想先整理报价</button
        ><button class="primary" :disabled="!s.storeId || !offer || Boolean(s.busy)" @click="start">
          {{ mission ? '继续当前委托' : '按以上条件开始' }}
        </button>
      </div>
    </section>
  </dialog>
</template>
