<script setup lang="ts">
// A main button's label that says when its step is under way, in its own place and at its own
// width: both labels share one cell (recovery.css .rf-hold), the arrow turns into a spinner.
defineProps<{ label: string; busy: string; working: boolean }>()
</script>
<template>
  <span class="rf-hold" :class="{ 'is-busy': working }" :data-busy="busy"
    ><span>{{ label }}</span></span
  ><AppIcon :name="working ? 'loader-circle' : 'arrow-right'" />
</template>
