import { defineConfig } from '@playwright/test'
const baseURL = process.env.FRONTEND_URL || 'http://127.0.0.1:3000'
if (!['127.0.0.1', 'localhost'].includes(new URL(baseURL).hostname))
  throw Error('These tests create synthetic data and require a loopback development URL.')
export default defineConfig({
  testDir: './tests',
  timeout: 90000,
  expect: { timeout: 30000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  outputDir: '../var/frontend-e2e/artifacts',
  reporter: [['line'], ['json', { outputFile: '../var/frontend-e2e/results.json' }]],
  use: {
    baseURL,
    viewport: { width: 1440, height: 1000 },
    reducedMotion: 'reduce',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
})
