<script setup lang="ts">
import { t as tr } from '~/i18n'
import { workTitle } from '~/utils/workPresentation'
const props = defineProps<{ issue: string | null }>()
const emit = defineEmits<{ back: []; open: [name: string] }>()
const shop = useShop()
const { s, product, hasRole } = shop
const space = useSpace()
const { item, linked, mission, ended } = space
const badge = computed(() => space.badgeFor(props.issue))
const error = ref('')
// Emergency restock is started from here; while one is under way its card leads the page instead.
const launcher = useRecoveryLaunch()
const canRestock = computed(
  () =>
    !!s.session?.recoveryCases &&
    hasRole('operator') &&
    mission.value?.status === 'ACTIVE' &&
    !launcher.inProgress(mission.value.id),
)
function restock() {
  if (mission.value) launcher.request({ missionId: mission.value.id, reason: 'manual' })
}
async function resume() {
  error.value = ''
  try {
    await shop.control('resume')
  } catch (e) {
    error.value = (e as Error).message
  }
}
</script>
<template>
  <button class="task-back text-link" @click="emit('back')">
    <AppIcon name="arrow-right" />{{ tr('返回今日') }}
  </button>
  <header
    v-if="item"
    id="space-mission"
    class="task-page-heading space-target space-heading"
    :class="{ 'target-active': space.isTarget('mission') }"
  >
    <div class="space-heading-copy">
      <div class="eyebrow">
        {{
          linked
            ? product?.name
              ? tr('备货委托 · {0}', [product.name])
              : tr('备货委托')
            : tr('我的事项')
        }}
      </div>
      <h1 :title="workTitle(item)">{{ workTitle(item) }}</h1>
    </div>
    <div class="task-heading-actions">
      <span class="tag" :class="badge.tone" role="status">{{ badge.label }}</span>
      <!-- The links stay on one line; on a narrow screen they move under the status together. -->
      <span v-if="canRestock || mission" class="space-heading-links"
        ><button
          v-if="canRestock"
          type="button"
          class="text-link"
          data-recovery-entry
          @click="restock"
        >
          <AppIcon name="truck" />{{ tr('应急补货') }}</button
        ><template v-if="mission"
          ><button class="text-link" aria-haspopup="dialog" @click="emit('open', 'mission')">
            {{ tr('委托详情') }}</button
          ><button
            v-if="mission.status === 'ACTIVE'"
            class="text-link"
            aria-haspopup="dialog"
            :disabled="Boolean(s.busy) || !hasRole('operator')"
            @click="emit('open', 'pause')"
          >
            {{ tr('暂停主动跟进') }}</button
          ><button
            v-else-if="mission.status === 'PAUSED'"
            class="text-link"
            :disabled="Boolean(s.busy) || !hasRole('operator')"
            @click="resume"
          >
            {{ tr('继续主动跟进') }}</button
          ><button
            v-if="!ended && hasRole('approver')"
            class="text-link"
            aria-haspopup="dialog"
            :aria-label="tr('结束委托…')"
            :disabled="Boolean(s.busy)"
            @click="emit('open', 'complete')"
          >
            {{ tr('结束') }}
          </button></template
        ></span
      >
    </div>
    <p v-if="error" class="notice amber space-heading-error" role="alert">{{ tr(error) }}</p>
  </header>
</template>
<style scoped>
.space-heading-links {
  display: inline-flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 6px 16px;
  white-space: nowrap;
}
@media (max-width: 580px) {
  .space-heading-links {
    gap: 14px;
  }
}
</style>
