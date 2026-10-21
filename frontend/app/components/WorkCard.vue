<script setup lang="ts">
import { t as tr } from '~/i18n'
import type { Schema } from '~/types/models'
import { money } from '~/utils/presentation'
import { workPresentation, workTitle } from '~/utils/workPresentation'
import { awaitsOwnerArrival, workBadge } from '~/composables/useSpace'
// `quiet`: another card on the page (the emergency restock) holds the one primary action, so
// this card's way in steps down to a secondary button. `inDecisions`: the card sits under the
// "需要你拍板" heading, so a badge saying the same is left out.
const props = defineProps<{ item: Schema<'WorkView'>; quiet?: boolean; inDecisions?: boolean }>()
defineEmits<{ open: [] }>()
const presentation = computed(() => workPresentation(props.item))
// The badge uses the shared status vocabulary; the backend's own wording stays in the text.
const { s, plan } = useShop()
const badge = computed(() =>
  workBadge(props.item, Date.now(), awaitsOwnerArrival(props.item.mission_id, s)),
)
const badgeShown = computed(() => !(props.inDecisions && badge.value.label === tr('需要你拍板')))
// The purchase waiting for the owner, when this item's plan is the one the page has loaded.
const purchase = computed(() => {
  const current = plan.value
  return current?.status === 'PENDING_APPROVAL' && current.id === props.item.business?.plan_id
    ? current.proposed_purchase
    : null
})
// The backend's own status line, unless the badge already says it: a plan awaiting the owner is
// what "your decision needed" means.
const state = computed(() =>
  props.item.business?.code === 'PENDING_APPROVAL' ? '' : tr(presentation.value.label),
)
const work = useWorkItems()
</script>
<template>
  <article class="work-card glass" :data-work-id="item.id">
    <div v-if="badgeShown" class="work-card-top">
      <span class="tag" :class="badge.tone">{{ badge.label }}</span>
    </div>
    <h2 :title="workTitle(item)">{{ workTitle(item) }}</h2>
    <p>
      <b v-if="state && state !== badge.label" class="work-card-state">{{ state }} · </b
      >{{ presentation.detailIsOriginal ? presentation.detail : tr(presentation.detail) }}
    </p>
    <small v-if="work.s.listError" class="source-note">{{
      tr('连接中断，显示上次读取的状态；打开后重新核对。')
    }}</small>
    <small v-if="item.demonstration" class="notice amber">{{
      tr('模拟接入结果 · 非真实 Agent 分析')
    }}</small>
    <div class="work-card-bottom">
      <b v-if="purchase" class="work-card-figures">{{
        tr('补货 {0} 件 · {1}', [purchase.quantity, money(purchase.total_minor)])
      }}</b
      ><button :class="quiet ? 'secondary' : 'primary'" @click="$emit('open')">
        {{ tr(presentation.action) }}<AppIcon name="arrow-up-right" />
      </button>
    </div>
  </article>
</template>
<style scoped>
h2:first-child {
  margin-top: 0;
}
.work-card-figures {
  font-size: 15px;
  font-weight: 600;
  color: #28343e;
  font-variant-numeric: tabular-nums;
}
</style>
