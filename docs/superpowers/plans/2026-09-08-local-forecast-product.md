# B1-C 前端、LangGraph与全栈验收 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户在现有页面查看/更新预测，并让现有LangGraph实际调用受限预测工具、返回可追溯引用。

**Architecture:** 前端复用Nuxt同源代理和后端生成类型，只呈现backend预测。LangGraph复用现有model/tool/checkpoint主图，后端工具网关持有权限、版本和刷新逻辑；模型不直接调用8030。真实模型、浏览器、重启与故障证据分别记录。

**Tech Stack:** Nuxt/Vue/TypeScript、已有ECharts、Playwright；现有backend Agent bridge、LangGraph、官方Luna适配；本地ML和独立forecast worker。

**Spec:** [设计第10～13节](../specs/2026-09-08-local-forecast-design.md)；依赖[B公开契约与REPLAY](2026-09-08-local-forecast-backend.md)。

## Global Constraints

- 模型不直接决定采购量，不计算或更改现金账本，不审批，不使用 RAG 文本直接改预测。
- 全部门槛完成前状态为b1_ready=false。
- 前端不计算采购建议、不把202当完成、不从聊天正文解析预测数量或审批动作。
- 沿用frontend/style.md；机密只在服务端私有配置。只使用授权、隔离的场景和测试库。
- 正文、工具调用和持久引用必须对应实际运行；受控模型测试不计真实Luna验收。

---

## 文件与接口地图

前端创建`app/components/ForecastPanel.vue`、`ForecastChart.client.vue`、`app/composables/useForecast.ts`、`app/utils/forecast.ts`；修改`app/pages/index.vue`、`app/components/{BusinessFacts,DecisionCard,AgentConversation}.vue`中需要的挂载/引用位置。类型与路由白名单通过`scripts/generate-api.mjs`从backend.runtime生成，不手改生成物。

Agent创建`backend/app/agent_bridge/forecast_tools.py`；修改`tools.py`、`evidence_policy.py`、`composition.py`、必要的`jobs.py`最终发布复核和`triggers.py`调用位置。现有`agent/src/shopsteward_agent/runtime.py`保持通用；除非新测试揭示缺陷，否则不增加预测专用图节点。

全栈工具创建`backend/tools/verify_forecast_fullstack.py`、`verify_agent_forecasts.py`，扩展`infra/start_windows.py`和`infra/local_dev.py`的可选启动参数；文档写`docs/runbooks/forecast-local.md`与报告。

### Task C1: 前端预测读取、刷新和图表

**Files:** Create `ForecastPanel.vue`、`ForecastChart.client.vue`、`useForecast.ts`、`utils/forecast.ts`、`frontend/tests/forecast.spec.ts`；Modify `app/pages/index.vue`、`BusinessFacts.vue`、`DecisionCard.vue`、`app/assets/css/shop.css`；Generate `app/types/backend.d.ts`和`server/utils/backend-routes.ts`。

**Interfaces:** `useForecast(scope: Ref<{storeId:string,skuId:string}|null>)`返回`current,history,error,loading,refreshPending,load,requestRefresh,openVersion`；`requestRefresh(reason:string)`从当前DTO取binding_version并复用原幂等键；`ForecastPanel`接收scope及可选forecastId，历史模式不读取当前总量替换旧版本；`forecastLabel(source,modelName,mode)`只做显示。

- [ ] 先用Playwright受控响应写零值/未知的行为断言，测试fixture放`frontend/tests/fixtures/forecast.ts`并明确所有DTO字段来自B导出契约：

```ts
import { test, expect } from '@playwright/test'
import { installForecastPage } from './fixtures/forecast'

test('unknown prediction is not rendered as zero', async ({ page }) => {
  await installForecastPage(page, { forecastStatus: 'UNAVAILABLE' })
  await page.goto('/')
  await page.getByRole('button', { name: '查看预测依据' }).click()
  await expect(page.getByText('暂无可用预测', { exact: true })).toBeVisible()
  await expect(page.getByText('预计销量 0 件', { exact: true })).toHaveCount(0)
})
```

- [ ] `installForecastPage(page,options)`复用现有business测试的认证/店铺/任务只读响应，新增GET forecast处理；它必须是可读的固定契约夹具，不启动后台业务。运行`corepack pnpm --filter @shopsteward/frontend exec playwright test tests/forecast.spec.ts`确认缺界面失败。
- [ ] 用新runtime生成types/公开白名单，实现按需加载预测面板，历史28天实线/预测虚线/起点标记与可读数据表。不新增ECharts包，不用fixture伪装真实图表来源。无数据null与0清楚区分。
- [ ] useForecast为scope和每轮请求维护递增token或AbortController；切场景清理任务/版本/错误。测试A场景请求晚于B返回时仍显示B。history弹层绑定forecast_id，最新预测变更不污染旧Plan依据。
- [ ] 更新按钮权限取capabilities.refresh：202显示“更新已排队”；成功才刷新预测与现有useShop；未知写入结果保留原键，CAS409重新读取。测试READY+刷新失败、STALE、shadow、fixed无曲线、不可达服务、viewer禁用。
- [ ] 执行api:check/typecheck/build以及本任务Playwright；保存桌面/窄屏与键盘操作证据。提交`feat(frontend): show versioned demand forecasts`。

