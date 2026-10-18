# ShopSteward 第二阶段 Eval 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking. 本文件只制定计划，不启动实现、模型调用或资源租赁。执行时在当前任务内顺序推进；是否委派子代理由用户另行指定。

**Goal:** 交付可以重复运行的补货决策评测，先产出 50 例基线，再交付 200 例开发集的动作、参数、实际任务完成率、延迟与成本报告，为后续 SFT 提供明确的补数依据。

**Architecture:** 冻结上下文评测单次决策；真实执行评测通过现有 Agent job 执行器注入点和工具网关完成。两层共享决策契约与评分口径，逐例输出证据，自动汇总模型对照和错误分布。使用本地文件与轻量 CLI，不建设独立评测平台。

**Tech Stack:** Python >=3.11、Pydantic、pytest、现有 OpenAIModel/httpx/SQLAlchemy/PostgreSQL；JSONL 存案例与逐例结果，JSON/CSV/Markdown 存指标和报告。Eval 不安装训练用 CUDA、TRL、PEFT 或模型权重。

**Spec:** [二阶段范围设计 v0.2](../specs/2026-09-14-phase2-task-model-data-eval-design.md)；[原计划第 4–6、11–12 章](2026-09-14-phase2-sft-data-eval-plan.md)。本计划按用户 2026-09-14 的新要求，把工作重心放在 Eval 实际产出和指标，缩减生产可靠性、稳定性和数据治理工作。

**状态与依据：**2026-09-14，E1–E6完成；所有案例/问题复核由Codex完成，人工复核为0。B2未配置，独立test300为后续工作。已核对当前代码提交 `30bed9f`。原范围设计与总计划当前为未跟踪文件，本次保留原样。除下方E1实施记录外，本文件中的路径、CLI与评测数字仍是实施约定，不代表已存在实现或实测结果。

**E1实施记录（2026-09-14）：**用户授权启动E1后，已新增决策/案例契约、validate CLI、50个规格候选和报告。逐例语义复核由Codex完成并标agent_reviewed，不冒称团队人工复核；真实执行和模型结果均尚未产生。后续进度见下方E2–E4实施记录。具体结果见[任务契约](../../reports/posttraining/task-contract-v0.md)与[规格统计](../../reports/posttraining/eval-e1-validation.json)。

**E1验证：**独立`.venv-pt`中的38项E1测试通过；业务环境中的58项Agent非数据库回归测试通过（其中包含新增契约测试，不与38相加计算唯一测试数）；Ruff检查与格式检查通过。validate确认50例、36核心/14挑战、58个决策目标，真实执行验证数量为0。

**E2–E4实施记录（2026-09-14）：**E2已完成；61项轻量测试与8项真实数据库集成测试通过。50例真实上下文已冻结，B0已完成50例/58决策（动作56/58、参数35/38、待复核0），B1模型探针成功，完整B1及真实执行批次随后后台运行。澄清复核继续由Codex完成并如实标agent_reviewed；不冒称团队人工复核。详见[scorer检查记录](../../reports/posttraining/eval-e2-checks.md)。2026-09-15已完成：B1动作58/58、参数38/38、核心执行36/36；B0核心34/36，所有待复核为0。真实回执抽查由Codex完成，不冒称人工。详见[smoke报告](../../reports/posttraining/smoke-v1/comparison.md)。

**最终交付（2026-09-15）：**dev B1动作228/230、完整参数151/151、核心执行139/140；B0核心89/140。所有待复核和环境错误0；B0三项按协议禁止继续的后续步保留失败。全部E1–E6产物完成，详见[dev报告](../../reports/posttraining/dev-v1/comparison.md)及[交接](../../reports/posttraining/eval-handoff-v1.md)。

## Global Constraints

- 首轮 SFT 只覆盖“补货场景下的工具选择、参数绑定、必要澄清”。
- 首轮入口是已有 Mission 的用户对话；无 Mission 的通用事项处理器不作为本轮依赖。
- 不训练开放式经营分析、预测计算、长报告生成、通用异常诊断或自主采购。
- 所有业务执行仍走现有授权、版本和幂等协议；模型不能提供服务密钥或审批凭据。
- 实际经营金额继续使用整数分；采购数量沿用后端严格整数及范围约束。
- Python 版本下限沿用项目 `>=3.11`；训练环境与业务应用环境分开锁定依赖。
- 每次模型响应一个动作；一个 episode 最多两次决策，第二次仅用于一次必要澄清后的回复。
- 数量上限与精确购买数量不同；`0` 与 `null` 不同；数量、ID 和版本错误不能由执行器改正后计为模型正确。
- 本阶段不以达到目标分数为交付条件；低分但口径清晰、可复查的基线同样是有效产出。

