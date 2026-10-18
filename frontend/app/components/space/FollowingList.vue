<script setup lang="ts">
import { t as tr } from '~/i18n'
import type { Schema } from '~/types/models'
import { workPresentation } from '~/utils/workPresentation'
import { needsOwner } from '~/composables/useSpace'

// Every work item of the current store: ongoing first (by priority), ended ones folded away.
const props = defineProps<{ items: Schema<'WorkView'>[] }>()
const emit = defineEmits<{ open: [id: string] }>()
const isEnded = (item: Schema<'WorkView'>) =>
  !needsOwner(item) &&
  (item.mission
    ? ['COMPLETED', 'CANCELLED'].includes(item.mission.status)
    : ['COMPLETED', 'CANCELLED'].includes(item.status))
const byPriority = (a: Schema<'WorkView'>, b: Schema<'WorkView'>) =>
  workPresentation(a).priority - workPresentation(b).priority
const ongoing = computed(() => props.items.filter((i) => !isEnded(i)).sort(byPriority))
const ended = computed(() => props.items.filter(isEnded))
</script>
<template>
  <section class="space-following" :aria-label="tr('全部事项')">
    <div class="section-label">
      {{ tr('进行中的事项') }}<span class="small-count">{{ tr(ongoing.length) }}</span
      ><span class="right">{{ tr('需要你的排在前面') }}</span>
    </div>
    <div class="space-watch">
      <SpaceWorkRow
        v-for="item in ongoing"
        :key="item.id"
        :item="item"
        @open="emit('open', item.id)"
      />
      <p v-if="!ongoing.length" class="space-quiet">{{ tr('暂无跟进中的事项') }}</p>
    </div>
    <details v-if="ended.length" class="completed-tasks space-ended">
      <summary>
        {{ tr('已结束的事项') }}<span>{{ tr(ended.length) }}</span>
      </summary>
      <div class="space-watch">
        <SpaceWorkRow
          v-for="item in ended"
          :key="item.id"
          :item="item"
          @open="emit('open', item.id)"
        />
      </div>
    </details>
  </section>
</template>