### Task C2: 后端Agent预测工具与权限

**Files:** Create `agent_bridge/forecast_tools.py`、`backend/tests/unit/test_agent_forecast_policy.py`、`backend/tests/integration/test_agent_forecast_tools.py`；Modify `agent_bridge/{tools,evidence_policy,composition}.py`。

**Interfaces:** `DEFINITIONS`按设计注册get_forecast/read_forecast_history/request_forecast_refresh；`call_forecast_tool(session,settings,principal,conversation,run,mission,store,name,args,invocation_id)->dict`；`forecast_requested(text:str)->bool`只识别明确预测读取；`can_request_forecast_refresh(roles:list[str],trigger:str,text:str)->bool`限制operator/admin与明确USER命令。

- [ ] 写权限测试：

```python
from app.agent_bridge.forecast_tools import can_request_forecast_refresh

def test_refresh_is_not_a_followup_write():
    assert can_request_forecast_refresh(["operator"],"USER","按最新销售更新预测")
    assert not can_request_forecast_refresh(["viewer"],"USER","更新预测")
    assert not can_request_forecast_refresh(["operator"],"FOLLOWUP","更新预测")
    assert not can_request_forecast_refresh(["operator"],"USER","如果更新预测会怎样")
```

- [ ] 运行聚焦测试确认失败；合并工具目录，参数extra=forbid，后端从绑定Mission取store/sku、当前USER消息做来源复核，不让模型指定scope/model/history/数量。读取fixed返回固定来源，读取不存在预测返回明确不可用而非猜测。
- [ ] 复用现有工具事务/租约：读/入队在短事务，ML HTTP由forecast worker执行；刷新工具返回job引用，无长轮询。相同ToolInvocation重放只入队一次。工具失败不得留下forecast引用。
- [ ] evidence_policy扩展明确“下周预计卖多少/预测依据/历史预测”必读；混合库存/预测/方案顺序get_dashboard→get_forecast→get_plan。否定预测查询、通用“什么是销量预测”不强制调用；不通过正则自动执行写操作。
- [ ] get_forecast加入Runtime的required_read_tools集合；工具返回status不可用时正文必须表达未知，即便工具HTTP成功。PG测试越店ID404、越权刷新、FOLLOWUP写拒绝、丢租约、模式切换、重复调用。
- [ ] 更新工具schema快照与API契约，保存`docs/api/agent-forecast-tools.json`用于核对实际catalog，不写虚构调用轨迹。提交`feat(agent): add authorized forecast tools`。

### Task C3: 预测引用、回答复核与主动解读

**Files:** Modify `agent_bridge/{composition,evidence_policy,jobs,triggers,forecast_tools}.py`、`frontend/app/components/AgentConversation.vue`、`ForecastPanel.vue`；Create `backend/tests/unit/test_agent_forecast_answer.py`、`frontend/tests/forecast-citations.spec.ts`；Modify `agent/tests/test_evidence_sequence.py`。

**Interfaces:** `forecast_answer_guard(result:dict,authority:dict,*,current_required:bool)->dict`对当前失效/越权/未成功引用作降级；`forecast_reference_changed(previous:dict,current:dict)->bool`区分业务结论变化与纯TTL续期；前端仅渲染后端返回type=forecast且字段合法的引用。

- [ ] 写失效引用测试：

```python
from app.agent_bridge.evidence_policy import forecast_answer_guard

def test_current_answer_cannot_claim_superseded_forecast():
    result = dict(content="预计60件",references=[dict(type="forecast",id="f1",version="v1")])
    checked = forecast_answer_guard(result,{"current_id":"f2","authorized_ids":["f1","f2"]},
                                    current_required=True)
    assert "FORECAST_CHANGED" in checked["validation_warnings"]
    assert checked["content"] != "预计60件"
```

- [ ] 先运行失败；实现最终工具结果与权限复核。复核至少在Agent最终保存Message的租约事务内进行，composition中读取的authority快照不能替代提交前检查；当前版本改变则标记变化，不借用旧版本假装当前。历史问答同scope有效旧版本仍可展示并附日期。
- [ ] 为预测总量输出后端标准化display字段；仅校验明确标注的总量/单位与已成功工具数据，不声称能验证所有语言。缺预测、对比不同时间范围、把预计说成保证、把统计基线说成训练模型的受控案例必须降级或纠正。
- [ ] AgentConversation遍历m.references，新增“预测依据”按钮，点击打开绑定forecast_id的ForecastPanel；引用跨场景或权限已失效显示不可访问，不跳到他店。刷新页面后Message.references与历史曲线不丢失。
- [ ] 仅用户已开启followup且预测可用性/候选/警报有变化时复用record_event；定义source_key=forecast:<id>:<decision_fingerprint>，重复发布幂等。纯TTL续期不因新增触发而重复解释；检查既有fingerprint包含state_version造成的自动跟进，增加业务语义比较避免刷屏，保留其他事件跟进。
- [ ] 运行受控LangGraph工具序列测试、权限/回答测试、引用浏览器测试。提交`feat(agent): preserve forecast evidence in answers and followups`。

