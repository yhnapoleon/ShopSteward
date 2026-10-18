# Task Policy 修复与复评 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking. 在当前任务内顺序执行；本计划不要求启动子代理。

**Goal:** 对齐受限补货决策的数量语义、单位和澄清协议，验证修复是否减少实际任务失败，并输出可直接用于 Data 阶段的剩余能力缺口。

**Architecture:** 保持“固定上下文 → 一次模型决策 → 现有真实工具”的架构。将现有提示原样保留为 v1，新增可配置的 v2，在相同冻结输入上做针对性对照，再对原 dev200/core140 复评。仅为实验增加提示版本选择和补充统计，不增加通用恢复循环或自动纠错层。

**Tech Stack:** Python >=3.11、Pydantic、pytest、现有 OpenAIModel/RestrictedPolicy、PostgreSQL 测试 fixture、现有 posttraining runner/scorer；不新增依赖。

**Spec:** [二阶段设计](../specs/2026-09-14-phase2-task-model-data-eval-design.md)、[原 Eval 计划](2026-09-14-phase2-eval-implementation-plan.md)、[Eval 交接](../../reports/posttraining/eval-handoff-v1.md)、[失败证据](../../reports/posttraining/dev-v1/failure-analysis.md)。本文件是修复决策及执行计划，状态为“已完成：R1–R4”；执行与复评已完成，实际结果及剩余问题见文末交付记录。

## 1. 可用产出与边界

| 项目 | 本轮安排 |
|---|---|
| 可用结果 | 非法数量得到必要澄清；最低/精确数量按统一契约处理；用户补齐件数后完成试算或修订 |
| 功能成功 | 任务成功、动作/参数正确、必要与多余澄清、真实执行、调用次数、token、时延 |
| 当前必需项 M0 | 可执行的统一契约；正确输入和模型输出；执行复评时测试 DB 可用 |
| 开发验证 M1 | 60例诊断、原200例决策和140例执行，只约束本轮候选选择 |
| 后置工作 M2 | 完整生产对话接入、后端意图判定改造、规模稳定性、独立test及泛化结论 |
| 下一步最小切片 | 保留v1提示，加入v2契约补充，运行负数/正数及单位对照 |

用户要求以实际产出为主；本轮不安排安全平台、压力测试、通用可靠性重构或多层审核。

## 2. Global Constraints

- 首轮 SFT 只覆盖“补货场景下的工具选择、参数绑定、必要澄清”。
- Python 版本下限沿用项目 `>=3.11`；训练环境与业务应用环境分开锁定依赖。
- 每个 episode 最多一次澄清及一次回复；复杂恢复不进入首轮 SFT。
- 上限不等于精确采购量，0 不等于 null；无包装信息不能把箱当件。
- 现有来源、版本、工具调用协议保持；不伪造用户消息，不在执行器内把模型错误静默改正。
- 本轮单位别名只适用于当前单一SKU、状态单位为“件”、没有用户自定义换算的上下文。不能推广为任意业务中的全局单位转换。
- 不修改 dev-v1、smoke-v1 的原始案例、金标、冻结输入或旧结果。诊断变体只用于开发诊断，不作为独立test，也不进入训练集。
- 不自动提交、合并当前工作区已有变更。本计划仅增加文件；执行时在已有变更基础上做限定编辑。
- Docker Desktop 由用户管理；不自动启动或重启。继续使用既有测试DB及按job ID隔离的执行路径。

## 3. 问题归因及处理决定

| ID | 问题/证据 | 根因状态 | 本轮处理 |
|---|---|---|---|
| S1 | 最低30要求：B1 handoff，金标clarify | 提示没有明确最低量的路由优先级；是否为唯一原因待对照 | 统一下限/精确量/上限语义及路由 |
| S2 | 23 units补充后再次clarify | 单位别名与澄清结束条件未充分传递 | 提示补齐协议；验证多轮上下文确实送达 |
| C1 | -8被输出成+8 | 已确认模型语义错误；频率与系统性未知 | 成对诊断、通用符号规则；不写“-8特判” |
| S3 | B0最后数字、关键词、只读末条消息 | 代码可确认的语义解析缺口 | 保留固定规则基线；记录能力分类，不扩写正则 |
| S4 | B0七次错误修改尝试，四次接受、三次拒绝 | 后端关键词不足以代表修改意图 | 独立后续项；本轮统计现象，不改后端规则 |
| E1 | 参数100%仍有负号错误 | 指标仅覆盖期望工具调用步骤 | 保留原指标，增加针对性语义统计与明确分母 |
| E2 | 缺B2和独立test | 后续实验输入尚未就绪 | 交付B2接入清单；不阻塞当前修复和Data结构准备 |

