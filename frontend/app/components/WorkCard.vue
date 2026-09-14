<script setup lang="ts">
import type { Schema } from '~/types/models'
import { when } from '~/utils/presentation'
import { workPresentation } from '~/utils/workPresentation'
const props = defineProps<{ item: Schema<'WorkView'> }>()
defineEmits<{ open: [] }>()
const presentation = computed(() => workPresentation(props.item))
const work = useWorkItems()
</script>
<template>
  <article class="work-card glass" :data-work-id="item.id">
    <div class="work-card-top">
      <span class="tag">{{ item.mission_id ? '备货事项' : '我的事项' }}</span
      ><span class="tag" :class="presentation.tone">{{ presentation.label }}</span>
    </div>
    <h2>{{ item.title }}</h2>
    <p>{{ presentation.detail }}</p>
    <small v-if="work.s.listError" class="source-note"
      >连接中断，显示上次读取的状态；打开后重新核对。</small
    >
    <small v-if="item.mission_id" class="source-note"
      >本轮讨论：{{ presentation.processing }}</small
    >
    <small v-if="item.demonstration" class="notice amber">模拟接入结果 · 非真实 Agent 分析</small>
    <div class="work-card-bottom">
      <span>{{ when(item.updated_at) }}</span
      ><button class="primary" @click="$emit('open')">
        {{ presentation.action }}<AppIcon name="arrow-up-right" />
      </button>
    </div>
  </article>
</template>