---

## 1. 阶段交付与取舍

### 1.1 必须交付

| 产物 | 具体内容 | 验收方式 |
|---|---|---|
| 任务契约 | 五类动作、数量语义、必要上下文、澄清 rubric | 每类案例都有明确允许动作和成功条件 |
| smoke-50 | 50 个完整 episode，含正常及边界表达 | 全部可解析；逐例金标人工复核；生成可读清单 |
| dev-v1 | 200 个 episode，含 smoke-50，140 核心 + 60 挑战 | 200 个唯一 ID；每条有来源家族与预期；报告分组数量 |
| 决策评测 CLI | 固定上下文 → B0/B1/B2 → 单动作解析 → 评分 | 一条命令产生逐例记录及汇总，离线重评分不再调用模型 |
| 执行评测 CLI | 独立 fixture → 同一决策策略 → 真实工具 → 状态评分 | 先完成 36 个核心 smoke 案例，再覆盖 dev 的 140 个核心案例 |
| 基线报告 | B0/B1 必做；B2 服务可用时追加 | 每个模型列明动作、参数、任务成功率、延迟、用量和成本 |
| 失败清单 | 每个失败的原输入、预期、预测、错误类型与修复方向 | smoke 全查；dev 失败全部归类，至少 20 个代表例解释，少于 20 则全列 |
| Data 交接清单 | 优先补充的 3–5 类场景、失败占比、建议配对方式 | 可以据此生成新的训练种子；不直接把 dev 案例放进训练集 |

B2 为未 SFT 的基础 instruct 模型，沿用总计划 7–8B 候选方向。无可用服务时先交付 B0/B1，标记“基础模型与 SFT 的对照尚未完成”，不为启动 Eval 强制租 GPU。已有服务端点由配置指定；不自行假定账号、模型名称或价格。

### 1.2 工作量控制

建议约 70% 精力用于案例、评分和错误分析，20% 用于 runner 与真实工具接入，10% 用于记录和使用说明；这是优先级而非精确工时统计。

本阶段不新增并发压测、长时间稳定性运行、重试恢复框架、监控告警、自动部署、复杂脱敏系统、对象存储发布服务或人工标注平台。沿用项目现有鉴权和测试库约束即可。

只保留影响评测是否成立的基本措施：执行使用已有专用测试库；模型输入与标准答案分开；同源案例不跨 train/dev/test；记录实际输出与工具回执。这些不独立发展为工作包。

版本冲突、取消、未知写入回执和生产幂等压力测试仍归总计划 W2/W7。本计划测正常请求的实际业务效果，不能据此宣称产品可靠性验收已经完成。展示仅核对真实回执构成的最小结果摘要，不安排前端自动化或完整工作区接入。

## 2. 仓库现状与复用方式

| 已有代码 | 已确认能力 | 本阶段用法 |
|---|---|---|
| `agent/src/shopsteward_agent/model.py` | `OpenAIModel.complete(messages, tools, *, tool_choice=None)` 返回 content、tool_calls、usage | 复用一次模型调用；通过注入 client 固定采样，不改通用 Agent 默认参数 |
| `backend/app/agent_bridge/tools.py` | `EvaluationArgs`、`RevisionArgs`、`tool_schemas` 和真实网关 | 导出受限工具 schema；调用现有网关；来源由后端绑定 |
| `backend/app/agent_bridge/jobs.py` | `make_handlers(settings, executor=...)` | 为 Eval 注入最薄执行函数，取得合法 run 上下文，不先改生产 composition |
| `backend/tests/integration/test_agent_tools.py` | 从消息和 Agent Run 调用试算/修订并检查业务变化 | 提取可复用 setup 逻辑和断言思路 |
| `backend/tests/integration/test_plan_revision_api.py` | 正常修订与 null 清除上限已有测试 | 用于 fixture 预期验证；网关行为仍需独立验证 |
| `backend/tests/integration/test_missions.py`、`test_agent_runs.py`、`test_planning_jobs.py` | 店铺初态、Mission、Plan、消息与 job 构造 | 将需要的构造逻辑抽到 Eval fixture；CLI 不导入 pytest 测试模块 |
| `backend/tests/integration/conftest.py` | `TEST_DATABASE_URL`、库名 `shopsteward_test`、迁移就绪检查 | 原样沿用约束，不另写环境管理系统 |