没有证据表明需要重写生产agent loop。若诊断发现第二条用户回复确实未传入模型，再针对该输入传递缺陷修复runner；不能仅凭输出波动推断状态机有错。

## 4. 固定的 v2 行为契约

本轮沿用原dev的金标方向，补足模型可见表述，不更改原评分答案。

| 输入条件 | 行为 |
|---|---|
| 合法且明确的上限、试算意图 | evaluate_plan，绑定当前Plan |
| 合法且明确的上限、修改意图 | revise_plan，绑定当前Plan和当前版本 |
| 当前有效目标为负数、小数或超范围 | clarify(valid_quantity)，不取绝对值、截断、四舍五入或夹到合法范围 |
| 否定/历史描述里有非法值，但最后有效目标合法明确 | 使用有效目标；不能因为全文出现负号就拒绝 |
| 用户要求最低数量或精确数量 | 首先clarify(quantity_semantics)，说明只支持上限，询问是否愿意改为上限语义；不把原要求自动改成上限 |
| 澄清后用户明确接受上限语义并给足信息 | 按试算/修改意图执行 |
| 澄清后用户坚持最低/精确数量 | handoff；不强制执行，不无休止再问。本轮诊断只测第一步边界，复杂恢复留在后续 |
| 当前单位为件，未定义其他换算，用户说unit/units/件 | 作为同一计数单位，不仅因语言不同再次确认 |
| 箱/包/托盘或用户明确自定义units换算，且换算缺失 | clarify(quantity_unit)，不能擅自视为件 |
| 已收到必要且足够的补充信息 | 结合原请求与回复执行；不重问已知数量、单位或Plan ID |
| 补充信息仍不足或不合法 | 不猜值。本轮两步协议不能完成时如实计未完成，不加自动恢复来抬分 |
| 改售价、发邮件、开放式经营报告等范围外事项 | handoff，不能统一落到“缺数量”澄清 |

## 5. 文件职责

| 文件 | 计划改动/职责 |
|---|---|
| `agent/src/shopsteward_agent/task_policy/policy.py` | 原提示v1、候选v2、提示版本解析、RestrictedPolicy注入 |
| `posttraining/src/shopsteward_pt/eval/policies.py` | 从runtime传递prompt_version，B0保持原样 |
| `posttraining/src/shopsteward_pt/eval/commands.py` | manifest记录实际选用提示及其哈希 |
| `agent/tests/test_task_policy.py` | 提示版本、上下文传递、输出不修补的单元验证 |
| `posttraining/tests/test_commands.py` | 版本对应哈希及续跑版本变化拒绝验证 |
| `posttraining/scripts/build_repair_diagnostics.py` | 构造60个开发诊断episode；复用EpisodeSpec和现有fixture |
| `posttraining/configs/eval_repair_diagnostics_v1.json`、`runtime_repair_diagnostics_v1.json` | 诊断数据、v1/v2并列配置 |
| `posttraining/configs/eval_dev_repair_v2.json`、`runtime_dev_repair_v2.json` | 原dev输入上的v2复评，独立输出目录 |
| `posttraining/datasets/repair-diagnostics-v1.jsonl`、`repair-diagnostics-v1-manifest.json`、`frozen-repair-diagnostics-v1.json`及其manifest | 诊断规格、来源说明、一次冻结输入 |
| `posttraining/scripts/report_repair_eval.py` | 离线读取原始轨迹/评分，生成配对变化、补充指标和分类结果 |
| `posttraining/tests/test_repair_reporting.py` | 用小型固定账本验证补充指标分母 |
| `docs/reports/posttraining/task-contract-v1.md` | 第4节契约的可交接版本，链接原v0，不覆盖原v0 |
| `docs/reports/posttraining/repair-v2/` | 诊断清单、验证、对照报告、selection.json、data-handoff.md |
| `posttraining/README.md` | 实际执行命令、选中的提示版本和新报告入口 |

