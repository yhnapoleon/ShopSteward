<script setup lang="ts">
import { joinText, t as tr } from '~/i18n'
import type { Schema } from '~/types/models'
import { when } from '~/utils/presentation'
import { workPresentation, workTitle } from '~/utils/workPresentation'
import { awaitsOwnerArrival, workBadge } from '~/composables/useSpace'
const props = defineProps<{ item: Schema<'WorkView'> }>()
defineEmits<{ open: [] }>()
const presentation = computed(() => workPresentation(props.item))
// The badge uses the shared status vocabulary; the backend's own wording stays in the text.
const { s } = useShop()
const badge = computed(() =>
  workBadge(props.item, Date.now(), awaitsOwnerArrival(props.item.mission_id, s)),
)
const state = computed(() => tr(presentation.value.label))
const work = useWorkItems()
</script>
<template>
  <article class="work-card glass" :data-work-id="item.id">
    <div class="work-card-top">
      <span class="tag">{{ tr(item.mission_id ? '备货事项' : '我的事项') }}</span
      ><span class="tag" :class="badge.tone">{{ badge.label }}</span>
    </div>
    <h2>{{ workTitle(item) }}</h2>
    <p>
      <b v-if="state !== badge.label" class="work-card-state">{{ state }} · </b
      >{{ presentation.detailIsOriginal ? presentation.detail : tr(presentation.detail) }}
    </p>
    <small v-if="work.s.listError" class="source-note">{{
      tr('连接中断，显示上次读取的状态；打开后重新核对。')
    }}</small>
    <small v-if="item.mission_id" class="source-note">{{
      joinText([tr('本轮讨论：'), tr(presentation.processing)])
    }}</small>
    <small v-if="item.demonstration" class="notice amber">{{
      tr('模拟接入结果 · 非真实 Agent 分析')
    }}</small>
    <div class="work-card-bottom">
      <span>{{ tr(when(item.updated_at)) }}</span
      ><button class="primary" @click="$emit('open')">
        {{ tr(presentation.action) }}<AppIcon name="arrow-up-right" />
      </button>
    </div>
  </article>
</template>
