<script setup lang="ts">
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
const props = defineProps<{ content: string }>()
const root = ref<HTMLElement | null>(null)
const copyStatus = ref('')
let epoch = 0
let resetTimers: ReturnType<typeof setTimeout>[] = []
function invalidate() {
  epoch++
  resetTimers.forEach(clearTimeout)
  resetTimers = []
  copyStatus.value = ''
}
function addCopyButtons() {
  invalidate()
  const version = epoch
  root.value?.querySelectorAll('pre').forEach((pre, index) => {
    const code = pre.querySelector('code')
    if (!code) return
    // These controls are created by the application after sanitization. Model HTML
    // cannot create buttons; copy exactly the rendered code, including newlines.
    const wrapper = document.createElement('div')
    wrapper.className = 'agent-code-block'
    const toolbar = document.createElement('div')
    toolbar.className = 'agent-code-toolbar'
    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'text-link'
    button.textContent = '复制代码'
    button.setAttribute('aria-label', `复制第 ${index + 1} 段代码`)
    button.addEventListener('click', async () => {
      button.disabled = true
      try {
        await navigator.clipboard.writeText(code.textContent || '')
        if (version !== epoch || !root.value?.contains(button)) return
        button.textContent = '已复制'
        copyStatus.value = `第 ${index + 1} 段代码已复制。`
        resetTimers.push(
          setTimeout(() => {
            if (version === epoch) button.textContent = '复制代码'
          }, 1800),
        )
      } catch {
        if (version === epoch) copyStatus.value = '无法复制，请选中代码后手动复制。'
      } finally {
        if (version === epoch) button.disabled = false
      }
    })
    pre.replaceWith(wrapper)
    toolbar.append(button)
    wrapper.append(toolbar, pre)
  })
}
onMounted(addCopyButtons)
onUnmounted(invalidate)
const markdown = new MarkdownIt({ html: false, linkify: false, breaks: true })
markdown.renderer.rules.link_open = (tokens, index, options, _env, renderer) => {
  tokens[index]!.attrSet('target', '_blank')
  tokens[index]!.attrSet('rel', 'noopener noreferrer')
  return renderer.renderToken(tokens, index, options)
}
// Model text cannot define executable HTML, images, forms, or business controls.
const rendered = computed(() =>
  DOMPurify.sanitize(markdown.render(props.content), {
    ALLOWED_TAGS: [
      'p',
      'br',
      'strong',
      'em',
      's',
      'ul',
      'ol',
      'li',
      'blockquote',
      'pre',
      'code',
      'a',
      'h1',
      'h2',
      'h3',
      'h4',
      'hr',
      'table',
      'thead',
      'tbody',
      'tr',
      'th',
      'td',
    ],
    ALLOWED_ATTR: ['href', 'title', 'start', 'target', 'rel'],
    ALLOWED_URI_REGEXP: /^(?:https?:\/\/|mailto:)/i,
  }),
)
watch(
  rendered,
  async () => {
    invalidate()
    await nextTick()
    addCopyButtons()
  },
  { flush: 'post' },
)
</script>
<template>
  <div>
    <div ref="root" class="agent-markdown" v-html="rendered" />
    <p v-if="copyStatus" class="code-copy-status" role="status">{{ copyStatus }}</p>
  </div>
</template>
