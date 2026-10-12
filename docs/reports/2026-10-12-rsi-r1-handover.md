# 会话交接：合并 main、自进化 R0 与 R1 的搜索

写于 2026-10-12 上午（Asia/Shanghai）。读者是接手这条工作线的下一个对话，以及项目负责人。本文覆盖 2026-10-09 至 10-12 这一个对话的工作；更早的背景见[寻源交接](2026-10-08-sourcing-handover.md)和[上一份会话交接](2026-10-08-session-handover.md)，整个项目的总交接仍是仓库根目录的 [HANDOVER.md](../../HANDOVER.md)，本文没有改动它。

几个词在本文里的意思：

- **寻源循环**：主流程发需求，每家供应商一个审查者读文档交回报价卡，代码把关，求解器出方案，解释者把方案讲清楚。
- **单环节评测**：不跑整条循环，只对照标准答案跑解释，或只跑一家供应商的阅读。
- **放行比对**：候选文本与父版本在优化器没见过的 gate 划分上逐场景配对比较，通过才算放行。
- **排序分**：给优化器排序用的分数，不是成绩。对外报告用通过次数。

## 1. 现状一句话

`main` 已合并进 `YH` 并推送；自进化的 R0（仪器）做完；R1 的两次搜索各产出了一个候选解释文本，但放行比对还没跑，所以到现在没有任何新文本被放行。

## 2. 接手后先做什么

项目负责人的原话是“写个handover，我交给下一个对话跑”。我的理解是：R1 的放行比对由下一个对话执行。这一步约 350 次 `gpt-6-luna` 调用。我在上一条消息里问过是否开始，负责人没有直接回答“开始”，如果拿不准就先用一句话确认。

具体步骤和命令在第 8 节。

## 3. 项目负责人在这个对话里做的决定

按这些执行，不需要再问：

- **RSI 先细化设计再做**；设计见[寻源循环的自进化设计](../superpowers/specs/2026-10-09-sourcing-rsi-design.md)，第 9 节是实施记录。
- **R1 交给演化**，不手工补那一句；**先做难尺子再演化审查者文本**；**RSI 四轮不设时间上限**。
- **DeepSeek 已充值**，可以用。
- **Case 专家的默认策略改为固定流程**。已改，四种策略仍可切换。
- **`gepa-r1` 暂不启用**；多专家策略和 `gepa-r1` 要先找到或设计出合适的使用场景，负责人的说法是“先射箭再画靶”。
- **引入技术的标准**是前沿、能写进简历，要先调研；不要按课程要求覆盖面来排。
- **允许分批提交和推送**。远端仓库是公开的，推送前要扫密钥和本机路径。
- **2026-10-11**：我提了一个五步顺序（合并 `main`；做完 R0 并跑 R1；接后端和前端；选做两项；最后四天做报告和视频），负责人回复“可以，依次做1和2先”。我的理解是只确认了第 1、2 步，第 3 步是否提前到 R2、R3 之前没有明确。

沿用的旧决定：交付标准是概念验证；真实运行先小批量再放大；课程最终交付截止是 2026-10-25 23:59。

## 4. 等项目负责人决定的事

1. **前后端接入是否提前到 R1 之后。** 见上一节最后一条。
2. **引入哪些前沿技术。** 我调研后列了七项，建议做前三项：
   - S1 演化式程序搜索（OpenEvolve）做多商品多供应商联合补货
   - S2 时序基础模型 Chronos-2 做零样本预测
   - S3 把审查者的阅读规则做成 Skill 再演化
   - S4 MCP 服务器加 MCP Apps 界面
   - S5 AP2 式的签名授权
   - S6 把审查者蒸馏成小模型（需要 GPU，本机没有 NVIDIA 显卡）
   - S7 文档视觉模型读报价单
3. **“分头核查”多专家用例做不做。** 设想是三个专家在求解器出方案后各拿不同材料核查方案的输入，用场景自带的预设读错当用例，同时给 `gepa-r1` 一个靶子。要证明它适合多专家，需要一次小规模的单 Agent 对多专家比对，而负责人之前说过比对先搁置。
4. **修改方案守卫的取舍是否接受。** 见第 6 节。
5. **证据编号是否缩短。** 见第 7.3 节，它会改动产品里的编号格式。
6. **报告和两段视频由谁做。** 视频不允许用 AI 生成的配音。
7. **公开仓库里的数据切片是否介意。** 寻源数据集里有 91 段 M5 的周销量切片，已随代码推送。

