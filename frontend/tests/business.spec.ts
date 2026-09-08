import { test, expect, type Page } from '@playwright/test'
import fs from 'node:fs/promises'
async function button(p: Page, name: string) {
  await p.getByRole('button', { name, exact: true }).click()
}
async function controls(p: Page, name: string) {
  await button(p, '联调控制 · 合成数据')
  await p.getByRole('dialog').getByRole('button', { name, exact: true }).click()
  await expect(p.getByRole('dialog')).toHaveCount(0)
}
async function scenario(p: Page) {
  if (process.env.ENVIRONMENT_TEST_TOKEN)
    await p.request.post('/api/session', { data: { token: process.env.ENVIRONMENT_TEST_TOKEN } })
  await p.goto('/')
  await controls(p, '创建新的 SC-01 场景')
  await expect(p.getByRole('button', { name: '开始备货跟进', exact: true })).toBeVisible()
  await expect(p.getByTestId('cash')).toHaveText('¥1,000')
  return await p.evaluate(() => localStorage.getItem('ss.store')!)
}
async function start(p: Page) {
  await button(p, '开始备货跟进')
  await button(p, '按以上条件开始')
  await expect(p.getByRole('heading', { name: '建议补货 40 件', exact: true })).toBeVisible()
}
async function actions(p: Page, id: string) {
  const r = await p.request.get('/api/backend/api/v1/actions?store_id=' + id)
  expect(r.ok()).toBeTruthy()
  return (await r.json()).items as Array<{
    id: string
    quantity: number
    plan_id: string
    status: string
  }>
}
async function buy(p: Page, q: number, cash: string) {
  await button(p, `核对 ${q} 件采购`)
  await expect(p.getByRole('dialog')).toContainText(`${q} 件 ×`)
  await p.getByRole('button', { name: `确认采购 ${q} 件 · ¥${q * 10}`, exact: true }).dblclick()
  await expect(p.getByRole('dialog')).toHaveCount(0)
  await expect(p.getByTestId('cash')).toHaveText(cash)
}
async function advance(p: Page) {
  await controls(p, '推进下一个经营事件')
}

test('真实SC01：40件确认、刷新、暂停中到货、需求变化再20件、最终账目', async ({ page }, info) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  const id = await scenario(page)
  await start(page)
  expect(await actions(page, id)).toHaveLength(0)
  await button(page, '比较全部候选')
  await expect(page.getByRole('row').filter({ hasText: '80件' })).toContainText('低于现金底线')
  await button(page, '关闭对话框')
  await page.screenshot({
    path: info.outputPath('decision-desktop.jpg'),
    type: 'jpeg',
    quality: 80,
    fullPage: true,
  })
  await buy(page, 40, '¥600')
  await expect(page.getByTestId('stock')).toHaveText('20')
  await expect(page.getByTestId('inbound')).toHaveText('40')
  const first = (await actions(page, id))[0]!.id
  await page.reload()
  await expect(page.getByTestId('cash')).toHaveText('¥600')
  expect((await actions(page, id))[0]!.id).toBe(first)
  await button(page, '暂停跟进')
  await button(page, '确认暂停主动跟进')
  await expect(
    page.locator('.follow-panel').getByText('主动跟进已暂停', { exact: true }),
  ).toBeVisible()
  await advance(page)
  await expect(page.getByTestId('stock')).toHaveText('60')
  await expect(page.getByTestId('inbound')).toHaveText('0')
  await button(page, '恢复跟进')
  await advance(page)
  await expect(page.getByTestId('stock')).toHaveText('50')
  await expect(page.getByTestId('receivables')).toHaveText('¥200')
  await advance(page)
  // Allow the local business worker to finish queued event-driven replanning.
  await expect(page.getByRole('button', { name: '核对 20 件采购', exact: true })).toBeVisible({
    timeout: 90000,
  })
  await buy(page, 20, '¥400')
  await advance(page)
  await expect(page.getByTestId('stock')).toHaveText('70')
  await expect(page.getByTestId('inbound')).toHaveText('0')
  expect((await actions(page, id)).map((a) => a.quantity).sort()).toEqual([20, 40])
  await page.reload()
  await expect(page.getByTestId('cash')).toHaveText('¥400')
  await expect(page.getByTestId('receivables')).toHaveText('¥200')
  await button(page, '本次经营简报 已做的决定、实际结果与下一步')
  await expect(page.getByRole('dialog')).toContainText('在库：70 件；在途：0 件')
  const d = page.waitForEvent('download')
  await button(page, '保存简报')
  const downloaded = await d
  await downloaded.saveAs(info.outputPath('business-brief.txt'))
  const actualDashboard = await (
    await page.request.get('/api/backend/api/v1/dashboard?store_id=' + id)
  ).json()
  await info.attach('real-state', {
    body: JSON.stringify({
      storeId: id,
      dashboard: actualDashboard,
      actions: await actions(page, id),
      firstAction: first,
    }),
    contentType: 'application/json',
  })
  expect(errors).toEqual([])
})

