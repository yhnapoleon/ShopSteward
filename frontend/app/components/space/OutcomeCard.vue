<script setup lang="ts">
import { t as tr } from '~/i18n'

// No plan waits for the owner: say what the mission is waiting for instead.
const props = defineProps<{ working: boolean; rechecking?: boolean; recheckOpen?: boolean }>()
const { stock } = useShop()
const { status } = useTaskPresentation()
const { mission, ended, item } = useSpace()
// While the plan is re-checked after "next day" or the owner's own write (usePlanRecheck), the
// backend calls it "to be updated" (PLAN_STALE): the expected step, not news, and there is no plan
// here to confirm. The card says the re-check in its description's place, as a today-page card
// does, so nothing moves when the window ends; also for the moment the item's line still lags
// the new plan.
const rechecked = computed(
  () =>
    !!mission.value &&
    !ended.value &&
    (props.rechecking || (props.recheckOpen && item.value?.business?.code === 'PLAN_STALE')),
)
</script>
<template>
  <article class="task-outcome glass space-outcome">
    <span class="task-outcome-icon"
      ><AppIcon
        :name="
          !mission
            ? 'loader-circle'
            : ended
              ? 'check-check'
              : working
                ? 'clock'
                : stock?.in_transit
                  ? 'truck'
                  : 'orbit'
        "
    /></span>
    <div>
      <h2>
        {{
          tr(
            !mission
              ? '正在读取这项委托'
              : ended
                ? mission.status === 'COMPLETED'
                  ? '这项委托已完成'
                  : '这项委托已取消'
                : working
                  ? '正在核实采购提交'
                  : stock?.in_transit
                    ? '等待到货'
                    : '暂时没有新的决定',
          )
        }}
      </h2>
      <p v-if="rechecked" class="space-recheck" role="status">
        <span class="space-pulse" aria-hidden="true" />{{ tr('正在重新核对方案…') }}
      </p>
      <p v-else>{{ tr(mission ? status.detail : '方案、采购单与到货记录读取后显示在这里。') }}</p>
    </div>
  </article>
</template>