调研的来源和每项的理由只在对话里讲过，没有写成文档。需要时重新调研，不要凭记忆引用数字。

## 5. 这个对话做了什么

按时间顺序：

1. 读交接、核对工作区；DeepSeek 充值后第一次在它上面跑通整条循环。
2. 写 RSI 细化设计；调研多专家的适用条件和前沿技术。
3. 把 2026-09-12 以来积压的全部工作分批提交并推送。
4. 默认策略改为固定流程。
5. R0：把关和 Case 运行器保存被拒的原文与理由；单环节评测；新循环的 GEPA 适配器；配对放行检查；失败台账。
6. 把 `origin/main` 合并进 `YH`，解决 13 个冲突文件，修了合并暴露的一处语义冲突和一个原有的不稳定测试。
7. R1：父版本在 gate 划分上的基线；两次 GEPA 搜索。

## 6. 合并 main 的要点

`main` 带来了队友的事项处理者、服务端报价工作流、数量比较和中英双语界面，共 9 个提交、135 个文件。

- **迁移**：两条历史都保留，新增合流迁移 `0017_cases_quotations_merge`，接在 `0015_quotations` 和 `0016_learning_foundation` 之后，做法沿用仓库里 `0014` 的先例。隔离测试库已升级。**负责人日常用的数据库还没有升级**，需要在 `backend/` 下执行一次 `alembic upgrade head`。
- **取并集的地方**：`/api/v1/me` 的能力列表、worker 的两种 profile（`learning` 和 `work`）、Alembic 的模型导入。
- **前端**：恢复方案的逻辑保留，外面套上 `main` 的翻译函数。
- **一处取舍**：`main` 的修改方案守卫只要消息里有否定词就拒绝；这边原有的测试要求“请把方案修改为最多20件，不要下单”能够修改。现在否定检查会先去掉“不要下单”这类拒绝购买的说法，其他否定照旧拒绝。代码在 `backend/app/work_items/authorization.py`。这是我做的取舍，负责人没有表态。
- **留下的尾巴**：这条线自己的四个页面（恢复工作区、学习工作区、上下文检查器、Skill 质量卡）约 134 条界面文字没有英文翻译，`node frontend/scripts/check-i18n.mjs` 会列出来；这个检查没有接进测试。前端浏览器端到端测试没有跑。

合并时顺手修的一个原有问题：学习调度 `enqueue_due` 按固定顺序只取前 100 个策略，排在后面的永远轮不到。测试库里累积到 155 个策略后，相关测试约三成概率失败。现在分页处理全部策略。

## 7. 关键结果

所有数字来自真实模型调用，每个配置的重复次数写在表里。场景是合成的，这些是开发级的观察。

### 7.1 基线

| 评测 | 模型 | 划分 | 运行数 | 通过 |
|---|---|---|---|---|
| 完整循环 | `deepseek-flash` | smoke | 12 | 11 |
| 阅读单测 | `deepseek-flash` | smoke | 42 | 42 |
| 阅读单测 | `deepseek-flash` | evo-val | 33 | 32 |
| 解释单测，每场景 3 次 | `gpt-6-luna` | evo-val | 36 | 26 |
| 解释单测，每场景 3 次 | `gpt-6-luna` | gate | 72 | 50 |
| 完整循环 | `gpt-6-luna` | gate | 24 | 15 |

最后两行是 R1 放行比对的父版本一侧，文本版本是 `seed`。完整循环那 24 次里，需求 24、全部审查 23、报价卡 23、决策 23、解释 15；78 张报价卡有 77 张可用。

读法：

- **阅读环节接近做满。** `deepseek-flash` 读 75 家只读错 1 张（按箱报价读成按件），所以要先做更难的数据集再演化审查者文本。
- **解释是主要的失分处**，而且单次波动大：gate 的 24 个场景里，三次全过的 7 个，过两次的 13 个，过一次的 3 个，全败的 1 个。

### 7.2 R1 的两次搜索

任务模型 `gpt-6-luna`，反思模型 `deepseek-v4-pro`，验证集是 evo-val 的 12 个场景各 3 次。

| 搜索 | 评测次数 | 起点排序分 | 最好候选排序分 | 改了哪条提问 | 存为 |
|---|---|---|---|---|---|
| 种子 0 | 204 | 0.889 | 0.972 | 影响 | `sourcing-r1-s0` |
| 种子 1 | 213 | 0.824 | 1.0 | 证据、影响 | `sourcing-r1-s1` |