最初规划时没有 `posttraining/` 或 `task_policy/`，本轮已新增。Eval 先新增共享决策契约与纯决策调用器；真实执行通过 job 的已有注入点完成。以后 W2 接入产品时复用这些模块，不复制一套模型判断或业务计算。

现有默认 fixture 在上限 20 时可能正好购买 20，但通用 scorer 必须检查“实际采购量 ≤ 上限”。另加一个上限较宽、实际建议量较少的 fixture，防止复制测试里的特殊断言。

后端对修订来源仍有关键词检查。语义正确而收到 `EXPLICIT_REVISION_REQUIRED` 或 `HYPOTHETICAL_ONLY` 的案例记 `backend_policy_mismatch`；保留决策得分和执行失败，不通过修改原用户消息绕过。修后端规则不是本阶段默认任务。

## 3. 案例集与金标

### 3.1 数量分配

| 任务 | smoke-50 | dev-v1 | 主要覆盖 |
|---|---:|---:|---|
| PT-01 假设试算 | 10 | 40 | 普通上限、0、上界、中文数字 |
| PT-02 明确修订 | 10 | 40 | 完整数量表达、当前对象、不同版本 |
| PT-03 否定修改、仅试算 | 8 | 30 | “先别改”、前后纠正、否定优先 |
| PT-04 缺少数量 | 8 | 30 | 问必要缺项，收到完整有效回复后执行 |
| PT-05 历史指代 | 3 | 12 | 唯一指代、多个冲突数量、来源受限 |
| PT-06 撤回 | 3 | 10 | 结束当前请求，不撤销 Mission |
| PT-07 非法数量 | 4 | 16 | 负数、小数、超上界、零附近表达 |
| PT-08 范围外 | 2 | 10 | 季度报告等应转交请求 |
| PT-09 单位歧义 | 1 | 8 | 无依据将箱换算为件 |
| PT-10 取消额外上限 | 1 | 4 | 明确 null；与上限 0 成对比较 |
| 合计 | 50 | 200 | 核心 PT-01–04：36/140；挑战：14/60 |

smoke-50 是 dev-v1 的子集，不重复计算独立样本。先实现四类核心任务，边界样本按表补足。dev 至少包含 40 个来源家族，每个家族不超过 10 个 episode；记录实际家族分布，不把同一模板改写当独立证据。

每个 episode 明确一组允许动作，不保留“clarify 或 handoff 都差不多”的未定标签。PT-09 默认选择 `clarify`，询问换算关系；不提供回复的边界案例只评价本次澄清，不混进核心任务完成率。

PT-04 的脚本回复使用完整句，例如“把本次采购上限改成 20 件”。回复只在模型正确询问缺项后进入第二步；模型没问或问错时不得无条件发送答案帮其完成任务。第二步上下文包含真实第一步问题与脚本回复。

PT-10 在真实网关验证前不进入可发布案例集；若网关拒绝但工具语义明确，记录明确修订金标和集成限制。不得把执行失败改标成模型应当澄清。

### 3.2 数据格式示例

下面的 `$current_plan_id` 等引用由 fixture 映射成真实值；冻结决策集保存映射后的可见输入。

```json
{
  "episode_id": "dev-pt01-001",
  "task_type": "PT-01",
  "scenario_family": "cap-hypothesis-direct-01",
  "split": "dev",
  "suite": "core",
  "fixture_recipe": "replenishment_standard",
  "user_message": "如果本次采购上限是20件，会怎样？",
  "followup_user_message": null,
  "expected_steps": [{
    "allowed_actions": ["evaluate_plan"],
    "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 20},
    "clarification_slot": null
  }],
  "final_predicates": [
    "receipt_ok", "current_plan_unchanged", "task_constraints_unchanged",
    "cash_stock_transit_unchanged", "no_purchase_created"
  ]
}
```

语义边界写入契约：数量范围 `[0, 1000000]` 的严格整数或明确 `null`；浮点数、布尔值不能作为整数；工具调用必须显式给出 `max_purchase_qty`，缺失不能自动视为 null。`plan_id`、`expected_mission_version` 与可见状态严格比较。