本轮不改变工具schema、工具描述、PolicyContext结构、数据库模型和原scorer规则，以保证同一冻结输入可直接比较。契约细则放进system prompt和交接规范；工具描述的概括性措辞仍有效。若将来确需改变工具描述，应另设工具版本并重新冻结比较输入，不混入本轮。

## Task R1：实现可比较的契约修复

**Files:** 修改上表中的policy.py、policies.py、commands.py及两个现有测试；创建task-contract-v1.md和两套新config/runtime。

**Interfaces:**
- `prompt_for_version(version: str) -> str`：只接受v1/v2，未知版本抛ValueError。
- `RestrictedPolicy(model, *, prompt_version: str = "v1")`：缺省保持现状；decide签名与返回值不变。
- runtime非B0策略增加`prompt_version`，省略时为v1；`manifest()`记录同一个解析函数返回的文本哈希。

- [x] 保存当前SYSTEM_PROMPT完整文本为v1，禁止为了整洁改写原文本；保留SYSTEM_PROMPT别名指向v1兼容现有导入。
- [x] 先增加版本选择及模型输入传递测试，运行确认新接口缺失时失败。核心测试内容如下，实际加入现有测试文件：

```python
@pytest.mark.asyncio
async def test_selected_prompt_and_completed_reply_reach_model_unchanged():
    from shopsteward_agent.task_policy.contracts import PolicyContext, decision_tool_schemas
    from shopsteward_agent.task_policy.policy import RestrictedPolicy, prompt_for_version

    class Model:
        async def complete(self, messages, tools, tool_choice):
            self.received = (messages, tools, tool_choice)
            return {"tool_calls": [{"type": "function", "function": {
                "name": "revise_plan", "arguments": {
                    "plan_id": "p", "max_purchase_qty": 23, "expected_mission_version": 2
                }
            }}]}

    context = PolicyContext(
        messages=[
            {"role": "user", "content": "Please change the purchase cap."},
            {"role": "assistant", "content": "What quantity cap would you like?"},
            {"role": "user", "content": "Change the current cap to 23 units."},
        ], mission_id="m", plan_id="p", mission_version=2,
        quantity_unit="件", quantity_cap=20, tool_schemas=decision_tool_schemas(),
        context_version="test",
    )
    model = Model()
    result = await RestrictedPolicy(model, prompt_version="v2").decide(context)
    messages, tools, choice = model.received
    assert messages[0]["content"].startswith(prompt_for_version("v2"))
    assert messages[1:] == context.messages
    assert tools == context.tool_schemas and choice == "required"
    assert result.decision.arguments["max_purchase_qty"] == 23
    assert result.raw_response["tool_calls"][0]["function"]["arguments"]["max_purchase_qty"] == 23
```

此测试只证明接线和输入传递，不能证明真实模型懂units；语义效果由R2/R3验证。不要增加大量只断言提示包含某个词的测试。

- [x] 用以下最小实现保留v1，新增v2补充段，并在decide中使用`self.system_prompt`：

```python
SYSTEM_PROMPT_V1 = SYSTEM_PROMPT  # 现有文本原样保留
SYSTEM_PROMPT_V2 = SYSTEM_PROMPT_V1 + """
数量解释与澄清规则：
保留当前有效数量的正负号。负数是非法目标，不能取绝对值、截断或改成0。
区分用户当前目标与被否定、引用或已撤回的数字；原文出现负数不代表合法的新目标也无效。
最低采购量、精确采购量都不能用上限代替：先说明仅支持上限，询问是否接受上限语义。
这类首次请求优先澄清；若用户在澄清后明确坚持不支持的语义，再转交。
当前单位是件、没有其他换算定义时，unit/units就是件的计数别名，不要仅因中英文切换再次确认。
箱、包、托盘或用户另有定义的单位需要已知换算，不能直接当件。
结合原请求与补充回复判断信息是否齐全；齐全后直接试算或修订，不重复询问已明确的数量、单位和Plan ID。
用户没有提供足够信息时不能猜值；只问影响完成当前请求的必要缺项。
"""

def prompt_for_version(version: str) -> str:
    prompts = {"v1": SYSTEM_PROMPT_V1, "v2": SYSTEM_PROMPT_V2}
    if version not in prompts:
        raise ValueError(f"unknown prompt version: {version}")
    return prompts[version]

# RestrictedPolicy.__init__:
# self.system_prompt = prompt_for_version(prompt_version)
# self.model = model
```