两次搜索各自独立地在“影响”提问里加了同一个意思：报告的每个候选都要说明缺口，没有缺口也要明说。种子 1 还在“证据”提问里加了一段：每条说法照抄求解器的字段，求解器没给的值算缺失。

同一份初始文本两次测出 0.889 和 0.824，所以这两个验证分只说明方向。**两个候选都还没有过放行比对。**

搜索记录在 [strategy-eval/2026-10-11-r1-evolve/](strategy-eval/2026-10-11-r1-evolve/)。

### 7.3 保存被拒原文之后查到的两个原因

- **解释被整份拒收，是模型抄错了证据编号。** gate 基线 72 次里的 5 次全部如此。编号是 `snapshot:` 加 64 位十六进制，模型抄短了或抄重了一段，运行器按“引用了没有提供的证据”拒收。文本很难可靠地修好它，更稳妥的是把给模型看的编号缩短，但那会改动产品里的编号格式（`agent/src/shopsteward_agent/cases/frozen.py`），需要负责人同意。
- **报价卡被拒，是引文跨了多行。** 完整循环 gate 基线里被拒的 5 次阅读全部如此，其中 3 次是把“计价单位：箱”那一行和商品所在行接在一起。把关把引文当成一段连续原文去找，找不到就拒绝。上一份交接说的“引用了换算后的单价”在这些记录里没有出现。修法是让把关逐行核对多行引文。

这两处我都没有改。原因是 R1 的放行比对要求父版本和候选版本在同一套规则下比较，而父版本的基线已经按现在的规则跑完了。

### 7.4 用量

- OpenAI：这个对话约 720 次 `gpt-6-luna` 调用。没有配置价格表，金额没有算。
- DeepSeek：余额从 49.55 元到 43.16 元。10 月 9 日约 270 次 `deepseek-flash` 调用用了 1.34 元；两次搜索的反思调用用了约 5 元。

## 8. 下一步怎么做

在 `posttraining/` 目录下、设好 `$env:PYTHONPATH = "src"` 之后运行。密钥文件的本机路径不写进仓库，在助手的本机备忘里。

### 8.1 R1 的放行比对

门槛定义在设计文档第 4.4 节，目标是事先写下的，不要改：候选没有与求解结果矛盾的说法；没有“父版本多数通过、候选多数失败”的场景；通过率比父版本高至少 10 个百分点；完整循环各环节不变差。

```powershell
# 1. 两个候选各跑解释单测，gate 划分，每场景 3 次（各 72 次调用）。
#    结果和父版本写在同一个目录里，靠文本版本名区分。
..\.venv\Scripts\python.exe -m shopsteward_pt.strategy_eval stage --stage explain --cases datasets/ops-sourcing-v1 --out ../docs/reports/strategy-eval/2026-10-11-r1-explain --partition gate --replicates 3 --model gpt-6-luna --bundle sourcing-r1-s0 --key-file <OpenAI 密钥文件> --parallel 4
..\.venv\Scripts\python.exe -m shopsteward_pt.strategy_eval stage --stage explain --cases datasets/ops-sourcing-v1 --out ../docs/reports/strategy-eval/2026-10-11-r1-explain --partition gate --replicates 3 --model gpt-6-luna --bundle sourcing-r1-s1 --key-file <OpenAI 密钥文件> --parallel 4

# 2. 只看解释环节的配对结果
..\.venv\Scripts\python.exe -m shopsteward_pt.strategy_eval gate --stage explain --out ../docs/reports/strategy-eval/2026-10-11-r1-explain --baseline seed --candidate sourcing-r1-s0
..\.venv\Scripts\python.exe -m shopsteward_pt.strategy_eval gate --stage explain --out ../docs/reports/strategy-eval/2026-10-11-r1-explain --baseline seed --candidate sourcing-r1-s1

# 3. 给表现好的那个跑一遍完整循环（约 200 次调用），再带上循环结果做最终判定
..\.venv\Scripts\python.exe -m shopsteward_pt.strategy_eval source --cases datasets/ops-sourcing-v1 --out ../docs/reports/strategy-eval/2026-10-11-r1-loop --partition gate --model gpt-6-luna --bundle <选中的版本> --key-file <OpenAI 密钥文件> --parallel 3
..\.venv\Scripts\python.exe -m shopsteward_pt.strategy_eval gate --stage explain --out ../docs/reports/strategy-eval/2026-10-11-r1-explain --baseline seed --candidate <选中的版本> --loop-out ../docs/reports/strategy-eval/2026-10-11-r1-loop

# 4. 换一个模型确认没有变差，只报告，不作为否决项（约 100 次调用）
..\.venv\Scripts\python.exe -m shopsteward_pt.strategy_eval source --cases datasets/ops-sourcing-v1 --out ../docs/reports/strategy-eval/2026-10-09-sourcing-e2e-deepseek --partition smoke --model deepseek-flash --base-url https://api.deepseek.com --api-mode chat_completions --bundle <选中的版本> --key-file <DeepSeek 密钥文件> --parallel 3
```

