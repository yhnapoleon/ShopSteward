# 会话交接：协作策略、评测底座与提示词演化

**2026-10-08 下午有后续：先读[多供应商寻源交接](2026-10-08-sourcing-handover.md)。** 工作方向已转到新场景，本文第 9 节的下一步已被取代；本文其余内容（已做的决定、环境、测试数据库的用法、踩过的坑）仍然有效。

写于 2026-10-08（Asia/Shanghai）。读者是接手这条工作线的下一个对话，以及项目负责人。本文只覆盖 2026-10-07 至 10-08 这两天的工作；整个项目的总交接仍是仓库根目录的 [HANDOVER.md](../../HANDOVER.md)，本文没有改动它。

## 1. 现状一句话

Case 专家的四种协作策略、离线评测底座和一次 GEPA 提示词演化都已实现，并用 DeepSeek 跑出了真实结果；所有代码都在工作区里，没有提交；有两个默认值是否修改在等项目负责人决定。

## 2. 项目负责人已经做的决定

接手后按这些执行，不需要再问：

- **工作顺序**：先完成“Multiagent × Context Engineering × Rubric”这条线，再系统性引入自进化。后续拓展按[技术选型与自进化设计](../superpowers/specs/2026-10-08-technology-selection-and-evolution-design.md)的 X1 到 X5 阶段走。
- **交付标准是概念验证**：目标是在理想条件下跑通一次完整演示，不追求上线级的稳定性。发布门槛和其他门槛可以放宽。放宽的是门槛，不是如实报告：没测的不能写成测了。
- **真实模型用 DeepSeek**：密钥在本机的 `ds.txt`，它在仓库之外，本机路径不写进仓库。直接把这个路径当密钥文件传入，不要复制进仓库，不要打印。暂不设额度上限，但要先小批量再放大，不要一上来跑全量。
- **优化用分数**按设计文档第 5.4 节的定义。
- **Skill 准入门槛可以分两档**（设计文档第 7.6 节的选项乙）。这一条已获同意，但代码还没改，见第 7 节。
- **没有要求提交代码**。不要自行提交、重置或清理工作区。

课程最终交付截止是 2026-10-25 23:59，提交前需在 Canvas 复核。

## 3. 等项目负责人决定的事

这四件事上次对话结束时还没有答复：

1. **默认策略是否从按需专家换掉。** 实测里一次调用的固定流程最好也最便宜。按设计里预先写下的规则应当换成固定流程或单 Agent，但这会影响“多智能体”的展示叙事。目前 `AGENT_CASE_STRATEGY` 的默认值仍是 `adaptive_multi`。
2. **是否启用演化后的提示词 `gepa-r1`。** 目前 `AGENT_CASE_TEXT_BUNDLE` 的默认值仍是 `seed`。
3. **下一步先做哪个**：重复运行加第二个随机种子、给用例加入文档类证据、还是开始 X3 的基线 Skill。上次的建议是先做第一个。
4. **是否分批提交。** 工作区积压了 9 月 12 日以来的全部改动。

## 4. 这两天做了什么

按时间顺序：

1. **读设计稿并梳理状态。** 确认两条设计线各自的实现程度。
2. **协作策略层。** 新增固定流程（R0）、单 Agent（R1）、固定三专家（R2）、按需专家加一次定向补查（R3）四种可切换的策略，代码合并专家结果，按角色冻结模型，并能把一次运行导出为评分记录。
3. **技术调研与选型。** 写了设计文档：引入 GEPA、MAST 失败标签、Agent Skills 格式；CP-SAT 有条件引入；其余暂缓或不引入。
4. **X1 评测底座。** 提示词做成带版本和哈希的文本制品；生成 60 个合成用例；说法核对器、批量运行器、MAST 自动标签、配对门槛报告。
5. **X2 GEPA 试点。** 第一次搜索因接线问题白跑，修正后第二次成功，产出文本制品 `gepa-r1`。
6. **真实运行。** 约 2,300 次模型调用，结果写进了[评测与演化报告](2026-10-08-strategy-evaluation.md)。

