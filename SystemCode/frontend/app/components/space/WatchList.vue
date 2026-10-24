<script setup lang="ts">
import { t as tr } from '~/i18n'
import type { Schema } from '~/types/models'

// "What the system is watching for me": ongoing items that need nothing from the owner now.
defineProps<{ items: Schema<'WorkView'>[] }>()
const emit = defineEmits<{ open: [id: string] }>()
</script>
<template>
  <div class="space-watch">
    <SpaceWorkRow v-for="item in items" :key="item.id" :item="item" @open="emit('open', item.id)" />
    <p v-if="!items.length" class="space-quiet">{{ tr('暂无跟进中的事项') }}</p>
  </div>
</template>