test('真实非推荐20：后端生成新版本；已有后端随后再次建议补足20', async ({ page }, info) => {
  const id = await scenario(page)
  await start(page)
  await button(page, '补 20 件 现金 ¥800 · 预计缺 20 件')
  await expect(
    page.getByRole('heading', { name: '你正在查看：补 20 件', exact: true }),
  ).toBeVisible()
  await buy(page, 20, '¥800')
  expect(await actions(page, id)).toHaveLength(1)
  await expect(page.getByRole('button', { name: '核对 20 件采购', exact: true })).toBeVisible()
  await expect(page.getByTestId('inbound')).toHaveText('20')
  await info.attach('documented-backend-difference', {
    body: '采购20件成功后，后端清除临时数量上限，并对剩余缺口再次推荐20件。前端如实显示，没有再次采购。此行为与v0.3原型保留少买取舍不同，留后端同学确认。',
    contentType: 'text/plain',
  })
  expect(await actions(page, id)).toHaveLength(1)
})

test('真实拒绝与警报知晓：无采购，知晓不等于解除', async ({ page }) => {
  const id = await scenario(page)
  await start(page)
  await button(page, '本轮暂不补货 现金 ¥1,000 · 预计缺 40 件')
  await button(page, '记录本轮取舍')
  await button(page, '记下这次取舍')
  await expect(page.getByRole('heading', { name: '暂时没有新的决定', exact: true })).toBeVisible()
  expect(await actions(page, id)).toHaveLength(0)
  await page.reload()
  await expect(page.getByRole('heading', { name: '暂时没有新的决定', exact: true })).toBeVisible()
  await page.getByRole('button', { name: /项经营提醒，查看依据/ }).click()
  await button(page, '标记已知晓')
  await expect(page.getByRole('dialog')).toContainText('已知晓，尚未解除')
  const r = await page.request.get(
    '/api/backend/api/v1/alerts?store_id=' + id + '&status=ACKNOWLEDGED',
  )
  expect((await r.json()).items.length).toBeGreaterThan(0)
  expect(await actions(page, id)).toHaveLength(0)
})

test('真实采购丢响应：刷新后沿用同一确认恢复，不产生第二笔', async ({ page }) => {
  const id = await scenario(page)
  await start(page)
  let hideReads = false
  await page.route('**/api/backend/api/v1/actions?*', (r) =>
    hideReads ? r.abort('connectionreset') : r.continue(),
  )
  await page.route('**/api/backend/api/v1/plans/*/decision', async (r) => {
    await r.fetch()
    hideReads = true
    await r.abort('connectionreset')
  })
  await button(page, '核对 40 件采购')
  await button(page, '确认采购 40 件 · ¥400')
  await expect(page.getByRole('heading', { name: '确认结果尚未取得', exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: '确认结果尚未取得', exact: true })).toBeVisible()
  expect(await actions(page, id)).toHaveLength(1)
  await page.unroute('**/api/backend/api/v1/plans/*/decision')
  hideReads = false
  await button(page, '查询原确认结果')
  await expect(page.getByTestId('cash')).toHaveText('¥600')
  expect(await actions(page, id)).toHaveLength(1)
})

test('旧接口能力降级：可比较20件但禁止确认，仍能拒绝原方案', async ({ page }) => {
  await page.route('**/api/session', async (r) => {
    const response = await r.fetch()
    await r.fulfill({ response, json: { ...(await response.json()), planRevision: false } })
  })
  const id = await scenario(page)
  await start(page)
  await button(page, '补 20 件 现金 ¥800 · 预计缺 20 件')
  await expect(page.getByRole('button', { name: '核对 20 件采购', exact: true })).toBeDisabled()
  await expect(
    page.getByText('此后端暂不支持确认其他数量；可以比较，或确认当前推荐。'),
  ).toBeVisible()
  await button(page, '本轮暂不补货 现金 ¥1,000 · 预计缺 40 件')
  await button(page, '记录本轮取舍')
  await button(page, '记下这次取舍')
  expect(await actions(page, id)).toHaveLength(0)
})