关键结果（gate 划分，24 个优化器没见过的合成用例，`deepseek-flash`，每个配置跑一次）：

| 策略 | 初始提示词 | 演化后 | 平均模型调用 |
|---|---|---|---|
| R0 固定流程 | 23/24 | 24/24 | 1.0 |
| R1 单 Agent | 21/24 | 24/24 | 2.0 |
| R2 固定三专家 | 21/24 | 22/24 | 6.3 降到 6.0 |
| R3 按需专家 | 18/24 | 22/24 | 7.8 降到 7.0 |

按需专家的主要失败是向用户提出不必要的澄清，初始提示词下 6 次，演化后 2 次。

## 5. 代码在哪里

分支 `YH`，HEAD 仍是 `30bed9f`，与远端一致。工作区有 52 个已修改的跟踪文件和 100 个未跟踪条目，其中包含更早的未提交工作。下表只列这两天新增或改动的部分。

| 内容 | 位置 |
|---|---|
| 四种策略、路由、代码合并 | `agent/src/shopsteward_agent/cases/strategy.py` |
| 专家运行器（角色工具、输出约定、回复解析、补查） | `agent/src/shopsteward_agent/cases/runner.py` |
| 文本制品的加载与保存 | `agent/src/shopsteward_agent/cases/bundle.py` |
| 文本制品文件 | `agent/src/shopsteward_agent/cases/bundles/case-experts/seed.json`、`gepa-r1.json` |
| 冻结证据工具、路由信号、一次策略运行的入口 | `agent/src/shopsteward_agent/cases/frozen.py` |
| 后端入口（模型配置、持久化、权限复核） | `backend/app/agent_bridge/context_cases.py` |
| 新增配置项 | `backend/app/core/config.py`：`agent_case_strategy`、`agent_case_role_models`、`agent_case_text_bundle` |
| 评分轨迹导出 | `posttraining/src/shopsteward_pt/case_eval/strategy_trace.py` |
| 评测包：用例、核对器、运行器、MAST、GEPA 适配、命令行 | `posttraining/src/shopsteward_pt/strategy_eval/` |
| 合成用例集 | `posttraining/datasets/ops-synthetic-v1/` |
| 专家面板显示策略、补查和未采信的分歧 | `frontend/app/components/RecoveryWorkspace.vue` |
| 测试 | `agent/tests/test_case_strategy.py`、`test_case_bundle.py`；`backend/tests/unit/test_case_experts.py`、`backend/tests/integration/test_case_expert_context.py`；`posttraining/tests/strategy_eval/`、`posttraining/tests/case_eval/test_strategy_trace.py` |
| 原始运行结果 | `docs/reports/strategy-eval/`，约 13 MB |

## 6. 怎么运行

### 环境

| 环境 | 用途 |
|---|---|
| `.venv` | Agent、后端、评测批量运行和出报告 |
| `.venv-pt` | 评测包里只依赖 Pydantic 的测试；没有 LangGraph |
| `.venv-evo` | GEPA 搜索；已被 `.gitignore` 忽略，重建方法见[评测运行说明](../runbooks/strategy-evaluation.md) |

### 测试

以下命令从仓库根目录 `ShopSteward/` 运行。

```powershell
# Agent，不需要数据库
cd agent; ..\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider --basetemp=../var/strategy-tests/agent; cd ..

# 评测包：三个环境各跑一遍，缺依赖的测试会自动跳过
.venv-pt\Scripts\python.exe  -m pytest -c posttraining/pyproject.toml posttraining/tests -q -p no:cacheprovider --basetemp=var/strategy-tests/pt
.venv\Scripts\python.exe     -m pytest -c posttraining/pyproject.toml posttraining/tests/strategy_eval posttraining/tests/case_eval/test_strategy_trace.py -q -p no:cacheprovider --basetemp=var/strategy-tests/pt-main
.venv-evo\Scripts\python.exe -m pytest -c posttraining/pyproject.toml posttraining/tests/strategy_eval -q -p no:cacheprovider --basetemp=var/strategy-tests/pt-evo
```

