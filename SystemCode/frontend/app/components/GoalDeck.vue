<script setup lang="ts">
import { joinText, t as tr } from '~/i18n'
import { money } from '~/utils/presentation'
const props = defineProps<{ open: boolean }>(),
  emit = defineEmits<{ close: []; start: []; quote: []; submitted: [id: string] }>()
const { s, stock, offer, product, mission, hasRole } = useShop()
const work = useWorkItems()
// The page reopens an ongoing mission; an ended one is followed by a new mission.
const ongoing = computed(() => ['ACTIVE', 'PAUSED'].includes(mission.value?.status || ''))
// Conditions shown above the button: the ongoing mission's, else those a new mission uses.
const cashFloor = computed(() => (ongoing.value ? mission.value!.policy.cash_floor_minor : 30000))
const interval = computed(() => (ongoing.value ? mission.value!.schedule.interval_seconds : 30))
const startDisabled = computed(
  () => !s.storeId || !offer.value || Boolean(s.busy) || (!ongoing.value && !hasRole('operator')),
)
async function submitted(id: string) {
  await close()
  emit('submitted', id)
}
const layer = ref<HTMLDialogElement>(),
  main = ref<HTMLElement>(),
  anchor = ref<HTMLElement>(),
  scrim = ref<HTMLElement>()
let origin: HTMLElement | null = null,
  animations: Animation[] = []
