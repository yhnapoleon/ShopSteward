<script setup lang="ts">
import type { Schema } from '~/types/models'
import { when } from '~/utils/presentation'
defineProps<{ item: Schema<'WorkView'> }>()
defineEmits<{ open: [] }>()
const work = useWorkItems()
</script>
<template>
  <article class="work-card glass" :data-work-id="item.id">
    <div class="work-card-top">
      <span class="tag">{{ item.mission_id ? '备货事项' : '我的事项' }}</span
      ><span class="tag" :class="{ amber: ['WAITING_INPUT', 'BLOCKED'].includes(item.status) }">{{
        work.label(item)
      }}</span>
    </div>
    <h2>{{ item.title }}</h2>
    <p v-if="item.question && item.status === 'WAITING_INPUT'">{{ item.question }}</p>
    <p v-else>{{ item.summary || '要求已保存，可以继续补充。' }}</p>
    <small v-if="item.demonstration" class="notice amber">模拟接入结果 · 非真实 Agent 分析</small>
    <div class="work-card-bottom">
      <span>{{ when(item.updated_at) }}</span
      ><button class="primary" @click="$emit('open')">
        {{ item.status === 'WAITING_INPUT' ? '补充信息' : '继续这件事'
        }}<AppIcon name="arrow-up-right" />
      </button>
    </div>
  </article>
</template>
