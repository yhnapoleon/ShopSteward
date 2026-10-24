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
    <div class="rf-head-copy">
      <h3 class="rf-title" aria-live="polite">
        {{ tr('{0}的结果还没确认', [tr(flow.unconfirmedStep.value)]) }}
      </h3>
      <p class="rf-sub" role="status">
        {{
          tr(
            tried && !busy
              ? '这次还是没有收到回音，稍后再试。'
              : '没有收到回音，这一步可能已经生效。再试一次会沿用刚才的提交，不会重复。',
          )
        }}
      </p>
    </div>
    <footer class="rf-next">
      <button
        type="button"
        class="primary"
        :disabled="busy || !flow.operator.value"
        data-recovery-next
        data-recovery-retry
        @click="retry"
      >
        {{ tr(busy ? '正在确认…' : '再试一次（沿用刚才的提交）') }}<AppIcon name="arrow-right" />
      </button>
    </footer>
  </div>
</template>
