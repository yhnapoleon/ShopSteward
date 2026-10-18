<script setup lang="ts">
import { t as tr } from '~/i18n'

// Today page: the mission needs more than its regular plan can give. One sentence, one way in;
// the work page opens with the restock brief already filled in.
const emit = defineEmits<{ open: [missionId: string] }>()
const prompt = useRecoveryPrompt()
const { s } = useShop()
watch(
  () => s.storeId,
  () => void prompt.load(),
  { immediate: true },
)
function go() {
  const id = prompt.launch()
  if (id) emit('open', id)
}
</script>
<template>
  <article v-if="prompt.shown.value" class="rf-prompt attention-card glass" data-recovery-prompt>
    <div class="rf-prompt-copy">
      <span class="tag amber">{{ prompt.tag.value }}</span>
      <h2>{{ prompt.title.value }}</h2>
    </div>
    <button type="button" class="primary" @click="go">
      {{ tr('找别家补') }}<AppIcon name="arrow-right" />
    </button>
  </article>
</template>