判定结果写在 `gate-<版本>-explain.json`。无论通过与否，把结果写进设计文档第 9 节。两个候选都没通过时，按设计保留 `seed`，把过程写成负面结论，再由人补那一句、作为人工版本走同一道门槛。

通过之后“启用”是什么意思要说清楚：寻源循环还没有接进产品，解释用哪个文本版本由调用方传入。产品配置 `AGENT_CASE_TEXT_BUNDLE` 管的是 Case 专家，默认仍是 `seed`，不要因为 R1 通过就去改它。

### 8.2 R1 之后

1. **两处仪器修正**，各自单独测前后变化：把关逐行核对多行引文；缩短证据编号（需要负责人同意）。改完后重跑一遍完整循环的 gate 基线，作为后面几轮的新父版本。
2. **R2**：生成 `ops-sourcing-v2`，加难到 `deepseek-flash` 的报价卡可用率落在 60% 到 85% 之间。加难方向和停止条件在设计文档第 4.5 节。
3. **R3**：在 v2 上演化审查者文本，命令是 `evolve --stage read`。
4. **接后端和前端**：先读 `backend/app/quotations/` 和 [事项与报价接入](../work-intake-and-quotations.md)，寻源循环应接在队友的报价流程上。
5. 第 4 节里等决定的事。

## 9. 踩过的坑

- **搜索的日志停住不等于没跑完。** 种子 1 的搜索在凌晨停了五个多小时，早上又自己跑完了，很可能是机器休眠。我在它停住时向负责人报告了“没有跑完”，随后更正。判断是否结束要看日志末尾有没有 `exit` 行，或者版本文件是否已经生成。
- **单环节评测给模型的上下文必须和真实循环一致。** 最初给解释者的报价卡引用的是文档标题，真实循环里引用的是商品所在行，模型把它报成缺失。改成引用真实的行之后才开始记基线，之前 4 次试跑作废。
- **集成测试不会自己迁移数据库。** 它断言测试库已经在迁移头。新增迁移后要先执行 `.venv\Scripts\python.exe var\next-phase-tests\run.py backend -m alembic upgrade head`。
- **测试库在多次运行之间保留数据。** 测试不能断言全局数量。
- **生成文件不能靠文本合并。** 合并后要重新导出 OpenAPI 并执行 `api:check`。这次重新导出的结果与自动合并的一致。在 Windows 上 `python -m app.export_openapi` 会写出 CRLF 换行，内容没变时不要把它提交进去。
- **不要同时跑 GEPA 搜索和批量运行。** 沿用上一份交接的提醒，这次是串行跑的。
- **单次分数波动大。** 比较两个文本版本时每个场景至少跑 3 次，看多数。
- **反思模型不便宜。** 一次搜索的反思调用约 2.5 元。按 10 月 9 日测到的每次约 0.005 元算，同样 200 次评测如果用 `deepseek-flash` 做任务模型，任务调用本身才约 1 元。R3 的预算要把反思算进去。
- **长的补丁脚本写成文件再执行。** 在 Bash 里用 here-doc 传带引号的多段 Python 失败过一次。
- **推送前扫描。** 仓库公开。这个对话里两份旧交接和一条运行记录曾含本机绝对路径，已替换。

上一份交接第 8 节的坑仍然适用，尤其是测试数据库的启动方式。

## 10. 代码在哪里

分支 `YH`，与远端一致。写本文前的最后一个提交是 `d572dd5`，本文所在的提交只增加了本文。工作区只剩故意不提交的 `tmp/` 和 `output/`。