- [x] 在make_policy中给RestrictedPolicy传`prompt_version=config.get("prompt_version", "v1")`。不改模型、温度、API模式和输出预算。
- [x] 在manifest中使用实际policy配置选择提示，增加`prompt_version`字段；`prompt_sha256`对选中的文本计算。B0明确标注提示不适用，旧B0结果文件不重写。
- [x] 对`prompt_for_version("v1") != prompt_for_version("v2")`、未知版本ValueError、同一配置下模型实际提示与manifest哈希相等增加测试；复用test_commands已有tmp_path/monkeypatch结构，把第一次运行的prompt_sha256设为v1、续跑设为v2，断言`pytest.raises(ValueError, match="prompt_sha256")`。原有同版本续跑测试继续通过。
- [x] 运行轻量测试。通过后创建新runtime：诊断策略`B1`=v1、`B1_candidate`=v2；全量复评`B1`=v2。所有API设置复制现有runtime并固定同一实际模型/endpoint/API模式；价格未知继续null。
- [x] 诊断配置指向新60例及新frozen路径；复评配置仍指向`dev-v1.jsonl`、原manifest和`frozen-dev-v1.json`，仅runtime与报告输出路径换新。不要对dev执行freeze。

## Task R2：60例诊断，区分契约问题与模型能力问题

**Files:** 创建build_repair_diagnostics.py、诊断数据/config、repair-v2报告目录。

**Interfaces:** 使用现有`EpisodeSpec`、`ExpectedStep`和`freeze/evaluate/rescore`；不新增记录schema。生成函数`build_diagnostics() -> list[EpisodeSpec]`，脚本运行时写JSONL、manifest与按类别ID分组文件`diagnostic-groups.json`。

- [x] 按下表生成确定的60例。数量取7、19、42，意图分别为“仅试算本次上限{表达}，不修改”和“明确将本次上限修改为{表达}”。每条都有明确金标和逐例依据。

| 分类 | 组合及金标 | 数量 |
|---|---|---:|
| 数字符号 | `-{n}件`、`负{中文n}件` → clarify(valid_quantity)；`{n}件` → 对应工具；`{n}件；此前说的负{中文n}件不是本次要求` → 对应工具 | 4表达×3数×2意图=24 |
| 上下限语义 | `最多{n}件` → 对应工具；最低请求“{意图前缀}采购量至少{n}件，我要最低数量，不是上限” → clarify(quantity_semantics)；精确请求“{意图前缀}采购量必须等于{n}件，我要精确量，不是上限” → 同槽clarify | 3语义×3数×2意图=18 |
| 补齐信息 | 第一轮分别“只试算本次采购上限，数量稍后补充”/“请修改本次采购上限，数量稍后补充”；回复分别“仅试算本次上限{n}件，不修改”或“Only evaluate this purchase cap at {n} units; do not change the plan.”，以及修改对应句；先clarify(max_purchase_qty)，再正确工具 | 2单位表达×3数×2意图=12 |
| 未知包装换算 | “仅试算本次上限{n}箱，不修改”/“明确将本次上限修改为{n}箱”，fixture没有每箱件数；clarify(quantity_unit)，不提供第二轮脚本 | 3数×2意图=6 |

其中语义表的意图前缀仅用“请试算本次”/“请修改本次”，不把“上限”强行套进最低量请求。中文数字映射固定为七、十九、四十二。