### Task C4: 可启动环境与真实模型/浏览器验收

**Files:** Create `backend/tools/verify_agent_forecasts.py`、`verify_forecast_fullstack.py`、`docs/runbooks/forecast-local.md`；Modify `infra/{start_windows,local_dev}.py`、`frontend/README.md`、`agent/README.md`；Produce `docs/reports/forecast-fullstack.md`及`docs/api/agent-forecast-result.json`。

**Interfaces:** 两个verifier均接受`--backend-url --simulation-url --ml-url --frontend-url --output-dir`；fullstack增加`--verify-restart`。启动器增加`--with-forecast`并从私有env加载artifact/token；不自动下载数据、训练或迁移。

- [ ] 先验证启动配置：端口占用拒绝，artifact hash不匹配ready=false，token未配置不打印值；进程PID写自有记录，Windows隐藏启动。普通business+Agent在不启用预测时继续启动。
- [ ] 默认隔离端口8050/8051/8052/3050，使用独立backend/sim测试数据库，数据加载脚本先校验目标库名与schema。Docker必须已由用户启动，不能为了验收启动第二套现有开发服务。
- [ ] 以真实A制品和现有官方Luna配置运行以下矩阵，每项记录输入、Run ID、实际ToolInvocation、输出references和前后state/账本：

| 场景 | 必须观察的实际行为 |
|---|---|
| “未来一周预计卖多少” | get_forecast返回模型日期/总量/来源，正文与引用一致 |
| “为什么建议补这些货” | dashboard+forecast+plan三种证据对应同一scope |
| “按最新销售更新预测” | 授权刷新工具返回job受理；worker成功后前端出现新版本 |
| “如果只补20件” | 原evaluate_plan，只读；不改预测、审批或账本 |
| “上次预测为什么不同” | read_forecast_history和历史引用；说明范围/资料差异 |
| ML失联/资料不完整 | 不虚构销量，不用固定60件冒充模型；既有采购核对继续 |
| 越权/提示要求直接采购 | 不调用审批、切模型或越店读取 |
| 库存+供应商条款+预测 | 保留原业务/文档检索与新增预测工具边界 |

- [ ] 浏览器完成一次REPLAY创建→初始预测→新方案→用户确认→推进日→新预测/方案→历史预测引用展开；至少一次关闭真实Agent确认业务仍可运转。对期末h<7、不完整日、零预测各保留证据。
- [ ] 真实Luna缺配置或调用失败只记录未覆盖，不用fake结果填充。实测的费用/调用次数从真实usage记录，配置凭据不写报告。
- [ ] 完成手册：Windows/macOS依赖、训练重建、制品复制校验、三类worker、模型切换/回退、端口、HTTP错误、观察时间/经营时间、备份与恢复步骤。提交`test(forecast): verify frontend and live LangGraph integration`。

### Task C5: 全进程恢复、最终质量门槛与交接

**Files:** Modify fullstack verifier、`docs/reports/forecast-fullstack.md`、`docs/runbooks/forecast-local.md`、`PROJECT_CONTEXT.md`、`HANDOVER.md`；Produce `docs/api/forecast-fullstack-result.json`。

- [ ] 启停前保存当前artifact hash、forecast_id/日曲线、Plan hash、任务/会话/Run/Message引用、Action回执、各账本数量和精确金额库存。
- [ ] 停止自有ML/API/business/forecast/Agent/frontend/simulator，保留数据库；重启后`--verify-restart`逐项对比，原预测证据不可变化。墙钟TTL过期允许显示STALE，不允许改写旧曲线或通过重启伪续期。
- [ ] 注入预测刷新丢响应、worker处理中断、最终回答发布前换预测版本、浏览器刷新和切场景；检查旧结果不能覆盖新scope、同键不重复发布、采购不重复、Agent引用不声称过期版本当前有效。
- [ ] 一次运行必要回归：ml全测试；backend预测/业务相关unit/API/PG与契约；simulator原SC01/SANDBOX/REPLAY；agent runtime/证据序列；frontend api:check/typecheck/build与相关浏览器。没有数据库/真实模型时的skip单独记录，不能计通过。
- [ ] 依设计门槛填写六个ready状态。模型离线/经营效果不过关则b1_ready=false，保留技术已接通说明；不得把通过比例变成虚构完成率。
- [ ] 更新两份交接顶部为当日真实结果、代码commit、模型版本、数据hash、当前运行服务和待办；旧知识pilot/MVP状态按其实际结果保持独立。聚焦diff/制品清单/机密检查后提交`docs: hand over verified local forecasting pipeline`。

## C交接结果

用户可以从已有页面查看来源和预测，显式请求刷新，经LangGraph读取真实预测引用，并在模拟经营中观察预测变化如何影响方案。预测服务离线时系统能说明缺少依据，采购执行和历史核对不被模型故障阻断。只有完整实测满足门槛才宣布B1首版完成。