澄清 rubric 三项：问到了该例指定缺项；没有擅自假定数量或单位；没有要求用户提供系统已知的 Plan ID。每项 0/1，全通过才计正确澄清。首批人工复核全部澄清响应并保存结果；无复核的澄清只有动作选择得分，语义质量与依赖它的任务得分标 `pending_review`。不引入 LLM judge。

## 4. 指标和报告口径

### 4.1 主指标

| 指标 | 分子 / 分母 | 必须附带的明细 |
|---|---|---|
| 动作正确率 | 预测属于允许集合的决策 / 所有实际发起且环境正常的决策 | 五类动作混淆矩阵、逐 PT 类型得分；格式错误记错 |
| 完整参数正确率 | 工具及所有必要参数全对 / 预期为业务工具调用的决策 | 数量、Plan ID、版本三类错误数；选错工具仍进入分母 |
| 核心 episode 成功率 | 核心任务目标与业务谓词全部满足 / 全部核心 episode | 试算、修订、澄清后完成分别列出；环境失败也保留在此分母 |
| 澄清召回率 | 正确询问必要缺项 / 真正缺信息的初始请求 | rubric 复核状态；另列首次动作选择召回 |
| 无必要澄清率 | 信息充分却澄清 / 信息充分的初始请求 | 每个失败例的原文本与上下文 |
| 范围外/撤回正确率 | 对应 handoff/no_action 正确 / 对应任务样本 | 范围外与撤回分开列，不混入核心成功率 |

辅助指标：格式合法率；错误修订尝试次数/不允许修订样本数；实际错误业务修改次数；模型决策 P50/P95；任务耗时 P50/P95；输入/输出 token；成本；后端拦截数和环境错误数。业务状态检查用于判断任务是否完成，不扩展成专项安全测试。

分母细节：

- 每份报告同时列 `scheduled_episodes`、`attempted_decisions`、`responded_decisions`、`environment_errors`、`pending_reviews`，每个比例显示分子/分母。
- 格式错误、空响应、多动作属于模型/协议失败，不从模型分母移除。HTTP 超时、服务不可用、测试库失败归环境/服务错误，另报端到端可用率与计入失败后的有效动作完成率，避免只展示有响应子集。
- 多轮任务第二步没执行：核心 episode 失败；不虚构第二次模型响应。补报“预期决策步骤覆盖数/总预期步骤”，使少执行的模型无法仅靠更小分母显得更好。
- 执行评分允许同时出现“决策正确、执行失败”。模型错误、后端规则、fixture 错误分别归因；fixture 金标修复后所有模型在同版案例上重跑。
- 学生独立得分为主；首轮关闭自动兜底与协议修复。后续若测兜底，单开实验行并计入全部成本。

### 4.2 成本与时间

```text
单次 API 成本 = 输入 token / 1,000,000 × 输入单价
             + 输出 token / 1,000,000 × 输出单价
每成功任务成本 = 同一组全部尝试成本之和 / 该组成功 episode 数
核心任务耗时 = 本 episode 所有模型调用 + 工具执行 + 结果构造耗时
```

价格来自运行配置，记录币种与价格日期；usage 或价格缺失填 `unavailable`，不填 0。零成功时每成功任务成本填 `not_computable`。自部署模型另列 GPU/服务时间与资源成本，不能因为 API 单价为 0 就称免费。

fixture 创建、预热、人工复核和人工回复等待不计入模型或任务时延，分别记录。PT-04 脚本回复没有真实用户等待时间，报告明确“排除用户思考时间”。每个模型先用 3 个不计分案例预热；单并发，每例一次，不安排压力测试；首轮不给 P95 目标作通过门槛。

### 4.3 交付门槛与后续模型目标分开

**Eval 交付门槛：**50/200 例规格齐全；scorer 关键反例通过；B0/B1 有完整结果；核心真实执行有逐例证据；指标可从原始记录重新计算；失败有分类和补数建议。未执行和待复核数量必须为 0 才能称对应报告完整。

**后续候选模型目标：**沿用总计划讨论值：动作正确率 ≥95%，完整参数正确率 ≥95%，核心成功率 ≥90%，无必要澄清率 ≤5%。是否作为正式门槛在基线后、训练前固定；不得为使模型过线修改金标。

SFT 后增加与 B2 的配对差异表：同一案例由错变对、由对变错、均对、均错。初步增益参考 +5 个百分点，但 200 例仅相差几例时按事实报告，不宣称统计显著。首次基线无需实现 bootstrap 或复杂显著性分析。

