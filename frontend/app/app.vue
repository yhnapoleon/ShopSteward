<script setup lang="ts">
import { locale, t } from '~/i18n'
useHead(() => ({
  title: t('ShopSteward · 经营空间'),
  htmlAttrs: { lang: locale.value === 'en' ? 'en' : 'zh-CN' },
}))
</script>
<template><NuxtPage /></template>