- [x] 任务分类：单步合法试算PT-01、合法修改PT-02；负数/最低/精确/包装澄清PT-07；两步补齐PT-04。预期计数为PT-01=9、PT-02=9、PT-04=12、PT-07=30，总计60 episode/72 expected decisions。
- [x] 使用standard fixture/version1；所有工具金标带`$current_plan_id`，修改加`$current_mission_version`。试算/修订谓词复用build_dev_v1.py从既有smoke规格取出的谓词；单步澄清用`clarification_relevant/no_business_mutation`；两步加`no_mutation_before_reply`及最终工具谓词。
- [x] 所有记录标split=dev；scenario_family按“分类+意图”分组；manifest明确其由已知失败设计而来，非独立来源。复核后记录agent_reviewed及具体理由，不标human_reviewed。
- [x] 执行现有validate；额外离线断言：`len(rows)==60`、总目标72、ID唯一、任务计数符合上表、两步12例、负数12例。无需为纯文案增加测试套件。
- [x] 为诊断集freeze一次，两个提示共用同一份冻结输入。运行v1/v2 decision；按实际问题复核后resume，禁止无条件注入第二轮答案。
- [x] 输出每类的v1/v2成功数、修复数、退化数及逐例输入/输出。负数12例与合法对照12例分开统计，避免“遇负号就澄清”造成表面提升。
- [x] 只有units仍波动、且轨迹无法定位时，允许最多24次额外决策调用：从原失败decision/execution的第二步step_contexts各取一份，两个提示各重复3次，共12次；若差异集中在先前澄清问题，再交换两份上下文中的assistant澄清句，重复同样12次。UUID、消息、模型参数除指定变量外保持原样。记录为辅助诊断，不计新独立episode。
- [x] 若发现输入缺失，先修复具体传递错误并补回归测试；不在同一run中改代码续跑。否则把剩余错误归入“在契约明确后仍发生的模型能力缺口”。

诊断目标60/60；达到58/60且无整类退化即可继续全量复评，不把少量残余错误变成无限提示优化。若低于58或出现整类退化，本轮候选不晋级全量，交付负结果并进入Data准备；只有明确实施错误才修正后另起run。

## Task R3：原200/140复评与实际收益统计

**Files:** 创建report_repair_eval.py、test_repair_reporting.py；输出repair-v2/comparison.md、comparison.json、selection.json及逐例变更清单。

**Interfaces:** 离线报告输入旧`var/posttraining/runs/dev-v1`、新`var/posttraining/runs/dev-repair-v2`和诊断run；复用现有scores/raw/specs/reviews，不修改原评分器。

- [x] 先用两条固定账本测试补充统计：两条都期望clarify→revise，一条正确完成、一条第二步继续clarify；断言第二步任务完成1/2、重复澄清1/2、每成功任务模型调用4/1；若其中一条因第一步失败没有第二次调用，成功分母仍是两条预期任务。
- [x] 实现`summarize_followups(specs, traces, scores) -> dict`：以有followup_user_message的规格为分母，第二步完成必须动作及完整参数均正确；第二步clarify计重复；缺步计未完成，不从分母删除。
- [x] 补充“合法数量工具决策正确率”“非法数量澄清正确率”“最低/精确语义路由正确率”“件/units补齐完成率”，分类ID来自diagnostic-groups.json；正例需动作和完整参数都对，澄清需rubric通过。
- [x] 实现`compare_runs(old_dir, new_dir) -> dict`按episode_id和mode配对，列出修复/新失败/持续失败，不能仅报净提升。报告同时保留原动作、参数、任务及真实执行指标。
- [x] 全量只重跑v2：原dev200 decision及core140 execution；原v1成绩作为历史比较，诊断中的v1/v2作为当期直接对照。报告明确历史全量对比存在调用时间和执行上下文差异，不声称严格因果证明。B0保持固定，不重跑。
- [x] 逐例复核实际澄清、resume补齐；完成后离线rescore，确认无待复核项。基础设施错误单列并修复受影响任务，不能算语义失败或直接忽略。
- [x] 核对原三个失败：`dev-pt07-011`、`dev-pt07-014`的decision，`dev-pt04-019`的execution；同时复查新增失败，避免只追原案例。
- [x] 输出总模型调用、每成功任务调用、输入/输出token、每成功任务token、decision/task P50/P95。warmup、辅助诊断、失败调用独立列账；价格未配置时金额仍为null。

### 候选采用标准

