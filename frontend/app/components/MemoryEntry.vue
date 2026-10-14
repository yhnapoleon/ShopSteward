<script setup lang="ts">
import { t as tr } from '~/i18n'

// Ways into the memory drawer (§8): the header icon button, or a settings row for screens where
// the header entry is hidden (small screens; mid-width headers that show the Agent entry).
defineProps<{ variant?: 'header' | 'settings' }>()
const { learned, show } = useAgentKnowledge()
const uid = useId()
</script>
<template>
  <section
    v-if="variant === 'settings'"
    class="settings-section memory-settings"
    :aria-labelledby="uid + '-heading'"
  >
    <h3 :id="uid + '-heading'">{{ tr('记忆') }}</h3>
    <div class="settings-group">
      <div class="settings-row">
        <div>
          <strong
            >{{ tr('系统记住了什么')
            }}<span v-if="learned" class="memory-new">{{ tr('有新内容') }}</span></strong
          >
          <p>{{ tr('偏好、经营笔记与可复用的做法') }}</p>
        </div>
        <button
          class="text-link"
          :aria-label="tr('打开记忆面板')"
          aria-haspopup="dialog"
          @click="show($event.currentTarget)"
        >
          {{ tr('打开') }}<AppIcon name="chevron-right" />
        </button>
      </div>
    </div>
  </section>
  <button
    v-else
    class="icon-btn memory-entry"
    :aria-label="tr('记忆')"
    :title="tr('系统记住了什么')"
    aria-haspopup="dialog"
    :aria-describedby="learned ? uid + '-new' : undefined"
    @click="show($event.currentTarget)"
  >
    <AppIcon name="sparkles" /><template v-if="learned"
      ><span class="memory-dot" aria-hidden="true" /><span :id="uid + '-new'" class="sr-only">{{
        tr('有新记忆')
      }}</span></template
    >
  </button>
</template>
