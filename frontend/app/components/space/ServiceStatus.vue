<script setup lang="ts">
import { t as tr } from '~/i18n'

// Which services this page can use right now. Every state is written out; the dot repeats it.
const { services } = useServiceStatus()
</script>
<template>
  <section class="rail-card glass space-services" :aria-label="tr('服务状态')">
    <span class="micro">{{ tr('服务状态') }}</span>
    <ul>
      <li v-for="service in services" :key="service.id">
        <span class="space-dot" :class="service.tone" aria-hidden="true" /><span
          class="space-service-name"
          >{{ tr(service.name) }}</span
        ><span class="space-service-state">{{ tr(service.state) }}</span>
      </li>
    </ul>
  </section>
</template>
