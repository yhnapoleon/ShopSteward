# Data 准备与 B2 基线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 本计划不要求子代理；并行指无依赖的工作可以交错推进。

**Goal:** 交付首批目标200个可训练episode及目标模型B2的训练前基线，依据实测缺口制定首轮1,000条数据配额与SFT短跑入口。

**Architecture:** Data复用现有EpisodeSpec、PolicyContext、Decision、真实fixture和scorer，新增来源记录、验证与单目标训练投影。B2复用v2提示和原dev200/core140，仅增加独立模型配置及必要服务兼容适配。两条线在错误分类、tokenizer模板检查和数据配额处汇合。

**Tech Stack:** Python >=3.11、Pydantic、pytest、现有真实工具与PostgreSQL fixture。B2服务/训练依赖在独立环境；模型候选沿用原方案Qwen/Qwen3-8B，先验证非thinking模式，不预设其优于其他模型。

**Spec:** [阶段设计](../specs/2026-09-14-phase2-task-model-data-eval-design.md)、[原总计划](2026-09-14-phase2-sft-data-eval-plan.md)、[修复交接](../../reports/posttraining/repair-v2/data-handoff.md)、[当前契约](../../reports/posttraining/task-contract-v1.md)。

**状态：** 规划完成、待执行。硬件/模型服务尚未确认；未启动下载、租赁、生成或训练。本计划不承诺SFT必然有收益。

## 1. 可用结果与范围

| 项目 | 定义 |
|---|---|
| 可用产物 | 200个通过验证的训练episode、训练投影和质量报告；一份B2决策/执行基线与错误分布 |
| 功能指标 | 有效episode及目标数、候选接受率、真实执行通过数、正确loss mask；B2任务成功、动作/参数、调用/token/时延 |
| 当前阻塞M0 | B2实际服务和协议可用；训练投影有正确目标；真实验证阶段DB可用 |
| 开发验证M1 | 原dev/core基线、数据逐类复核、tokenizer模板验证；只约束其对应结果，不阻塞无关Data准备 |
| 后置M2 | 生产部署、压力/稳定性体系、独立test300完整验收、多规模模型横评 |
| 下一步 | 登记模型环境，同时制作20个新来源种子，跑通数据收集→验证→导出的最小切片 |

本轮以数据和模型的实际可用产出为主，不建设复杂治理平台。B2是“未进行本项目SFT”的模型，可以本来就是官方指令模型；不把它误称为纯预训练权重。

## 2. Global Constraints

- 首轮 SFT 只覆盖“补货场景下的工具选择、参数绑定、必要澄清”。
- Python 版本下限沿用项目 `>=3.11`；训练环境与业务应用环境分开锁定依赖。
- 每个 episode 最多一次澄清及一次回复；补充用户消息完整表达修改意图与数量，沿用当前后端来源约束。
- 提示v2、五个动作、工具schema和原dev金标保持一致；不新增自动纠错或兜底后把结果计为模型独立成功。
- 原dev200、诊断60及其改写不进入train。语义类型可以重合，具体来源、模板改写与失败修复不能跨分区。
- 合成样本明确标为合成；source_id是来源记录，不是改名即可获得“独立真实来源”的证明。
- 模型、tokenizer、模板、精度/量化和解码配置为base/SFT比较固定变量。
- Docker仍由用户启动；不自动租GPU、购买服务或开始训练。需要付费资源时先完成资源方案与预算，再确认实际开通。
- 计划执行不自动提交或覆盖已有实验；长任务按用户偏好后台运行、每15分钟监视、无变化静默。

## 3. 阶段与依赖

| 任务 | 依赖 | 交付 |
|---|---|---|
| D1 数据记录和20例最小切片 | 现有契约 | 能验证、能导出的真实样本 |
| B1 模型环境与协议接入 | 实际服务/硬件信息 | 模型登记、10例兼容报告 |
| D2 新来源200例 | D1；不依赖B2成绩 | 有效episode、失败原因、通用训练投影 |
| B2 完整训练前基线 | B1 | 原200决策/140执行及逐类错误 |
| D3 目标模板和配额 | D2；tokenizer；配额依赖B2 | token/mask报告、数据发布、1k配额与SFT交接 |

没有B2端点时继续D1/D2；缺tokenizer时交付规范化投影并标“尚未通过目标模板验证”，不宣称可直接训练。

## 4. 文件与接口

新增研究侧文件：

