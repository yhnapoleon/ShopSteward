import { test, expect } from '@playwright/test'
import { setup } from './support/i18n-fixture'
test('settings material is opaque and mobile content scrolls inside dialog', async ({ page }) => {
  await setup(page)
  await page.addInitScript(() => localStorage.setItem('shopsteward.locale.v1', 'en'))
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await page.locator('.mobile-settings-entry').click()
  const dialog = page.locator('dialog[open]')
  await expect(dialog).toHaveCSS('opacity', '1')

  await page.screenshot({ path: '../var/i18n/settings-mobile.png', animations: 'disabled' })
  await dialog.getByRole('combobox').scrollIntoViewIfNeeded()
  await expect(dialog.getByRole('combobox')).toBeVisible()
  await page.screenshot({
    path: '../var/i18n/settings-mobile-scrolled.png',
    animations: 'disabled',
  })
})
