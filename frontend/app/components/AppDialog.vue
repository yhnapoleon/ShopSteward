<script setup lang="ts">
import { t as tr } from '~/i18n'
const props = defineProps<{ open: boolean; title: string; busy?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const dialog = ref<HTMLDialogElement>()
const titleId = useId()
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
  (open) => {
    if (!open || import.meta.server) return
    const active = document.activeElement
    if (active instanceof HTMLElement && active !== document.body) origin = active
  },
  { immediate: true },
)
// The element mounts on open. On close the modal ends at once, so the page is interactive and
// focus returns immediately. The closed modal has no backdrop, so a scrim that looks like it
// takes its place in the same task, and the two leave together in one quick fade (reduced motion
// skips it); the scrim passes the pointer through, and the leave finishes on its own clock.
const show = (el: Element) => (el as HTMLDialogElement).showModal()
function leave(el: Element, done: () => void) {
  const d = el as HTMLDialogElement
  d.close()
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return done()
  const scrim = document.createElement('div')
  scrim.className = 'dialog-scrim'
  scrim.setAttribute('aria-hidden', 'true')
  document.body.append(scrim)
  let finished = false
  const finish = () => {
    if (finished) return
    finished = true
    scrim.remove()
    done()
  }
  d.classList.add('dialog-leave-active')
  d.addEventListener('animationend', (e) => e.target === d && finish())
  setTimeout(finish, 200)
}
const restore = () => origin?.isConnected && origin.focus({ preventScroll: true })
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
  <Transition
    name="dialog"
    :css="false"
    mode="out-in"
    @enter="show"
    @leave="leave"
    @after-leave="restore"
  >
    <dialog
      v-if="open"
      ref="dialog"
      :aria-labelledby="titleId"
      @cancel.prevent="close"
      @click="outside"
    >
      <header class="modal-head">
        <h2 :id="titleId">{{ tr(title) }}</h2>
        <button class="icon-btn" :aria-label="tr('关闭对话框')" :disabled="busy" @click="close">
          <AppIcon name="x" />
        </button>
      </header>
      <div class="modal-body"><slot /></div>
    </dialog>
  </Transition>
</template>