- `posttraining/src/shopsteward_pt/data/records.py`：SourceRecord、TrainingEpisode、TrainingExample。
- `posttraining/src/shopsteward_pt/data/collect.py`：从新规格生成上下文/候选目标和轨迹。
- `posttraining/src/shopsteward_pt/data/verify.py`：复用契约/scorer/真实fixture验证，输出接受与拒绝记录。
- `posttraining/src/shopsteward_pt/data/export.py`：每个正确assistant目标一条训练样本；历史只作输入。
- `posttraining/src/shopsteward_pt/data/cli.py`：独立data命令，避免改变当前eval validate的含义。
- `posttraining/src/shopsteward_pt/serving/verify.py`：B2连接、工具协议及10例短测。
- `posttraining/tests/test_data_contract.py`、`test_training_projection.py`、`test_data_verification.py`、`test_b2_config.py`。
- `posttraining/configs/data_pilot_v1.json`、`eval_b2_v1.json`、`runtime_b2_v1.json`。
- `posttraining/datasets/sources-v1.jsonl`、`train-pilot-v1/`：来源、episode、targets、rejected、manifest。
- `docs/reports/posttraining/data-pilot-v1/`、`b2-v1/`：数据质量、服务兼容、错误分布和后续配额。

必要时修改`eval/policies.py`以传递显式B2服务参数，修改`eval/commands.py`以登记model/tokenizer revision、chat template hash、精度、thinking和解码配置。通用生产Agent不在本轮改造范围。

接口约定：

```python
def validate_sources(sources: list[SourceRecord]) -> None: ...
async def collect_episode(spec: EpisodeSpec, source: SourceRecord, runtime: dict) -> TrainingEpisode: ...
async def verify_episode(episode: TrainingEpisode, runtime: dict) -> dict: ...
def project_episode(episode: TrainingEpisode) -> list[TrainingExample]: ...
def render_example(example: TrainingExample, tokenizer) -> dict: ...
```

`SourceRecord`字段：source_id、origin_kind（authored_synthetic/replayable_fixture）、origin_ref、brief、split（train/test）、parent_source_id。
`TrainingEpisode`字段：episode_id、source_id、spec（EpisodeSpec）、step_contexts（PolicyContext列表）、targets（Decision列表）、verification（状态/各谓词/问题复核/真实回执路径）。
`TrainingExample`字段：example_id、episode_id、source_id、prompt_messages、tools、completion（一个assistant tool_call）、prompt_version、tool_schema_hash。业务回执、gold与复核理由保留在标准记录，不能加入prompt_messages。

## Task D1：最小数据链路

- [ ] 编写20个新来源种子，覆盖五动作、0/null、负数、单位、历史、两轮澄清；从业务需求和新的fixture事件出发，不读取dev句子做改写。origin_ref指向实际种子文件及条目。
- [ ] 先写契约/投影反例测试，再实现上述Pydantic记录：目标数与上下文数一致，最大2步，只有首步clarify可进入第二步，拒绝缺Plan/版本、参数类型错误和未通过验证的导出。
- [ ] 最小投影测试必须覆盖以下语义，而不只测试字段名称：

```python
def test_second_target_keeps_history_but_supervises_only_final_decision(valid_two_turn_episode):
    examples = project_episode(valid_two_turn_episode)
    assert len(examples) == 2
    assert examples[1].prompt_messages[-1]["role"] == "user"
    assert examples[1].completion["tool_calls"][0]["function"]["name"] == "revise_plan"
    assert len(examples[1].completion["tool_calls"]) == 1
    assert examples[0].source_id == examples[1].source_id
```

测试fixture用当前契约构造clarify→revise、明确完整用户回复及真实可见ID；故意把参数数量或Plan ID改错时verify必须拒绝，不能由投影器纠正。

- [ ] 动作金标先由独立任务规格给出；teacher只看到PolicyContext和schema，输出候选，不能看到expected_steps。teacher候选必须经语义/参数与真实工具验证后才能作为正例。
- [ ] 澄清题逐条检查问到必要槽位、不猜数量、不索取已知ID；包装问题不保留“工具可直接改为箱/袋”的误导选项。训练质量标准可比旧eval更严格，但不得追溯修改eval分数。
- [ ] 复用真实fixture执行每个拟接收工具目标；控制动作检查记录与状态。失败输出写rejected，原因区分模型、标签、工具协议、环境；环境错误修环境后重放，不作为训练负标签。
- [ ] 导出20例，打印源episode数、目标数、双轮数、接受/拒绝原因、示例消息。数据链路通过后再扩至200。

## Task B1：B2环境与协议

