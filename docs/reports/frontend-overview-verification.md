# 经营概览前端验证

2026-09-08（新加坡时间）。以下验证基于cbe2046a916164133c0c8faf10cdc09b55f3ef6f之上的经营概览改动，在提交前完成；发布标识与远端CI以对应Git提交和PR为准。

默认路由仍是今日。新次级入口读取经营现状、现金余额事件变化、UTC销售汇总/明细、库存与采购到货，采用ECharts6.1.0。现有Agent会话、方案比较、审批、幂等、环境切换及后端源码未改。

发布前复验：2026-09-08再次fetch确认origin/main仍为cbe2046，无新增PR；类型、契约、构建和12项生产受控回归再次通过（2026-09-08T00:11:55.100Z，16.23秒）。

## 实际验证

| 检查 | 本轮结果与边界 |
|---|---|
| 前端类型 | typecheck通过 |
| 契约 | api:check通过；生成类型和公开路由白名单无改动 |
| 生产构建 | build通过，SVG line/bar按模块加载；图表chunk约545.55kB，gzip186.07kB，保留Vite体积提示 |
| 生产浏览器回归 | overview.spec.ts 12 passed / 0 failed / 0 skipped / 0 flaky；16.79秒；最终运行起点2026-09-07T16:24:37.212Z |
| 首页/懒加载 | 默认今日；进入概览前不请求图表引擎chunk，进入后才下载 |
| 原决策流程 | 进入概览并返回后仍可核对原推荐；换场景关闭旧确认框。测试不提交采购 |
| 查询边界 | 65条销售明细跨3页取得，汇总独立于第一页；UTC区间与金额切换；不改现金/库存日期 |
| 恢复与隔离 | 读取失败保留原值并明确标记；更换筛选不冒用旧区间总量；旧场景延迟响应不污染新环境；上下文不一致显式提示 |
| 空值/状态 | 单独过期流水、无现金变更、无委托底线、部分到货、未知ETA、期初缺失与现金不平分别处理 |
| 交互与手机 | 方向键/Enter选择图表、Escape/焦点恢复、日期弹层、手机无横向溢出；SVG尺寸必须与容器一致，不只用裁切隐藏溢出 |
| 真实GET冒烟 | 从已有历史场景读得现金400、在库70、已记录销量10；页面无异常、未发送写请求 |
| 服务加载 | 按已说明的需要重启本项目已登记API、simulator和business worker，24个既有场景现金/预留/待结算/库存/经营时点保持；active_store已返回，运行OpenAPI与已提交契约一致；真实模型仍关闭 |

浏览器回归全量拦截API响应，固定场景是可复现的合成样例，不是真实店主数据。S5视觉样例与真实GET的S6历史场景分别记录。测试不创建新场景、不改变模拟时间、不执行采购、不调用模型。原有会产生业务写入的business.spec.ts和真实模型E2E本轮未运行；后端代码未改，不声称完整业务/模型或跨平台端到端重新验收。

## 重跑

先运行本机前端，用以下命令执行常规受控测试（生产资产检查会跳过）：

```bash
corepack pnpm --filter @shopsteward/frontend exec playwright test tests/overview.spec.ts
```

验证生产前端时，构建后单独在本机启动frontend/.output/server/index.mjs，再指定该地址与开关：

```bash
FRONTEND_URL=http://127.0.0.1:3012 OVERVIEW_PRODUCTION=true corepack pnpm --filter @shopsteward/frontend exec playwright test tests/overview.spec.ts
```

示例环境变量写法为POSIX；Windows按现有PowerShell约定设置相同变量，不运行Mac启动器。新回归使用Node标准文件URL读取样例，未引入平台专用路径；本轮没有新Windows CI运行证据。

原始结果在Git忽略的var/frontend-e2e/results.json与其artifacts目录。交互截图、参考图并排对照及本地设计验视保留在个人项目成果中，不把机器绝对路径或整套私人资料写入公开仓库。

## 提交范围与限制

本次候选提交：frontend下的页面入口、BusinessFacts、BusinessOverview、OverviewChart、useOverview、overview工具与样式、两个受控样例、overview.spec.ts、README/style/nuxt/package，以及pnpm-lock.yaml和本报告。后端、Agent、simulation、生成类型、代理、现有useShop/DecisionCard/AgentConversation不在改动范围。

工作期间另有HANDOVER.md、PROJECT_CONTEXT.md、README.md、docs/architecture.md四份并行文档改动，未由本任务编辑或纳入候选提交。不能使用git add -A把它们混入前端提交。

本地工程检查通过后，按jeffrey→main的PR流程发布，远端Windows CI需独立通过。上述结果不等于正式部署、真实商家接入或长时性能验收；测试和生产服务不调用真实模型。