test('报价本地工具：实际文件输入、甲乙计算、原币种和下载', async ({ page }, info) => {
  await page.goto('/')
  await button(page, '整理一份供应商报价 查看单件价、包装、起订量与来源')
  await button(page, '使用示例报价甲')
  await button(page, '开始整理')
  await expect(page.getByRole('dialog')).toContainText('折合 24 件')
  await button(page, '记下以后的整理要求')
  await button(page, '以后按这些步骤整理')
  await button(page, '换一份示例报价乙')
  await button(page, '开始整理')
  await expect(page.getByRole('dialog')).toContainText('折合 45 件')
  await expect(page.getByRole('dialog')).toContainText('¥12')
  const d = page.waitForEvent('download')
  await button(page, '保存本次结果')
  await (await d).saveAs(info.outputPath('quote-B.csv'))
  expect(await fs.readFile(info.outputPath('quote-B.csv'), 'utf8')).toContain('"12"')
  await page.locator('#quote-file').setInputFiles({
    name: '美元报价.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(
      '商品,报价金额,币种,计价单位,每包装件数,最低订购量,MOQ单位,来源\n样品,120,USD,箱,12,2,箱,报价单',
    ),
  })
  await button(page, '开始整理')
  await expect(page.getByRole('dialog')).toContainText('120 USD')
  await expect(page.getByRole('dialog')).not.toContainText('¥120')
  await expect(page.getByRole('dialog')).toContainText('暂不能计算')
  await page.screenshot({ path: info.outputPath('quote-currency.jpg'), type: 'jpeg', quality: 80 })
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
})

test('历史窗口：受控分页响应超过30条，轮询后仍保留旧记录', async ({ page }) => {
  const timeline = Array.from({ length: 60 }, (_, i) => ({
    id: 'timeline-' + i,
    mission_id: 'any',
    type: 'CHECK',
    summary: '可追溯记录-' + i,
    actor_type: 'SYSTEM',
    actor_id: null,
    references: [],
    created_at: new Date(Date.now() - i * 1000).toISOString(),
  }))
  await page.route('**/api/backend/api/v1/missions/*/timeline?*', async (r) => {
    const old = new URL(r.request().url()).searchParams.has('cursor')
    await r.fulfill({
      json: {
        items: old ? timeline.slice(30) : timeline.slice(0, 30),
        next_cursor: old ? null : 'older',
      },
    })
  })
  await scenario(page)
  await start(page)
  await page
    .getByRole('navigation', { name: '主导航', exact: true })
    .getByRole('button', { name: '经营记录', exact: true })
    .click()
  await button(page, '加载更早记录')
  await expect(page.getByText('可追溯记录-59', { exact: true })).toBeVisible()
  await page.waitForResponse((r) => r.url().includes('/timeline?') && !r.url().includes('cursor='))
  await expect(page.getByText('可追溯记录-59', { exact: true })).toBeVisible()
})

test('手机：事实先于决策，改选与关闭弹层可用，无横向溢出', async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await scenario(page)
  await start(page)
  await expect(page.locator('.task-fact-summary')).toBeVisible()
  await expect(page.locator('.task-fact-summary')).toContainText('¥1,000')
  await page.screenshot({ path: info.outputPath('mobile-first.jpg'), type: 'jpeg', quality: 80 })
  await page.locator('.options-disclosure summary').click()
  await button(page, '补 20 件 现金 ¥800 · 预计缺 20 件')
  await button(page, '核对 20 件采购')
  await expect(page.getByRole('dialog')).toContainText('20 件 ×')
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.setViewportSize({ width: 320, height: 640 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(320)
})

test('Agent受控故障：刷新后仍展示最近失败；澄清等待可取消', async ({ page }) => {
  await scenario(page)
  await start(page)
  let status = 'FAILED'
  const cid = 'test-conversation',
    rid = 'test-run'
  await page.route('**/api/backend/api/v1/missions/*/conversations?*', (r) =>
    r.fulfill({
      json: {
        items: [
          {
            id: cid,
            is_default: true,
            active_run_id: status === 'WAITING_INPUT' ? rid : null,
            followup_enabled: false,
            followup_version: 1,
          },
        ],
        next_cursor: null,
      },
    }),
  )
  await page.route(`**/api/backend/api/v1/conversations/${cid}/messages?*`, (r) =>
    r.fulfill({
      json: {
        items: [
          {
            id: 'test-message',
            conversation_id: cid,
            seq: 1,
            role: 'user',
            content: '解释当前方案',
            run_id: rid,
            references: [],
            created_at: new Date().toISOString(),
          },
        ],
        next_after_seq: null,
      },
    }),
  )
  const run = () => ({
    id: rid,
    conversation_id: cid,
    status,
    interrupt_id: 'test-interrupt',
    question: status === 'WAITING_INPUT' ? '请补充偏好内容' : null,
    error_code: status === 'FAILED' ? 'AGENT_MODEL_FAILURE' : null,
  })
  await page.route(`**/api/backend/api/v1/agent-runs/${rid}`, (r) => r.fulfill({ json: run() }))
  await page.route(`**/api/backend/api/v1/agent-runs/${rid}/cancel`, (r) => {
    status = 'CANCELLED'
    return r.fulfill({ json: run() })
  })
  await page.reload()
  await expect(
    page.locator('.agent-run-note').filter({ hasText: 'AGENT_MODEL_FAILURE' }),
  ).toBeVisible()
  status = 'WAITING_INPUT'
  await page.reload()
  await expect(page.getByText('请补充偏好内容', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '停止本轮回答', exact: true }).click()
  await expect(page.getByText('请补充偏好内容', { exact: true })).toHaveCount(0)
})