后端集成测试需要先启动隔离的测试数据库，它平时不运行：

```powershell
$pg = (Resolve-Path "var\next-phase-postgres").Path
Start-Process -FilePath "$pg\pgsql\bin\pg_ctl.exe" -ArgumentList @('-D', "`"$pg\data`"", '-l', "`"$pg\server.log`"", '-o', '"-p 55434 -c listen_addresses=127.0.0.1"', 'start') -WindowStyle Hidden
# 等端口 55434 监听后再跑；数据库测试必须串行
.venv\Scripts\python.exe var\next-phase-tests\run.py backend -m pytest tests -q -p no:cacheprovider --basetemp=../var/strategy-tests/backend --tb=short
& "$pg\pgsql\bin\pg_ctl.exe" -D "$pg\data" -m fast -w stop | Out-Null
```

最近一次全部通过的结果（2026-10-08）：Agent 145 项（含数据库）；后端全量 651 通过、3 跳过；评测包三个环境分别是 83 通过 3 跳过、18 通过 1 跳过、13 通过；相关文件的 Ruff 检查和格式检查通过。

### 评测与演化

命令和参数说明在[评测运行说明](../runbooks/strategy-evaluation.md)。最常用的一条，在 `posttraining/` 目录下、设好 `$env:PYTHONPATH = "src"` 之后运行：

```powershell
..\.venv\Scripts\python.exe -m shopsteward_pt.strategy_eval run --cases datasets/ops-synthetic-v1 --out ../docs/reports/strategy-eval/2026-10-08-gate --partition gate --bundle seed --model deepseek-flash --key-file <DeepSeek 密钥文件> --parallel 4 --max-model-calls 900
```

同一个 `--out` 目录里已完成的运行会被跳过，所以可以分批追加。

## 7. 还没做、还没验证的

- **Skill 准入门槛的两档方案没有实现。** 已获同意，但 `backend/app/learning/quality.py` 没有改。按现有门槛，20 个配对用例、零退化时仍需至少 6 例净改善才能通过，没有 Skill 能被启用。
- **前端浏览器测试没有重跑。** 改了专家面板之后只跑了类型检查和接口契约检查。
- **日常数据库没有迁移。** 迁移 0015、0016 只在隔离测试库上验证过。
- **结果是演示级的。** 用例是合成的，没有锁定测试集；每个配置只跑一次；GEPA 只跑了一个随机种子；自由文字的说法没有人工复核。同一份初始提示词在两次搜索开始时的验证集得分分别是 5/12 和 8/12，单次波动很大。
- **演化后的提示词对两种多专家策略没有通过演示级门槛**，各有 2 个用例由成转败，无法区分是退化还是波动。
- **GEPA 搜索的 token 用量没有逐次记录**，报告里是估算。没有价格表，没有算金额。
- **现在的用例只有结构化证据**，本来就偏向单次调用。需要跨文档判断适用性的场景还没测。
- **设计文档的 X3 到 X5 都没有开始**：基线 Skill 与 Mission 沙箱运行器、多 SKU 与 CP-SAT、流程 DSL 与 A2UI。
- **统一设计 v1.2 里更早列出的缺口仍在**：自由文本事项到 Case 的自动路由、PDF 供应通知接入、通用语义压缩、LLM 协调器。

## 8. 踩过的坑

- **启动测试数据库时不要用管道接 `pg_ctl start` 的输出**，否则命令会挂到超时。用上面的 `Start-Process` 写法，然后查端口。用完记得停。
- **不要同时跑 GEPA 搜索和批量运行。** 上次并发时本机出现 DNS 解析失败。现在连接错误会重试；模型服务报错的运行不会记为策略失败，而是留到下次重跑；GEPA 在服务持续不可用时会中止。
- **GEPA 中止后**，用同一个 `--run-dir` 重新执行会续跑；要重新开始一次搜索，必须换一个新的 `--run-dir`，否则会接着旧状态跑。
- **不要用 GEPA 默认的反思模板。** 它会写出几千字符、还重新定义输出格式的指令。现在用的是 `strategy_eval/evolve.py` 里的 `REFLECTION_TEMPLATE`，单个组件上限 1,500 字符。
- **文本制品的版本不可覆盖。** `gepa-r1` 已存在，新的搜索要换版本名。
- **汇总表里的“Mean score”不是质量成绩**，是给优化器排序用的，有任何子任务失败就是 0。对外报告用成功计数。
- **真实模型的回复不一定是纯 JSON。** 运行器现在接受包在代码块里或带一句说明的 JSON 对象。
- **“推荐”和“可行”不算专家分歧。** 合并逻辑里只有它们与“被拒绝”才构成需要裁决的冲突。改词表时要同步改 `strategy.py` 里的 `SAME_STANCE`。
- **`.venv-pt` 里没有 LangGraph**，需要真实运行器的测试在那里会被跳过，要在 `.venv` 或 `.venv-evo` 里跑才算数。
- **评测命令行要在 `posttraining/` 目录运行并设置 `PYTHONPATH=src`**；它会自己把 `agent/src` 和 `backend` 加进导入路径。

## 9. 建议的下一步

如果项目负责人没有别的指示，按这个顺序做。前两步合计约 1,500 到 2,000 次模型调用。

1. **重复运行。** 给 gate 上的两个文本版本各补到三次重复，已有的第一次会被跳过：

   ```powershell
   # 在 posttraining/ 下，PYTHONPATH=src；对 --bundle seed 和 --bundle gepa-r1 各跑一次
   ..\.venv\Scripts\python.exe -m shopsteward_pt.strategy_eval run --cases datasets/ops-synthetic-v1 --out ../docs/reports/strategy-eval/2026-10-08-gate --partition gate --bundle seed --replicates 3 --model deepseek-flash --key-file <密钥文件> --parallel 4 --max-model-calls 900
   ```

   然后对四种策略分别重跑 `gate` 命令。配对是按用例和重复序号做的。

2. **第二个随机种子的搜索。** 用 `.venv-evo`，换版本名和运行目录：

   ```powershell
   ..\.venv-evo\Scripts\python.exe -m shopsteward_pt.strategy_eval evolve --cases datasets/ops-synthetic-v1 --strategy adaptive_multi --max-metric-calls 100 --revision gepa-r2 --run-dir ../var/strategy-eval/gepa-r2 --seed 1 --key-file <密钥文件> --parallel 3
   ```

3. **把新结果补进[评测与演化报告](2026-10-08-strategy-evaluation.md)**，并更新第 3 节那两个默认值的建议。
4. **之后二选一**：给用例加入文档类证据，测试多专家策略可能占优的场景；或者开始 X3，先做两个人工基线 Skill 和 `SKILL.md` 导出。

## 10. 文档索引

| 文档 | 用途 |
|---|---|
| [技术选型与自进化设计](../superpowers/specs/2026-10-08-technology-selection-and-evolution-design.md) | 选了哪些技术、X1 到 X5 的拓展计划 |
| [评测与演化报告](2026-10-08-strategy-evaluation.md) | 这两天的全部实测结果和结论 |
| [评测运行说明](../runbooks/strategy-evaluation.md) | 评测与演化的命令、环境、用例集 |
| [下一阶段运行手册](../runbooks/next-phase-agent-recovery.md) | Case 专家的配置项和四种策略的行为 |
| [统一设计 v1.2](../superpowers/specs/2026-09-30-next-phase-integrated-design.md) | Multiagent × Context Engineering × Rubric 的完整目标设计 |
| [自进化总设计](../superpowers/specs/2026-10-03-memory-skill-workflow-evolution-design.md)及其[实施计划](../superpowers/plans/2026-10-03-memory-skill-workflow-evolution-plan.md) | Skill、流程、界面自进化的完整设计 |
| [核心实现交付报告](2026-10-02-next-phase-delivery.md) | 10 月 2 日那一轮交付了什么、没交付什么 |
