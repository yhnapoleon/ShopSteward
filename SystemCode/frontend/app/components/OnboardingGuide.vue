<script setup lang="ts">
import { t as tr } from '~/i18n'
import { money, number } from '~/utils/presentation'
const props = defineProps<{
  status: string
  step: number
  target: string
  location: string
  ready: boolean
  canSimulate: boolean
  hasResult: boolean
  resultOpened: boolean
  simulationSkipped: boolean
  existingResult: boolean
  aiAvailable: boolean
  completedNow: boolean
  storageFailed: boolean
  storeChanged: boolean
  error: string
  cash?: number
  onHand?: number
  inTransit?: number
}>()
const emit = defineEmits<{ action: [name: string] }>()
const panel = ref<HTMLElement>()
const title = computed(
  () =>
    [
      '用一次试算认识 ShopSteward',
      '先确认你在看哪家店铺',
      '看懂店铺的钱和货',
      '亲手做一次补货试算',
      '分清三个不同的动作',
      '把刚才的结果找回来',
    ][props.step] || '',
)
let highlighted: HTMLElement | null = null
let observer: MutationObserver | undefined
let frame = 0
function locate(scroll = false) {
  highlighted?.classList.remove('onboarding-target')
  highlighted = null
  if (props.status !== 'active' || !props.target) return
  highlighted =
    Array.from(document.querySelectorAll<HTMLElement>(props.target)).find(
      (el) => el.getBoundingClientRect().width > 0 && el.getBoundingClientRect().height > 0,
    ) || null
  highlighted?.classList.add('onboarding-target')
  if (scroll && highlighted) highlighted.scrollIntoView({ block: 'start', behavior: 'instant' })
}
watch(
  () => [props.step, props.status, props.location, props.target],
  async () => {
    await nextTick()
    locate(true)
    panel.value?.focus({ preventScroll: true })
  },
  { immediate: true },
)
onMounted(() => {
  observer = new MutationObserver(() => {
    cancelAnimationFrame(frame)
    frame = requestAnimationFrame(() => locate())
  })
  observer.observe(document.body, { childList: true, subtree: true })
  window.addEventListener('resize', resize)
})
function resize() {
  locate()
}
onUnmounted(() => {
  observer?.disconnect()
  cancelAnimationFrame(frame)
  highlighted?.classList.remove('onboarding-target')
  window.removeEventListener('resize', resize)
})
</script>

