<script setup lang="ts">
const work = useWorkItems(),
  { s } = work
const emit = defineEmits<{ submitted: [id: string] }>()
const inputId = useId()
async function send() {
  const d = await work.send(true)
  if (d) emit('submitted', d.item.id)
}
function keydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
    e.preventDefault()
    if (!s.busy && !s.pending && s.input.trim()) void send()
  }
}
</script>
<template>
  <section class="work-intake">
    <h2>今天想解决什么事？</h2>
    <p>可以先问一问，也可以交代一件需要跟进的事情。</p>
    <p v-if="!s.processorAvailable" class="source-note">
      助手暂不可用，要求会先保存；已有经营安排仍可查看。
    </p>
    <label :for="inputId">把事情告诉我</label
    ><textarea
      :id="inputId"
      v-model="s.input"
      rows="3"
      maxlength="8000"
      :disabled="s.busy || !!s.pending"
      placeholder="例如：下周有活动，帮我看看牛奶够不够卖，至少留500块钱。"
      @keydown="keydown"
    />
    <div class="work-examples">
      <button
        v-for="example in [
          '看看现在的库存和现金',
          '上次那个备货安排，我想少买一点',
          '帮我整理供应商报价',
        ]"
        :key="example"
        class="quiet-button"
        :disabled="s.busy || !!s.pending"
        @click="s.input = example"
      >
        {{ example }}
      </button>
    </div>
    <p v-if="s.error" class="notice amber" role="alert">{{ s.error }}</p>
    <div class="work-card-bottom">
      <small>发送后保留在同一事项中；不会自动采购。</small
      ><button class="primary" :disabled="s.busy || (!s.pending && !s.input.trim())" @click="send">
        {{ s.pending ? '恢复原提交' : '交给助手' }}<AppIcon name="arrow-right" />
      </button>
    </div>
  </section>
</template>
