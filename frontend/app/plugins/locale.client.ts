import { locale, localeKey, readLocale } from '~/i18n'
export default defineNuxtPlugin(() => {
  readLocale()
  window.addEventListener('storage', (event) => {
    if (event.storageArea === localStorage && (event.key === localeKey || event.key === null))
      locale.value = event.newValue === 'en' ? 'en' : 'zh-CN'
  })
})