<template>
  <section v-if="status !== 'active'" class="onboarding-invite glass" :aria-label="tr('新手指引')">
    <div>
      <span class="eyebrow"
        >{{ tr('新手指引')
        }}<span v-if="status === 'new'"> · {{ tr('第 {0} 步，共 6 步', [1]) }}</span></span
      >
      <h2>
        {{
          tr(
            completedNow
              ? '你已经认识了基本操作'
              : status === 'paused'
                ? '继续上次的新手指引'
                : '用一次试算认识 ShopSteward',
          )
        }}
      </h2>
      <p>
        {{
          tr(
            completedNow
              ? '以后看今日待办，去持续跟进查看进展，到经营记录找回结果。'
              : status === 'paused'
                ? '进度已保留。准备好后，从上次停下的地方继续。'
                : '选店铺、看钱和货，再比较一次补货数量。试算不会下单，每笔采购由你确认。',
          )
        }}
      </p>
      <p v-if="completedNow && aiAvailable">
        {{ tr('也可以打开“交给我一件事”，试着输入“请查询当前库存和现金”。消息由你确认发送。') }}
      </p>
    </div>
    <div class="onboarding-invite-actions">
      <button
        v-if="!completedNow"
        class="primary"
        @click="emit('action', status === 'paused' ? 'resume' : 'start')"
      >
        {{ tr(status === 'paused' ? '继续指引' : '开始体验') }}<AppIcon name="arrow-right" />
      </button>
      <button v-if="completedNow && aiAvailable" class="secondary" @click="emit('action', 'ask')">
        {{ tr('试试 AI 咨询') }}
      </button>
      <button class="text-link" @click="emit('action', completedNow ? 'dismiss' : 'skip')">
        {{ tr(completedNow ? '开始自己使用' : '稍后再说') }}
      </button>
    </div>
    <p v-if="storageFailed" class="source-note">
      {{ tr('浏览器暂时无法保存指引进度，刷新后可能需要重新开始。') }}
    </p>
  </section>
  <Teleport v-else to="body">
    <aside
      ref="panel"
      class="onboarding-coach glass"
      :class="{ 'onboarding-left': step === 2 }"
      role="region"
      :aria-label="tr('新手指引')"
      tabindex="-1"
      @keydown.esc.stop.prevent="emit('action', 'pause')"
    >
      <div class="onboarding-coach-top">
        <span class="eyebrow">{{ tr('第 {0} 步，共 6 步', [step + 1]) }}</span>
        <button class="icon-btn" :aria-label="tr('暂停新手指引')" @click="emit('action', 'pause')">
          <AppIcon name="x" />
        </button>
      </div>
      <div class="onboarding-progress" :aria-label="tr('指引进度')">
        <span v-for="n in 6" :key="n" :class="{ done: n <= step + 1 }" />
      </div>
      <h2>{{ tr(title) }}</h2>
      <p v-if="storeChanged" class="notice" role="status">
        {{ tr('店铺已切换。请先核对新店铺，之前的试算不会作为本轮结果。') }}
      </p>
      <template v-if="step === 1">
        <p>
          {{
            tr(
              '顶部是当前店铺。已有店铺可以直接继续；没有数据时，先选择店铺或由管理员准备示例店铺。',
            )
          }}
        </p>
        <p class="onboarding-check" role="status">
          {{ tr(ready ? '店铺和经营数据已就绪。' : '等待店铺与经营数据就绪后，才能继续。') }}
        </p>
        <button class="secondary" @click="emit('action', 'store')">
          {{ tr('选择或准备店铺') }}
        </button>
      </template>
      <template v-else-if="step === 2">
        <dl class="onboarding-facts">
          <div>
            <dt>{{ tr('可用现金') }}</dt>
            <dd>{{ tr(money(cash)) }}</dd>
            <small>{{ tr('现在可以使用的钱') }}</small>
          </div>
          <div>
            <dt>{{ tr('在库') }}</dt>
            <dd>{{ tr(number(onHand)) }}</dd>
            <small>{{ tr('店里已经有的货') }}</small>
          </div>
          <div>
            <dt>{{ tr('采购在途') }}</dt>
            <dd>{{ tr(number(inTransit)) }}</dd>
            <small>{{ tr('已采购但还没到的货') }}</small>
          </div>
        </dl>
        <p>{{ tr('找到页面中对应的三个数，再继续。数量单位为件。') }}</p>
        <p v-if="!ready" class="notice" role="status">
          {{ tr('当前数据尚未就绪，请等待连接恢复。') }}
        </p>
      </template>
      <template v-else-if="step === 3">
        <p>{{ tr('选商品和供应商，填写至少留下多少钱，再比较 0、20、40 件。0 表示不补货。') }}</p>
        <p>
          {{
            tr(
              '在表单里点击“比较并保存结果”。保存成功后，指引才会继续；不满足约束的候选会说明原因。',
            )
          }}
        </p>
        <button
          v-if="canSimulate"
          class="primary"
          :disabled="!ready"
          @click="emit('action', 'simulation')"
        >
          {{ tr('打开补货试算') }}
        </button>
        <p v-else class="notice">
          {{ tr('当前身份或服务暂不支持补货试算，可以先了解后续操作。') }}
        </p>
        <button v-if="existingResult" class="secondary" @click="emit('action', 'existing')">
          {{ tr('查看已有试算并继续') }}
        </button>
        <button class="text-link" @click="emit('action', 'skip-simulation')">
          {{ tr('跳过试算，先了解后续操作') }}
        </button>
      </template>
      <template v-else-if="step === 4">
        <p class="onboarding-check">
          {{
            tr(
              hasResult
                ? '试算结果已经保存，还没有因此采购。'
                : '本轮跳过了试算，尚未保存新的结果。',
            )
          }}
        </p>
        <ol class="onboarding-actions-explained">
          <li>
            <strong>{{ tr('保存结果') }}</strong
            ><span>{{ tr('留下这次比较，方便以后核对。') }}</span>
          </li>
          <li>
            <strong>{{ tr('建立备货委托') }}</strong
            ><span>{{ tr('让系统持续检查补货需求。') }}</span>
          </li>
          <li>
            <strong>{{ tr('确认采购') }}</strong
            ><span>{{ tr('核对具体订单后，才提交这笔采购。') }}</span>
          </li>
        </ol>
        <p>{{ tr('完成指引不需要建立委托或采购。') }}</p>
        <button v-if="hasResult" class="text-link" @click="emit('action', 'result')">
          {{ tr('查看刚才的试算') }}
        </button>
      </template>
      <template v-else-if="step === 5">
        <p>
          {{
            tr(
              hasResult
                ? '经营记录会保留你的结果。打开刚才的试算，确认以后能在哪里找到它。'
                : '经营记录保存过去的结果和决定；持续跟进用来看正在处理的事项。',
            )
          }}
        </p>
        <p v-if="resultOpened" class="onboarding-check" role="status">
          {{ tr('已经重新打开这份试算，可以完成指引了。') }}
        </p>
        <button v-else-if="hasResult" class="primary" @click="emit('action', 'result')">
          {{ tr('打开刚才的试算') }}
        </button>
        <button class="text-link" @click="emit('action', 'journal')">{{ tr('去经营记录') }}</button>
      </template>
      <p v-if="error" class="notice amber" role="alert">{{ tr(error) }}</p>
      <p v-if="storageFailed" class="source-note">
        {{ tr('浏览器暂时无法保存指引进度，刷新后可能需要重新开始。') }}
      </p>
      <div class="onboarding-controls">
        <button class="text-link" @click="emit('action', 'previous')">
          {{ tr('上一步') }}
        </button>
        <button
          v-if="step !== 3"
          class="primary"
          :disabled="step <= 2 ? !ready : step === 5 && hasResult && !resultOpened"
          @click="emit('action', 'next')"
        >
          {{
            tr(
              step === 1
                ? '店铺没问题，继续'
                : step === 2
                  ? '我找到了'
                  : step === 4
                    ? '我明白了，去找回结果'
                    : '完成指引',
            )
          }}
        </button>
      </div>
      <p class="onboarding-footnote">{{ tr('可以随时暂停，之后从设置中重新查看。') }}</p>
    </aside>
  </Teleport>
