import type { Ref } from 'vue'

/**
 * Whether a scrolling box holds more than it shows: its last child ends past the box's visible
 * height. Measured from the content itself, so room the page adds at the end once it does (the
 * presenter bar's footprint, space.css) never decides it. Re-measured whenever the box or any of
 * its children changes size, and as children come and go.
 */
export function useOverflowing(box: Ref<HTMLElement | null | undefined>) {
  const overflowing = ref(false)
  function measure() {
    const el = box.value
    const last = el?.lastElementChild
    if (!el || !last) {
      overflowing.value = false
      return
    }
    const end = last.getBoundingClientRect().bottom - el.getBoundingClientRect().top + el.scrollTop
    overflowing.value = end > el.clientHeight + 1
  }
  watch(
    box,
    (el, _, onCleanup) => {
      if (!el || typeof ResizeObserver === 'undefined') return
      const sizes = new ResizeObserver(measure)
      const observe = () => {
        sizes.disconnect()
        sizes.observe(el)
        for (const child of el.children) sizes.observe(child)
      }
      const children = new MutationObserver(observe)
      children.observe(el, { childList: true })
      observe()
      onCleanup(() => {
        sizes.disconnect()
        children.disconnect()
      })
    },
    { immediate: true, flush: 'post' },
  )
  return overflowing
}