## 5. 文件与接口

所有路径相对 ShopSteward 根目录。新增文件按下列职责实现；仅在相应任务中创建，不预先生成空模块。

| 文件 | 职责 |
|---|---|
| `agent/src/shopsteward_agent/task_policy/contracts.py` | `PolicyContext`、`Decision`、`DecisionRecord`、五类动作 schema |
| `agent/src/shopsteward_agent/task_policy/policy.py` | 单次模型请求与严格解析；与未来 W2 共享 |
| `agent/tests/test_task_policy.py` | 解析、数量、版本及单动作契约检查 |
| `posttraining/pyproject.toml` | 独立轻量 Eval 包及 test extra；不加入根 uv workspace |
| `posttraining/README.md` | 安装、准备 fixture、评测与重评分说明 |
| `posttraining/tasks/replenishment_v0.json` | 任务定义、动作说明及成功谓词名 |
| `posttraining/datasets/smoke-50.jsonl`、`dev-v1.jsonl` | episode 规格 |
| `posttraining/datasets/split-manifest.json` | episode 与来源家族分区清单及文件 hash |
| `posttraining/configs/eval_smoke_v1.json`、`eval_dev_v1.json` | 案例、模型配置、输出目录、运行模式 |
| `posttraining/src/shopsteward_pt/eval/records.py` | `EpisodeSpec`、`EpisodeTrace`、`EpisodeScore` 与结果 schema |
| `posttraining/src/shopsteward_pt/eval/fixtures.py` | fixture 构造、上下文读取、业务字段快照与真实网关适配 |
| `posttraining/src/shopsteward_pt/eval/policies.py` | B0 规则和 B1/B2 配置装配 |
| `posttraining/src/shopsteward_pt/eval/runner.py` | 决策模式/执行模式、脚本澄清、用量与时间采集 |
| `posttraining/src/shopsteward_pt/eval/scorers.py` | 动作、参数、rubric 合并与业务谓词评分 |
| `posttraining/src/shopsteward_pt/reporting.py` | 指标、混淆矩阵、失败清单及配对比较 |
| `posttraining/src/shopsteward_pt/cli.py` | `validate`、`freeze`、`evaluate`、`rescore`、`report` 入口 |
| `posttraining/tests/test_eval_contract.py`、`test_scorers.py`、`test_eval_runner.py`、`test_reporting.py` | 只测试会影响指标真伪的关键行为 |
| `backend/tests/integration/test_task_policy_eval.py` | 真实网关与状态断言的最小集成验证 |
| `docs/reports/posttraining/` | 可审阅的基线报告、失败分析、Data 交接清单 |

总计划原建议 YAML，本阶段配置统一用 JSON，避免为少量配置加解析依赖。后续 data/train CLI 可以沿用 JSON；若统一改回 YAML，单独更新消费者配置。原计划不在此次覆盖修改。

接口约定：

```python
# 函数签名为实施目标；全部接口在本节定义。
async def decide(context: PolicyContext) -> DecisionRecord: ...
async def freeze_contexts(specs: list[EpisodeSpec], config: dict) -> list[dict]: ...
async def run_episode(spec: EpisodeSpec, policy_id: str, *, mode: str,
                      config: dict, frozen_context: dict | None = None) -> EpisodeTrace: ...
def score_episode(spec: EpisodeSpec, trace: EpisodeTrace,
                  reviews: dict[str, dict]) -> EpisodeScore: ...
def summarize(scores: list[EpisodeScore], traces: list[EpisodeTrace]) -> dict: ...
```

`PolicyContext`：messages、mission_id、plan_id、mission_version、quantity_unit、quantity_cap、tool_schemas、context_version。`Decision`：name、arguments。`DecisionRecord`：decision（解析失败为 null）、raw_response、parse_error、usage、latency_ms。

`EpisodeSpec` 字段见第 3.2 节。`EpisodeTrace`：episode_id、policy_id、mode、context、steps（逐步 DecisionRecord）、receipts、before_state、after_state、delivery、environment_error、timing、cost。`EpisodeScore`：episode_id、policy_id、mode、per_step（action_correct、arguments_correct、format_valid、clarification_correct）、predicate_results、episode_success、failure_tags、review_status。不可用的评分字段为 null，并在汇总中列明原因。

