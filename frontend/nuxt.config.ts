export default defineNuxtConfig({
  compatibilityDate: '2026-09-07',
  ssr: false,
  devtools: { enabled: false },
  css: [
    '~/assets/css/shop.css',
    '~/assets/css/overview.css',
    '~/assets/css/tasks.css',
    '~/assets/css/work.css',
  ],
  typescript: { strict: true },
  runtimeConfig: {
    backendUrl: 'http://127.0.0.1:8000',
    backendToken: '',
    devTools: false,
    agentEnabled: false,
  },
  app: { head: { title: 'ShopSteward · 经营空间', htmlAttrs: { lang: 'zh-CN' } } },
})
