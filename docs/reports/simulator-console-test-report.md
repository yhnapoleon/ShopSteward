# Simulator Console 首版交付与验收

日期：2026-09-07。Git 基准 `YH / 4389747`；本次代码未提交。用户批准范围：持久化模拟数据、可配置场景和 Dashboard。Docker Desktop 由用户手动启动。

## 实际交付

复用 simulator 的 PostgreSQL 世界、事件、采购回执与幂等命令，增加 SANDBOX 初始条件、销售/需求修订/部分或全部到货 Trigger、本地 Dashboard。SC01 原有创建幂等内容与固定推进剧本保持兼容。迁移 `sim_0003_controls` 只增加 Run.configuration，既有数据保留。

界面支持模板、场景列表、源状态卡、操作预览、事件历史、联动初始化任务和 backend 观察。前端只访问同源 `/console/api`；服务器凭据没有进入静态资源。backend 场景初始化接受相同 SANDBOX 参数；事件仍由原 business worker 同步，Plan 及审批仍归 backend。

开发服务已运行：simulator/console 8001、backend 8000、business worker。backend 开发库增量升级至既有 `0009_agent_scopes`，Agent 关闭，本次没有模型调用。产品 `frontend/` 未修改。

## 自动测试与契约

| 检查 | 结果 | 范围 |
|---|---|---|
| simulator pytest | 23 passed，4.81 秒，0 failed/skipped | 专用 shopsteward_sim_test；原 12 项 + controls 7 项 + console 4 项 |
| backend＋Agent pytest | 226 passed，80.82 秒，0 failed/skipped | 专用测试数据库，完整回归；未启用真实模型 |
| Node UI 异步回归 | 3 passed | 实际 console.js + DOM/fetch mocks，无外部依赖或数据库 |
| Ruff check / format | 通过，32 Python 文件格式一致 | simulation 与 backend operations |
| node --check | 通过 | 最终 console.js |
| Alembic check | 无新增漂移 | simulator 与 backend 当前开发迁移 |
| 设计契约校验 | 通过 | backend 26 操作、services 10 操作、53 个示例及共享/负面用例 |
| 运行契约规范校验 | 通过 | backend 40 操作；simulator 9 操作；开启 console 19 操作 |

Controls 覆盖初始化持久化、同键并发仅一次、晚到重试回放原结果、不同内容键冲突、过时源序号、无库存销售回滚、预测为零时真实销售、真实订单分批到货、跨 run/超额到货拒绝、活动期边界、分页与 SC01/SANDBOX 模式隔离。Console 覆盖关闭时无路由、Host/Origin/peer/cross-site/JSON/header 边界与真实数据库写入。测试只操作专用测试库，不清空开发数据。

运行：`node simulation/tests/console_ui_regression.cjs`；其他命令见 [simulation README](../../simulation/README.md)。

## 真实服务验收

[HTTP 与重启证据](../api/simulator-console-acceptance-result.json)：13 项业务检查 + 3 项重启检查全部通过。新建三个联动场景，backend 创建 Mission 后，常规现金/库存场景推荐采购 40 件；低现金场景推荐 20 件；库存充足场景推荐 0 件。

主场景 `run_931cae4bac6f4fe5ab9c359e5f575779` 通过 backend 原审批 API 精确批准 Plan，等待真实 simulator ACCEPTED 回执，然后执行：收货 15 → 销售 5（单价 20 元）→ 剩余需求修订 90 → 收完余下 25。连续 5 个源事件均同步至 backend；最终现金 600 元、应收 100 元、现货 55、在途 0、需求 90、源序号 5，源头与后端逐项一致。四次同步等待实测约 3.03、5.92、4.97、4.02 秒，这是当前本机样本，不是延迟 SLA。

在后续事件已经发生后，重放早期销售原键仍返回原响应且不再次写入。只重启本任务拥有的 simulator 进程后，重新读取状态及原键重放均通过；连续序号仍为 5。原有场景没有被重置；第二次完整验收比较的 11 个既有 run 均保持原世界、快照、采购与进度。

首次验收的所有业务检查通过，但工具在最后执行“既有场景未改动”汇总时用了错误的异步迭代表达式而退出。已修复验收脚本并完整重跑；[首次证据](../api/simulator-console-acceptance-attempt1.json) 与其场景保留，没有把该次错误当作系统成功。重启比较使用 State DTO 规范化 datetime，避免 `Z` 与 `+00:00` 等价格式造成误报。

## 浏览器验收

[浏览器与最终状态证据](../api/simulator-console-browser-result.json)。通过真实页面执行，随后用只读 HTTP 断言数据：

- 独立创建 `run_40f1141f33c6443c99c8ed851537f2b4`，销售 3 件、单价 20 元，需求改为 80；刷新后现金 1000 元、应收 60 元、现货 17、需求 80、序号 2 保留。
- 联动创建 `run_ace55c8511fc4ae08030afffcc15e524`，页面完成初始化 job 轮询。通过原 backend API 创建 Mission/审批模拟采购 40 件后，页面登记 12 件、再收余下 28 件；最终现金 600 元、现货 60、在途 0、源序号及 backend 已同步序号均为 3。
- 页面正确显示当前 Plan ID、推荐数量、解释、事件与已解除警报。部分到货刷新后的剩余订单数量正确；全部收完后到货按钮消失。
- 1440px 桌面及 390px 窄屏检查通过。窄屏自动折叠创建器，场景导航局部横向滚动；文档 clientWidth 与 scrollWidth 同为 375px（扣除滚动条），无页面级横向溢出。浏览器无 error/warning。

## 审查修复与边界

独立审查复核事务锁、命令提交与事件原子性、幂等回放、来源边界、本地控制台和后端 HTTP 桥。增量复核发现并修复：读取错误覆盖未知写入重试入口、确定失败后仍锁住表单；切换场景加载期间旧 SC01 控件误用新 run；A→B→A 旧分页响应污染列表。三项保留为 Node VM 回归，复测均通过。另修复启动器选择 backend 身份时未优先使用环境变量的 AUTH_TOKENS。

首版为本机合成数据开发工具。联动创建导入店铺，不自动创建 Mission。没有远程多人权限管理、直接采购按钮、重置/删除世界、任意事件注入、随机流量、退款回款、故障注入、真实数据集导入或 RAG。报价/预测过期沿用既有业务约束；长期演示可创建新场景。Agent 跟进联调与产品前端验收是后续工作，本报告不声称已完成。

入口：<http://127.0.0.1:8001/console/>；启动、配置及可重复验收步骤见 [运行说明](../../simulation/README.md)。