`before_state/after_state` 只采集本任务相关字段：current_plan_id、mission_version、task_constraints、policy、旧 Plan 的 document/status、新 Plan、现金、库存、在途和采购行动 ID 集合。修订允许旧 Plan 的 status 变为 SUPERSEDED，但其原始 document 必须保留；不能断言整个旧记录不变。

冻结上下文的控制：`freeze` 先由真实 fixture 导出模型可见状态；决策 runner 严禁读取 expected 字段。执行模式每例创建等价业务初态，使用运行时真实 ID；模型间按相同 recipe 和数值状态对照，不强求隔离数据库对象具有相同 UUID。ID 只做占位符到真实对象的输入映射，不纠正模型输出。

## 6. 实施任务

### E1：固定契约，产出 smoke-50

**文件：**新增 contracts.py、records.py、replenishment_v0.json、smoke-50.jsonl、split-manifest.json、test_eval_contract.py、test_task_policy.py；轻量包配置、初始化文件与 validate CLI 随本任务创建。

**输入/输出：**总计划 PT-01–10 → `PolicyContext/Decision/EpisodeSpec`、50 个可读可解析案例。

- [x] 按第 3.1 节写 50 例；先完成 36 个核心案例，每例填写 expected_steps 和 final_predicates。
- [x] 增加数量语义测试：布尔值、负数、小数不合法，0/null 合法；缺少上限字段与显式 null 分开。
- [x] 实现 Pydantic 契约、`validate` 和案例清单导出；五类动作之外的名称或多个 tool_call 判错。
- [x] 逐例复核 50 例的动作与数量语义，输出 `task-contract-v0.md` 和 `smoke-50-cases.md`。本轮复核者为Codex；原拟人工复核尚未发生，团队可继续在清单上审阅，不计为E1编码阻塞项。
- [x] 运行契约测试；所有案例可解析且分组计数与表一致后完成本任务。

关键验收测试（由实际 Decision Pydantic 模型执行）：

```python
import pytest
from pydantic import ValidationError
from shopsteward_agent.task_policy.contracts import Decision

@pytest.mark.parametrize("qty", [True, -1, 20.5, 1000001])
def test_invalid_quantity_is_not_silently_coerced(qty):
    with pytest.raises(ValidationError):
        Decision.model_validate({"name": "evaluate_plan", "arguments": {
            "plan_id": "fixture-plan", "max_purchase_qty": qty}})

@pytest.mark.parametrize("qty", [0, None, 1000000])
def test_valid_quantity_preserves_type_and_value(qty):
    result = Decision.model_validate({"name": "evaluate_plan", "arguments": {
        "plan_id": "fixture-plan", "max_purchase_qty": qty}})
    assert result.model_dump()["arguments"]["max_purchase_qty"] == qty
```

### E2：实现 scorer，确保分数有意义

**文件：**scorers.py、test_scorers.py；为测试增加 `posttraining/tests/fixtures/scorer_cases.json`。

**接口：**消费 EpisodeSpec/EpisodeTrace，产出 `score_episode(spec, trace, reviews)`。

- [x] 编写一组固定轨迹反例：选错工具、数量错、Plan ID 错、版本错、空/多动作、正确调用未执行、试算误写、上限较宽但采购量较少、缺失人工复核、正确语义被后端拒绝。
- [x] 实现严格结构比较：JSON 键顺序/空格无关；数量类型、null、对象和版本有关。
- [x] 实现试算/修订/撤回谓词，并合并澄清人工复核。`mode=decision` 不生成真实执行成功率。
- [x] 在固定轨迹中验证模型正确、业务执行失败可以同时存在；无工具回执不能计执行成功。
- [x] 运行全部反例，输出 scorer 检查摘要。

测试案例文件每条含 `spec`、`trace`、`reviews`、`expected_success`、`expected_failure_tag`。关键测试形态：

```python
import json
from pathlib import Path
from shopsteward_pt.eval.records import EpisodeSpec, EpisodeTrace
from shopsteward_pt.eval.scorers import score_episode

def test_known_business_counterexamples():
    path = Path(__file__).parent / "fixtures" / "scorer_cases.json"
    for row in json.loads(path.read_text(encoding="utf-8")):
        result = score_episode(EpisodeSpec.model_validate(row["spec"]),
            EpisodeTrace.model_validate(row["trace"]), row["reviews"])
        assert result.episode_success == row["expected_success"]
        if row["expected_failure_tag"]:
            assert row["expected_failure_tag"] in result.failure_tags
```