| 指标 | 原B1 | 本轮标准 |
|---|---:|---|
| dev任务成功 | 198/200 | 不低于198/200，目标200/200 |
| core真实执行成功 | 139/140 | 不低于139/140，目标140/140 |
| 原三条失败 | 三条跨模式失败 | 目标全部修复；仍有失败则标部分修复 |
| 诊断成功 | R2获得当期v1值 | v2≥58/60，目标60/60；不得整类退化 |
| 整体收益 | — | 至少一个任务成功指标提高，或诊断提高且全量任务数不退化；全部相同则不宣称收益 |
| 信息足够后的重复澄清 | 原执行已观察1条 | 目标0；新增重复必须逐例解释 |
| 实际非预期修改 | B1为0 | 保持0，属于当前任务正确性指标 |
| 调用和时延 | 历史decision P95约2.92s、execution task P95约4.83s | 保持一次决策一次调用；P95或每成功任务token增幅>25%时解释代价，不单凭一次时延抖动否决 |

满分是目标，不是Data启动前提。没有明确提升或发生任务退化时保留v1；有收益但未解决全部问题时可以选择v2并标“部分修复”，把剩余错误交给B2/Data。不能把已知负号错误留着却写“已全部修复”。

## Task R4：交接Data与独立后续项

**Files:** repair-v2/selection.json、data-handoff.md；更新posttraining/README.md报告入口。

- [x] selection.json保存chosen_prompt_version、diagnostic/dev/core计数、fixed_ids、regressed_ids、remaining_ids、选择理由和实际配置路径。
- [x] 按“契约缺口已修/模型能力仍弱/证据不足”三种状态汇总，给每项绑定原始episode和实际输出。
- [x] Data交接规范使用第4节契约；新增训练样本来自新的任务来源，不把60例诊断或原dev近义改写作为训练来源。
- [x] 明确优先候选族：带符号数量/否定纠正、上下限与精确量、单位与澄清后执行。相对数量/历史引用是否重点扩写，等待B2，而非照搬B0失败比例。
- [x] B2接入需要实际model/checkpoint、endpoint、API模式、key_file及可选price；配置与已选提示一致，用原dev/core评测。端点不可用只阻塞B2测量与基于B2的配额确定，不阻塞Data schema、来源整理、小批链路样本准备。不在本计划中租GPU或训练。
- [x] 后端S4单列后续工作：保留七条错误修改尝试为回归种子，再加入正确修改/只试算/撤回的对照；先定修改意图与来源绑定接口，再考虑替换关键词。由生产接入需求触发，独立计划和独立验收，不混入本轮提示收益。
- [x] B0仅作为冻结规则基线。如产品明确要部署规则路径，再另开语义解析方案；不为了接近B1分数逐条补关键词。
- [x] 完成后暂停本轮监视；最终报告清楚说明“采用哪个提示、修了哪些、还剩哪些、能否开始Data”，不以测试通过替代模型收益。

## 6. 执行命令与预算

从仓库根目录执行，PowerShell：

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONPATH="$PWD\agent\src;$PWD\posttraining\src"
.venv-pt/Scripts/python.exe -m pytest agent/tests/test_task_policy.py posttraining/tests -q