- [ ] 先登记已有服务地址或GPU/显存/OS、模型文件、可用存储；优先使用已存在资源。候选沿用Qwen/Qwen3-8B，不做广泛选型；固定实际revision后才生成可运行配置。
- [ ] 若没有可用资源，输出`b2-v1/environment-options.md`，列一个可实施部署方案、实例单价来源、下载/启动开销、预计基线时长及最高金额。未确认资源前不伪造endpoint或租赁；Data照常推进。
- [ ] runtime的B2必须显式指定model、base_url、api_mode、key_file、prompt_version=v2；禁止缺字段时回落到B1的模型或密钥。无鉴权本地服务也使用独立客户端配置，不复用远端API凭证。
- [ ] 新增配置反例测试：缺model/base_url失败、B2参数实际送达客户端、B1原有默认不变。注册信息至少记录model/tokenizer revision、服务版本、模板hash、dtype/quantization、上下文长度和实际解码配置。
- [ ] 初始使用非thinking模式、并发1、单调用tool_choice=required、输出预算1024、超时60秒、无自动修复；若服务不支持required，先判断适配问题，不静默换auto。必须改协议时显式升版本，并使将来base/SFT使用相同设置。
- [ ] 10个兼容请求覆盖五动作，以及中文/英文、多轮、0/null、边界整数。检查结构化调用解析、参数类型、实际prompt和token统计；语义答错如实记录，不要求基线高分才允许评测。
- [ ] 对Qwen模板使用实际支持的非thinking开关；通过服务请求和tokenizer渲染核对生效，不仅在提示里写“不思考”。不承诺未经实测的GPU显存配置可容纳模型。