### E3：打通 50 例决策评测并立即出基线

**文件：**policy.py、policies.py、runner.py、fixtures.py 的冻结上下文部分、cli.py、test_eval_runner.py、eval_smoke_v1.json。

**接口：**`freeze_contexts` → PolicyContext；`decide` → DecisionRecord；`run_episode(mode="decision")` → EpisodeTrace。

- [x] 从现有 fixture 提取最少构造函数，创建真实 Plan 并导出 50 例冻结上下文，保留上下文文件 hash。
- [x] 实现 B0：明确的否定/假设优先规则、修改关键词与数字提取、缺项澄清和范围外路由；记录中文数字及复杂指代支持范围。B0 不读取 expected，也不特殊匹配 episode_id。
- [x] 复用 OpenAIModel 实现 B1/B2；同一 system prompt、工具 schema、输出预算、温度 0（端点不支持则记录实际设置），单次调用，不自动修复。
- [x] 运行 B0/B1 smoke-50。可用的 B2 同批加入；服务未配置不阻塞 B0/B1。
- [x] 导出 raw.jsonl、scores.jsonl、人工澄清 review.jsonl、summary.json、failures.csv、report.md；对所有澄清复核后用 rescore 更新报告。
- [x] 全量阅读 50 例失败，确认问题来自模型、上下文还是金标，得到第一份可讨论基线。

runner 的关键可测行为：给测试策略一个计数器和一个故意输出错误工具的结果，断言调用计数为 1、raw 输出原样保留、分数为错；若第二步需要澄清，初始问题问错时计数仍为 1。测试使用内存 fake client，不调用真实 API。

**验收：**相同冻结输入可比较 B0/B1；所有原始响应均有对应分数或明确环境错误；离线 rescore 不触发模型请求。

### E4：完成核心任务的真实执行评分

**文件：**fixtures.py 的执行适配、runner.py 的 execution 模式、test_task_policy_eval.py。

**接口：**消费同一 DecisionRecord，通过 `make_handlers(settings, executor=...)` 和真实 `/internal/v1/agent-tools/{tool}` 运行，产出 receipts/state/delivery；业务操作不在研究目录重写。

- [x] 在专用测试库创建初态、Mission、Plan、Conversation 和真实用户消息；沿用现有 job Runner 取得合法执行上下文。
- [x] 首先用固定正确决策执行 PT-01/PT-02，保存真实回执和前后状态差异。这只是验证 runner，不列作模型成绩。
- [x] 增加“宽上限、实际购买更少”、0/null 以及 PT-04 一次脚本澄清的验证；控制动作由最薄 harness 处理，不开发完整持久对话分支。
- [x] 模型调用 evaluate/revise 后，结果摘要只复制真实回执的数量、对象和状态；不让模型生成经营报告。
- [x] 运行 B0/B1 的 36 个 smoke 核心 episode；PT-05–10 的执行探针仅单列，不加入核心分母。
- [x] 将来源关键词拦截与模型错误分别统计；没有可用测试库时仍完成 E3，但本任务标未完成，不报告虚构执行分数。

**验收：**每个核心 episode 有真实执行或明确失败轨迹；PT-04 包含问答后工具执行。至少人工核对试算、修订、澄清各 2 例的原始回执与评分。可观察业务效果通过无需新增压力测试或生产 UI。

### E5：扩到 dev-v1，交付对照报告和 Data 建议

**文件：**dev-v1.jsonl、eval_dev_v1.json、reporting.py、test_reporting.py，以及 docs/reports/posttraining 下最终报告。

**接口：**`summarize(scores, traces)` 消费 E2–E4 结果；不在报告层重新猜测动作或业务成功。

- [x] 按第 3.1 节增加 150 例并复核，扩充来源家族和状态组合；保留 smoke ID，发布 dev-v1 与文件 hash。
- [x] 固定 B0/B1 的提示与配置，运行 200 例决策和 140 例核心执行；若修改提示调优另开 run_id，最终对照使用同版设置。
- [x] B2 可用时跑相同两套评测；同时列模型 revision/端点配置、工具与提示 hash、上下文版本、并发、价格和用量缺失数。
- [x] 自动生成按模型、PT 类型、suite、动作及错误类型的表格；给出动作混淆矩阵、参数错误拆解和成本明细。
- [x] 对所有失败归类，由Codex解释40个不同代表例（42条分析），人工复核为0；产出 3–5 项补数优先级，分别标“补数据”“修上下文/协议”“后端规则限制”。
- [x] 同一份 raw 数据重评分，核对报告总数；用包含一个选错工具、一个选对的人工账本验证完整参数正确率为 1/2，而不是 1/1。