</template>

<style scoped>
.onboarding-invite {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 20px;
  padding: 24px 28px;
  margin: 0 0 24px;
  border-radius: 24px;
}
.onboarding-invite > div:first-child {
  flex: 1 1 340px;
}
.onboarding-invite h2 {
  font-size: 21px;
  margin: 6px 0 8px;
}
.onboarding-invite p {
  margin: 0;
  line-height: 1.7;
  color: var(--muted);
}
.onboarding-invite-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  align-items: center;
}
.onboarding-coach {
  position: fixed;
  z-index: 35;
  right: 24px;
  bottom: 100px;
  width: min(380px, calc(100vw - 32px));
  max-height: min(620px, 76dvh);
  overflow-y: auto;
  padding: 22px 24px 16px;
  border-radius: 24px;
  background: #f7f9fc;
  box-shadow:
    0 12px 50px rgb(31 52 80 / 18%),
    inset 0 1px #fff;
  outline: none;
}
.onboarding-left {
  right: auto;
  left: 24px;
}
.onboarding-coach-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.onboarding-coach-top .icon-btn {
  width: 44px;
  height: 44px;
}
.onboarding-coach h2 {
  font-size: 22px;
  margin: 16px 0 12px;
  line-height: 1.45;
}
.onboarding-coach p {
  font-size: 14px;
  line-height: 1.7;
  margin: 12px 0;
}
.onboarding-coach > button {
  display: flex;
  margin-top: 12px;
}
.onboarding-progress {
  display: flex;
  gap: 6px;
}
.onboarding-progress span {
  height: 4px;
  border-radius: 4px;
  background: #dce3ec;
  flex: 1;
}
.onboarding-progress .done {
  background: var(--blue);
}
.onboarding-facts {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 10px;
  margin: 0;
}
.onboarding-facts dt,
.onboarding-facts small {
  font-size: 12px;
  color: var(--muted);
  line-height: 1.6;
}
.onboarding-facts dd {
  font-size: 21px;
  font-weight: 600;
  margin: 8px 0;
  overflow-wrap: anywhere;
}
.onboarding-facts small {
  display: block;
}
.onboarding-check {
  color: #275a46;
  background: #eaf3ed;
  padding: 10px 12px;
  border-radius: 12px;
}
.onboarding-actions-explained {
  padding-left: 22px;
  margin: 16px 0;
}
.onboarding-actions-explained li {
  padding-left: 4px;
  margin: 12px 0;
  font-size: 14px;
  line-height: 1.7;
}
.onboarding-actions-explained span {
  display: block;
  color: var(--muted);
}
.onboarding-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
}
.onboarding-coach .onboarding-footnote {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 0;
}
:global(.onboarding-target) {
  outline: 3px solid #2869c4 !important;
  outline-offset: 6px;
  scroll-margin-top: 130px;
  scroll-margin-bottom: 360px;
}
:global(.onboarding-running) {
  padding-bottom: 350px;
}
@media (max-width: 820px) {
  .onboarding-coach,
  .onboarding-left {
    left: 16px;
    right: 16px;
    bottom: calc(82px + env(safe-area-inset-bottom));
    width: auto;
    max-height: 45dvh;
    padding: 14px 20px;
    border-radius: 20px;
  }
  .onboarding-coach h2 {
    font-size: 19px;
    margin: 10px 0;
  }
  .onboarding-invite {
    padding: 20px;
  }
  .onboarding-invite h2 {
    font-size: 20px;
  }
  .onboarding-controls {
    margin-top: 12px;
    padding-top: 12px;
  }
  :global(.onboarding-target) {
    scroll-margin-top: 100px;
    scroll-margin-bottom: 480px;
  }
}
@media print {
  .onboarding-invite,
  .onboarding-coach {
    display: none;
  }
}
</style>