官方依据：[Qwen3-8B模型卡](https://huggingface.co/Qwen/Qwen3-8B)说明非thinking开关；[vLLM工具调用文档](https://docs.vllm.ai/en/latest/features/tool_calling/)用于核对所安装版本的模型/parser/template组合。具体服务命令在环境确认后固定，不把滚动文档当项目锁定版本。

## Task D2：200个episode的小批数据

- [ ] 新建至少50个train来源种子，每来源至多4个有效episode；种子含具体业务条件、意图和参数依据，不能只是复制句子换source_id。
- [ ] 另保留至少10个新来源brief到test来源池，不扩写、不用于训练；这只是后续独立test准备，不等于已建立300例test。来源池可全为明确标注的合成来源，不要求先收集真实店铺数据。
- [ ] 首批目标分布如下。D1的20例计入200，不额外叠加。分布用于链路覆盖，不代表真实请求频率，B2回来后再定1k配额。

| 类别 | episode | 最少train种子 |
|---|---:|---:|
| PT-01 正常试算 | 32 | 8 |
| PT-02 正常修改 | 32 | 8 |
| PT-03 否定/纠正意图 | 24 | 6 |
| PT-04 澄清后执行 | 40 | 10 |
| PT-05 历史引用 | 20 | 5 |
| PT-06 撤回 | 8 | 2 |
| PT-07 数量与语义边界 | 16 | 4 |
| PT-08 范围外 | 12 | 3 |
| PT-09 包装换算未知 | 8 | 2 |
| PT-10 取消上限 | 8 | 2 |
| 合计 | 200 | 50 |

- [ ] 正负数量、0/null、最终有效意图/被否定数字、当前/历史Plan和版本等变化跨类别分布；不做维度笛卡尔积。40个双轮episode对应总目标约240条，单独报告，不能写成240个独立任务。
- [ ] 按20→100→200有效episode扩量，最多300候选episode；拒绝样本保留原因和来源。一个批次出现相同误标时先改生成规则，再继续，不把“删除错例”当修复。
- [ ] 所有接收工具目标实际验证；所有接收澄清目标逐例语义复核，标agent_reviewed。首批不要求双人审核或另建评审平台。
- [ ] 最小来源检查：source/parent_source分区一致；同episode拆分目标同分区；规范化完全重复剔除，近似文本仅列候选供复查。不得把通常的语义类型重合错误地判为泄漏。
- [ ] 输出接受率、拒绝原因、任务/来源分布、真实执行验证通过数。候选300仍不足200有效时交付实际数量和缺口，不无限生成；至少100有效可支持后续小规模链路短跑，仍明确200目标未完成。

## Task B2：训练前全量基线

- [ ] 使用`eval_b2_v1.json`指向原dev-v1及frozen-dev-v1；只替换runtime为实际B2。无需重新冻结，不重跑B0/B1。
- [ ] 运行200 decision/140 core execution，按现有实际问题复核与resume规则完成第二步；环境错误与语义失败分开。
- [ ] 输出动作、完整参数、任务成功、必要/多余澄清、第二步完成、范围外路由、错误写入尝试、调用/token、P50/P95。金额已知才算，实例按实际时长与单价计费；API费为0不等于GPU成本为0。
- [ ] 每类列明分子分母和代表失败，区分动作、数值理解、ID复制、版本绑定、历史、单位、服务解析和后端拒绝。不能把B1已知失败的变体作为唯一测量。
- [ ] 对照B1 v2仅作能力参考；真正的SFT收益以后与这份B2同模型基线比较。温度/精度/模板变化另编号，不覆盖原run。

## Task D3：目标模板、发布与SFT交接

- [ ] 使用已锁定tokenizer渲染每条TrainingExample，输入与服务端messages/tools模板对应。每条只监督最后一个正确assistant决策，历史assistant、用户、工具回执均不算loss。
- [ ] 检查普通试算、修订、澄清、转交、撤回、null及两轮样本的真实token与mask：目标token非空，前文mask全为0，JSON参数round-trip后类型和值一致。不得仅设assistant_only_loss便假设历史assistant都不计loss。
- [ ] 初始序列上限4096；报告P50/P95/max与超限数。超限样本先排除并说明，不能截掉目标或关键历史；若超限成为常态，统一调整服务/训练长度再发布。
- [ ] 导出规范化targets.jsonl和目标模板投影，manifest记源episode/目标/来源数、已验证数、hash、prompt/tool/template版本。数据版本不原地覆盖。
- [ ] 根据B2错误分布制定1k配额：保留至少50%常规与已有正确能力样本；剩余部分优先覆盖反复出现的语义错误。每种重点错误必须给出B2证据，不根据B0失败比例机械分配。
- [ ] 完成`data-b2-handoff.md`：是否具备100–300条SFT短跑条件、仍缺哪些环境、下一轮具体训练量和预算估算。此计划止于准备，不启动LoRA训练。

如果B2已经接近任务上限，可选择先做成本/部署验证，并记录“未证明需要SFT”；如果格式不兼容，先修服务适配，不用更多训练样本掩盖接口错误；如果语义差距大且数据可学，再进入短跑。

模板/mask实现以[TRL SFT文档](https://huggingface.co/docs/trl/sft_trainer)为参考，需核对安装版本和实际token结果；本阶段不向业务环境安装训练库。

## 5. 命令与预算

以下data/serving命令是本计划要实现的接口，当前尚不存在；现有eval命令可直接复用。配置由B1阶段的实际环境登记生成，不能用未填写的示例地址执行。

```powershell
$env:PYTHONPATH="$PWD\backend;$PWD\agent\src;$PWD\posttraining\src;$PWD\knowledge\src;$PWD\simulation"
.venv/Scripts/python.exe -m shopsteward_pt.data.cli collect --config posttraining/configs/data_pilot_v1.json --limit 20
.venv/Scripts/python.exe -m shopsteward_pt.data.cli verify --config posttraining/configs/data_pilot_v1.json
.venv-pt/Scripts/python.exe -m shopsteward_pt.data.cli export --config posttraining/configs/data_pilot_v1.json
.venv/Scripts/python.exe -m shopsteward_pt.serving.verify --config posttraining/configs/runtime_b2_v1.json
.venv/Scripts/python.exe -m shopsteward_pt.cli evaluate --config posttraining/configs/eval_b2_v1.json --run-dir var/posttraining/runs/b2-v1 --policies B2 --mode decision
.venv/Scripts/python.exe -m shopsteward_pt.cli evaluate --config posttraining/configs/eval_b2_v1.json --run-dir var/posttraining/runs/b2-v1 --policies B2 --mode execution --suite core
```

tokenizer渲染在独立模型环境执行`data.cli render --config ...`；纯导出不依赖GPU。具体环境锁文件由实际安装结果生成。

- B2最多450次模型请求：兼容10、正式最多400、warmup3，留少量排障空间；不做自动多次重复采样。
- Data最多300候选episode、每例最多两次teacher决策，teacher调用上限600；不额外调用模型做批量改写，以新作者种子与受控变体构建输入。修复拒绝样本也计入预算。
- 这两个上限是新的规划预算，不沿用已完成修复轮次的600账本；费用需依据实际价格/资源确认。预算耗尽交付现有产物，不自动扩量。
- 暂估2–4个有效工作日，外部服务准备时间另计；以D1/B1/D2/B2/D3产物验收，不把日程当效果承诺。
- 只有执行批量任务时才恢复已有监视，避免计划阶段空转。未确认硬件不阻塞D1/D2。

## 6. 完成标准

- [ ] 目标200个有效episode（不足时准确报告）、约240目标、至少50个train来源与10个保留来源brief；无虚构独立性。
- [ ] 模型接口与实际tokenizer模板可复现；导出目标mask检查通过，训练前基础模型已登记。
- [ ] B2的200/140完整基线或明确环境阻塞原因；有真实错误分类与后续配额。
- [ ] 数据质量、有效样本成本/时延、base指标均有报告，能够开始小规模SFT或明确说明不需要/尚不能训练。
- [ ] 不将本阶段产物包装成已经完成的微调收益、真实店铺经营收益或生产部署。