**报告最低结构：**实验配置 → 总表 → 分任务结果 → 澄清与参数错误 → 实际执行结果 → 时延与成本 → 失败案例 → Data 下一步。不能只交一张总准确率图。

### E6：复现说明与后续 test 验收约定

**文件：**README.md、`docs/reports/posttraining/eval-handoff-v1.md`。

- [x] 写明完整安装和运行命令、输出位置、依赖测试库的步骤，以及如何重评分。
- [x] 写明缺 B2 时后续补测步骤；没有 B2 结果时不得产生 SFT 相对 base 的结论。
- [x] 为后续 test-v1 固定 300 例结构：200 核心 + 100 挑战；来源家族与 dev/train 独立，候选锁定前不运行 test 调提示。
- [x] 本阶段不要求立即编完并调用 300 例 test；在训练数据扩写前须先分配独立 test 来源家族。后续训练阶段建设 test 时沿用本阶段 runner/scorer。
- [x] 写明完成清单、已知限制、实测花费和剩余动作；为后续 data 阶段提供任务家族级建议，不导出 dev 正确答案当训练数据。

**验收：**另一位开发者能据 README 重新生成 smoke 报告；最终文档明确列出“50/200 已完成、B2 是否完成、真实执行覆盖、300 test 尚属后续工作”。

## 7. 最终运行入口

已实现的安装、测试库准备、validate/freeze/evaluate/rescore/report命令以[posttraining README](../../../posttraining/README.md)为准；原先规划的execution extra和report --run-root没有采用，不应复制旧草案命令。

实际单组目录：`var/posttraining/runs/{smoke-v1,dev-v1}/{decision,execution}/{B0,B1}`。包含manifest/specs/raw/scores/reviews/summary/failures/report。dev执行模式为140核心，带--suite core；decision为200例。run目录必须显式传入。完整环境使用根.venv和已有uv.lock，.venv-pt只负责纯契约/评分/报告。源码、数据、报告留在工作区，未自动提交或合并。

[最终交接](../../reports/posttraining/eval-handoff-v1.md)列出了成本缺失、B2状态、独立test300与Data后续。四组dev离线rescore完全一致，原始失败不改标。

## 8. 顺序、时间预算与完成判断

| 顺序 | 任务 | 集中工作预算 | 可见结果 |
|---|---|---|---|
| 1 | E1 契约与 50 例 | 0.5–1 天 | 案例表、动作与参数定义 |
| 2 | E2 scorer | 0.5–1 天 | 能拒绝错误轨迹的评分器 |
| 3 | E3 决策 runner 与基线 | 1 天 | 第一份 50 例模型对照 |
| 4 | E4 真实执行 | 1–1.5 天 | 36 核心案例的真实任务成功率 |
| 5 | E5 dev 扩展与分析 | 1–1.5 天 | 200 例决策、140 例核心执行和补数优先级 |
| 6 | E6 文档与交接 | 0.5 天 | 可复现操作说明与后续 test 约定 |

合计约 4.5–6.5 个集中工作日，假设模型 API 和迁移好的测试库可用；不含服务申请、GPU 部署、等待团队复核或后端独立修复。优先完成 E3 的第一份可讨论报告，不等 200 例全部完成才展示结果。

最终勾选：

- [x] 50 个 smoke、200 个 dev 案例及语义金标可审阅。
- [x] B0/B1 的 200 例决策报告、140 例核心执行报告完整；B2 状态明确。
- [x] 动作、完整参数、核心任务成功率的分子/分母清楚；澄清由Codex复核完成（人工复核0）。
- [x] 格式错误、后端拦截、环境失败及模型错误可区分。
- [x] 时延、token、成本有实测值或明确不可用原因。
- [x] 原始记录可离线重评分；失败案例有解释；Data 有 3–5 类可行动补数建议。
- [x] 报告明确本阶段不等于 SFT 效果验证、生产稳定性验收或 300 例独立 test 完成。

只要以上产物完整，即使基础模型未达到 95% 或当前 API 模型存在失败，Eval 阶段仍可验收。下一阶段根据测到的错误决定补什么数据，而不是以扩大量或训练完成作为默认成功标准。
