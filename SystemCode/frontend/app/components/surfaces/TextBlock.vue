<script setup lang="ts">
// Markdown through the existing MarkdownMessage, which allows no HTML, images, forms or controls.
defineProps<{ markdown: string }>()
</script>
<template>
  <div class="surface-text"><MarkdownMessage :content="markdown" /></div>
</template>