$env:PYTHONPATH="$PWD\backend;$PWD\agent\src;$PWD\posttraining\src;$PWD\knowledge\src;$PWD\simulation"
.venv/Scripts/python.exe posttraining/scripts/build_repair_diagnostics.py
.venv-pt/Scripts/python.exe -m shopsteward_pt.cli validate --config posttraining/configs/eval_repair_diagnostics_v1.json
.venv/Scripts/python.exe -m shopsteward_pt.cli freeze --config posttraining/configs/eval_repair_diagnostics_v1.json
.venv/Scripts/python.exe -m shopsteward_pt.cli evaluate --config posttraining/configs/eval_repair_diagnostics_v1.json --run-dir var/posttraining/runs/repair-diagnostics-v1 --policies B1 B1_candidate --mode decision
```

复核每个实际问题、写入该policy自己的reviews.jsonl后，原evaluate命令增加`--resume`；复用现有review字段和rubric，不自动照抄另一提示的审核结论。

```powershell
.venv/Scripts/python.exe -m shopsteward_pt.cli evaluate --config posttraining/configs/eval_dev_repair_v2.json --run-dir var/posttraining/runs/dev-repair-v2 --policies B1 --mode decision
.venv/Scripts/python.exe -m shopsteward_pt.cli evaluate --config posttraining/configs/eval_dev_repair_v2.json --run-dir var/posttraining/runs/dev-repair-v2 --policies B1 --mode execution --suite core
.venv-pt/Scripts/python.exe -m shopsteward_pt.cli rescore --run-dir var/posttraining/runs/dev-repair-v2/decision/B1
.venv-pt/Scripts/python.exe -m shopsteward_pt.cli rescore --run-dir var/posttraining/runs/dev-repair-v2/execution/B1
.venv-pt/Scripts/python.exe posttraining/scripts/report_repair_eval.py --baseline var/posttraining/runs/dev-v1 --candidate var/posttraining/runs/dev-repair-v2 --diagnostics var/posttraining/runs/repair-diagnostics-v1 --output docs/reports/posttraining/repair-v2
```

以上报告脚本参数在R3实现；不是当前已存在的命令。每个evaluate完成首轮后都需按实际pending列表复核并resume再出最终报告。若诊断未晋级，报告脚本允许candidate目录不存在，输出“未执行全量”和候选不晋级理由，不能伪造全量成绩。

静态检查仅限本轮改动Python文件。未改后端时不额外重跑其他会清空队列的集成测试；core140真实执行是本轮业务验证。若实际修改runner，再补针对输入传递的回归测试和相关已有runner测试。

**模型调用预算：** 诊断两提示最多144正式决策；全量候选最多400；各诊断策略3次warmup和全量3次warmup，共9次，预计最多553次。条件诊断最多24次，合计577次。整轮硬上限600次，余量用于少量失败重试；到达上限停止新增调用，交付已有结果与剩余项，不自动加预算。账本包含失败尝试，不只统计返回usage的请求。v1/v2都不新增自动retry；resume仅补协议允许的未完成步骤。

**时间估算：** 实施与报告约半天至一天；模型和真实执行通常几十分钟，受API和复核影响，不作完成时间承诺。最多一轮候选契约修正加一次全量复评；不反复对dev调到100%。

**后台执行：** 执行获授权后，批量调用使用隐藏后台进程、独立日志和阶段状态；现有run_smoke_background.py写死了B0/B1组合，不直接用于两提示诊断。可用隐藏PowerShell进程执行上面的明确CLI调用并重定向输出，无需扩建调度器。任务启动后更新已有`shopsteward-eval`监视为15分钟，指向新run；状态不变静默，出现错误、可明确修正的问题、复核待办或完成时介入。调用中途不更换提示或金标。计划编写阶段不启动任务、不恢复监视。

## 7. 计划自检与交付清单

- [x] 三个B1失败、B0缺陷、后端缺陷与指标缺口均有处理或明确后续归属。
- [x] 保留原金标与原结果，区分开发诊断、历史比较和当期提示对照。
- [x] 任务参数、文件位置、诊断数量和72步分母与现有EpisodeSpec兼容。
- [x] 正负对照与未知包装案例防止“全部澄清”制造表面收益。
- [x] prompt_version同时用于真实调用和manifest，避免实验版本记错。
- [x] 不以B2或独立test缺失阻塞当前可用产出；没有虚构微调收益。
- [x] 执行产物：v2代码/配置、60例诊断对照、200/140复评或明确未晋级结果、候选选择、Data交接。

2026-09-15执行更新：R1完成并通过测试；R2的60例规格和真实冻结输入已准备；R3报告代码已准备。模型成绩以新run实际结果为准。

2026-09-15 02:03 UTC：R2完成，v1 59/60、v2 60/60，零退化；条件units额外实验无需执行。全量复评启动，累计调用150/600。

2026-09-15最终交付：v2诊断60/60、决策199/200、核心执行140/140；553/600调用；选择v2并保留ID抄写/包装措辞剩余问题。条件units实验与runner缺失修复未触发，相关勾选表示条件已检查，无额外执行。B2、B0重写和后端修改按计划后置。报告：../../reports/posttraining/repair-v2/data-handoff.md。
