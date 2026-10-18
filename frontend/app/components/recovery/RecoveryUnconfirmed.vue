<script setup lang="ts">
import { t as tr } from '~/i18n'
import { useFlow } from '~/composables/useRecoveryFlow'

// A submission whose answer never came back. The owner sees which step it was and one way on:
// send the same submission again under its original key, so it cannot happen twice.
const flow = useFlow()
const busy = computed(() => !!flow.working.value || flow.recovery.busy.value)
const tried = ref(false)
async function retry() {
  tried.value = true
  await flow.retry()
}
</script>

<template>
  <div class="rf-stage" data-recovery-unconfirmed>
    <h3 class="rf-title" aria-live="polite">
      {{ tr('{0}的结果还没确认', [tr(flow.unconfirmedStep.value)]) }}
    </h3>
    <p class="notice amber rf-banner" role="status">
      {{
        tr(
          tried && !busy
            ? '这次核实还没有回音，稍后再试。'
            : '网络中断或服务出错时，这一步可能已经生效。核实会按原来的提交再发一次，不会重复。',
        )
      }}
    </p>
    <footer class="rf-next">
      <button
        type="button"
        class="primary"
        :disabled="busy || !flow.operator.value"
        data-recovery-next
        data-recovery-retry
        @click="retry"
      >
        {{ tr(busy ? '正在核实…' : '核实并重试原提交') }}<AppIcon name="arrow-right" />
      </button>
    </footer>
  </div>
</template>
