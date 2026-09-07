<script setup lang="ts">
const props = defineProps<{ open: boolean; title: string; busy?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const dialog = ref<HTMLDialogElement>()
let origin: HTMLElement | null = null
// Remember the trigger before an asynchronous action temporarily disables it.
function rememberFocus(event: FocusEvent) {
  if (!props.open && event.target instanceof HTMLElement && event.target !== document.body)
    origin = event.target
}
onMounted(() => document.addEventListener('focusin', rememberFocus))
onUnmounted(() => document.removeEventListener('focusin', rememberFocus))
watch(
  () => props.open,
  async (open) => {
    await nextTick()
    if (open) {
      const active = document.activeElement
      if (active instanceof HTMLElement && active !== document.body) origin = active
      dialog.value?.showModal()
    } else {
      dialog.value?.close()
      origin?.isConnected && origin.focus({ preventScroll: true })
    }
  },
  { immediate: true },
)
function close() {
  if (!props.busy) emit('close')
}
function outside(e: MouseEvent) {
  const d = dialog.value
  if (e.target !== d || !d) return
  const r = d.getBoundingClientRect()
  if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom)
    close()
}
</script>
<template>
  <dialog ref="dialog" aria-labelledby="dialog-title" @cancel.prevent="close" @click="outside">
    <header class="modal-head">
      <h2 id="dialog-title">{{ title }}</h2>
      <button class="icon-btn" aria-label="关闭对话框" :disabled="busy" @click="close">
        <AppIcon name="x" />
      </button>
    </header>
    <div class="modal-body"><slot /></div>
  </dialog>
</template>