let serial = 0
// Motion (§12): the card settles in from 96% toward the button that opened it in 240ms on the
// ease-out curve and leaves in 180ms; the scrim and the anchor only fade. Opened or closed from
// the keyboard it appears and disappears at once; reduced motion keeps the fades only.
const ease = 'cubic-bezier(0.23, 1, 0.32, 1)'
let keyboard = false
const fromPointer = () => (keyboard = false)
const fromKeyboard = (event: KeyboardEvent) => {
  if (!['Shift', 'Control', 'Alt', 'Meta'].includes(event.key)) keyboard = true
}
const still = () => matchMedia('(prefers-reduced-motion: reduce)').matches
function fade(entering: boolean, duration: number) {
  return [scrim.value, anchor.value]
    .filter((el): el is HTMLElement => !!el && el.style.display !== 'none')
    .map((el) =>
      el.animate([{ opacity: entering ? 0 : 1 }, { opacity: entering ? 1 : 0 }], {
        duration,
        easing: ease,
        fill: entering ? 'none' : 'forwards',
      }),
    )
}
async function close() {
  const n = ++serial
  const d = layer.value
  if (!d?.open) return
  animations.forEach((a) => a.cancel())
  animations = []
  if (main.value && !keyboard) {
    const moving = !still(),
      duration = moving ? 180 : 120
    const leaving = [
      main.value.animate(
        moving
          ? [
              { opacity: 1, transform: 'none' },
              { opacity: 0, transform: 'scale(0.97)' },
            ]
          : [{ opacity: 1 }, { opacity: 0 }],
        { duration, easing: ease, fill: 'forwards' },
      ),
      ...fade(false, duration),
    ]
    animations = leaving
    await Promise.all(leaving.map((a) => a.finished.catch(() => {})))
    if (n !== serial) return
    leaving.forEach((a) => a.cancel())
    animations = []
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
    ++serial
    await nextTick()
    const d = layer.value
    if (!d) return
    // Safari does not focus a clicked button; without a control to return to there is no anchor.
    const active = document.activeElement
    origin = active instanceof HTMLElement && active !== document.body ? active : null
    if (!d.open) d.showModal()
    animations.forEach((a) => a.cancel())
    animations = []
    if (!main.value) return
    const o = origin?.getBoundingClientRect(),
      r = main.value.getBoundingClientRect()
    if (anchor.value)
      Object.assign(
        anchor.value.style,
        o
          ? {
              display: '',
              left: o.left + 'px',
              top: o.top + 'px',
              width: o.width + 'px',
              height: o.height + 'px',
            }
          : { display: 'none' },
      )
    main.value.focus({ preventScroll: true })
    if (keyboard) return
    // Scale toward the trigger: its centre, in the card's own box, is the transform origin.
    main.value.style.transformOrigin = o
      ? `${o.left + o.width / 2 - r.left}px ${o.top + o.height / 2 - r.top}px`
      : 'center'
    const moving = !still()
    animations = [
      main.value.animate(
        moving
          ? [
              { opacity: 0, transform: 'scale(0.96)' },
              { opacity: 1, transform: 'none' },
            ]
          : [{ opacity: 0 }, { opacity: 1 }],
        { duration: moving ? 240 : 160, easing: ease },
      ),
      ...fade(true, moving ? 200 : 160),
    ]
  },
)
onMounted(() => {
  document.addEventListener('pointerdown', fromPointer, true)
  document.addEventListener('keydown', fromKeyboard, true)
})
onUnmounted(() => {
  document.removeEventListener('pointerdown', fromPointer, true)
  document.removeEventListener('keydown', fromKeyboard, true)
  animations.forEach((a) => a.cancel())
})
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
    <div ref="scrim" class="deck-scrim" @click="close" />
    <button ref="anchor" class="deck-anchor" :aria-label="tr('收回委托入口')" @click="close">
      <AppIcon name="x" />{{ tr('交给我一件事') }}
    </button>
    <section ref="main" class="deck-main" tabindex="-1">
      <template v-if="work.s.available"
        ><div class="deck-topline">
          <span id="deck-title" class="tag">{{ tr('交给我一件事') }}</span
          ><button class="icon-btn" :aria-label="tr('收起委托卡片')" @click="close">
            <AppIcon name="x" />
          </button>
        </div>
        <WorkIntake v-if="props.open" @submitted="submitted" />
        <section class="deck-structured" aria-labelledby="deck-structured-title">
          <h3 id="deck-structured-title">{{ tr('按当前条件开始备货跟进') }}</h3>
          <div class="start-scope">
            <b>{{ product?.name || tr('请先选择示例店铺') }}</b
            ><span>{{
              tr('现金{0}、库存{1}件、预计需求{2}件', [
                tr(money(s.dashboard?.state.available_cash_minor)),
                stock?.on_hand ?? '',
                stock?.remaining_demand ?? '',
              ])
            }}</span
            ><span>{{
              joinText([
                tr('现金底线'),
                tr(money(cashFloor)),
                '·',
                tr('每'),
                tr(interval),
                tr('秒检查计划，经营事件后复查'),
              ])
            }}</span>
          </div>
          <p class="channel-note">{{ tr('开始跟进不会自动采购，每笔采购仍由你确认。') }}</p>
          <div class="modal-actions">
            <button class="secondary" @click="quote">{{ tr('我想先整理报价') }}</button
            ><button class="primary" :disabled="startDisabled" @click="start">
              {{ tr(ongoing ? '继续当前委托' : '按以上条件开始') }}
            </button>
          </div>
        </section></template
      >
      <template v-else>
        <div class="deck-topline">
          <span class="tag">{{ tr('当前可使用的两件事') }}</span
          ><button class="icon-btn" :aria-label="tr('收起委托卡片')" @click="close">
            <AppIcon name="x" />
          </button>
        </div>
        <h2 id="deck-title">{{ tr('把这次备货交代清楚。') }}</h2>
        <p>{{ tr('确认下面的范围后建立跟进委托。开始跟进不会自动采购。') }}</p>
        <div class="intake-scope">
          <div class="detail-row">
            <span>{{ tr('商品') }}</span
            ><b>{{ product?.name || tr('请先选择示例店铺') }}</b>
          </div>
          <div class="detail-row">
            <span>{{ tr('目标') }}</span
            ><b>{{ tr('比较活动备货方案，跟进到货与需求变化') }}</b>
          </div>
          <div class="detail-row">
            <span>{{ tr('现金底线') }}</span
            ><b>{{ tr(money(cashFloor)) }}</b>
          </div>
          <div class="detail-row">
            <span>{{ tr('当前条件') }}</span
            ><b>{{
              tr('现金{0}、库存{1}件、预计需求{2}件', [
                tr(money(s.dashboard?.state.available_cash_minor)),
                stock?.on_hand ?? '',
                stock?.remaining_demand ?? '',
              ])
            }}</b>
          </div>
          <div class="detail-row">
            <span>{{ tr('检查安排') }}</span
            ><b>{{ joinText([tr('每'), tr(interval), tr('秒检查计划，经营事件后复查')]) }}</b>
          </div>
        </div>
        <p class="channel-note">
          {{ tr('当前连接合成经营环境。每次采购仍需确认；进展在应用内查看。') }}
        </p>
        <div class="modal-actions">
          <button class="secondary" @click="quote">{{ tr('我想先整理报价') }}</button
          ><button class="primary" :disabled="startDisabled" @click="start">
            {{ tr(ongoing ? '继续当前委托' : '按以上条件开始') }}
          </button>
        </div>
      </template>
    </section>
  </dialog>
</template>