| 内容 | 位置 |
|---|---|
| 把关的拒绝理由、可单独调用的 `review_supplier` | `agent/src/shopsteward_agent/cases/sourcing.py`、`agent/src/shopsteward_agent/offer_cards.py` |
| Case 运行器保存被拒的回答 | `agent/src/shopsteward_agent/cases/runner.py` |
| 单环节评测、配对放行检查、失败台账 | `posttraining/src/shopsteward_pt/strategy_eval/stages.py` |
| 新循环的 GEPA 适配器与反馈文字 | `posttraining/src/shopsteward_pt/strategy_eval/evolve.py` |
| 命令 `stage`、`evolve --stage`、`gate --stage`、`ledger` | `posttraining/src/shopsteward_pt/strategy_eval/cli.py` |
| 两个候选解释文本 | `agent/src/shopsteward_agent/cases/bundles/case-experts/sourcing-r1-s0.json`、`sourcing-r1-s1.json` |
| 合流迁移 | `backend/migrations/versions/0017_cases_quotations_merge.py` |
| 修改方案守卫 | `backend/app/work_items/authorization.py` |
| 学习调度分页 | `backend/app/learning/dispatch.py` |
| 默认策略 | `backend/app/core/config.py` |
| 测试 | `posttraining/tests/strategy_eval/test_stages.py`、`test_evolve.py`；`agent/tests/test_case_sourcing.py`、`test_cases.py`；`backend/tests/integration/test_learning_jobs.py`、`backend/tests/unit/test_work_processor.py` |
| 运行结果 | `docs/reports/strategy-eval/` 下以 `2026-10-09-` 和 `2026-10-11-` 开头的目录 |

搜索的原始运行目录在 `var/strategy-eval/r1-explain-s0` 和 `r1-explain-s1`，没有进仓库。

## 11. 怎么运行

环境、测试命令和测试数据库的启停与上一份交接相同，命令说明在[评测运行说明](../runbooks/strategy-evaluation.md)，其中“单独跑一个环节”一节是这次新加的。

最近一次测试结果：

| 范围 | 结果 | 时间 |
|---|---|---|
| 后端全量，带数据库 | 741 通过，6 跳过 | 2026-10-11，合并和两处修正之后 |
| Agent，不带数据库 | 148 通过，3 跳过 | 2026-10-12 |
| Agent，带数据库 | 151 通过 | 2026-10-11 |
| 评测包，`.venv` | 46 通过，1 跳过 | 2026-10-12 |
| 评测包，`.venv-pt` | 102 通过，5 跳过 | 2026-10-12 |
| 评测包，`.venv-evo` | 44 通过 | 2026-10-12 |
| 前端类型检查、接口契约检查 | 通过 | 2026-10-11 |
| 前端浏览器端到端测试 | 没有跑 | — |

后端全量在最后几个只动评测包的提交之后没有重跑。

## 12. 还没做、还没验证的

- **R1 没有放行结论。** 两个候选只有验证集上的排序分。
- **R2、R3、可选的 R4 都没有开始。**
- **寻源循环仍没有接入后端和前端。**
- **两处已知原因的拒收没有修**，见第 7.3 节。
- **失败台账命令写了、有测试，但还没有在真实结果上生成过一份。**
- **文本制品文件里的 `gate` 字段没有回填。** 版本文件不可覆盖，放行结论目前只写在结果目录的 JSON 里。
- **界面英文翻译缺约 134 条**；前端浏览器测试没跑；负责人的日常数据库没升级迁移。
- **前沿技术一项都没有开始做**，“分头核查”用例只有对话里的设想，没有设计文档。
- **课程交付物没有动**：报告、两段视频、安装与使用指南、课程技术对照表、个人报告。
- 上一份交接第 13 节里其余没做的事仍然没做。

## 13. 文档索引

| 文档 | 用途 |
|---|---|
| [寻源循环的自进化设计](../superpowers/specs/2026-10-09-sourcing-rsi-design.md) | 四轮计划、门槛定义、第 9 节的实施记录 |
| [评测运行说明](../runbooks/strategy-evaluation.md) | 全部命令，含单环节评测和按环节演化 |
| [寻源交接](2026-10-08-sourcing-handover.md) | 寻源场景和循环的由来、数据来源、更早的坑 |
| [上一份会话交接](2026-10-08-session-handover.md) | 环境、测试数据库的用法、四种协作策略 |
| [评测与演化报告](2026-10-08-strategy-evaluation.md) | 旧任务上四种策略与 `gepa-r1` 的实测 |
| [事项与报价接入](../work-intake-and-quotations.md) | 队友的报价流程，接前后端之前要读 |
| [多智能体用例探索](../research/2026-09-30-multiagent-use-case-exploration.md) | 多专家用例最初的设计意图 |
