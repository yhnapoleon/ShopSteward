# 协作策略评测与文本演化运行说明

更新：2026-10-08。对应设计：[技术选型与受评估约束的自进化设计](../superpowers/specs/2026-10-08-technology-selection-and-evolution-design.md)的 X1、X2 阶段。实测结果见 [2026-10-08 评测与演化报告](../reports/2026-10-08-strategy-evaluation.md)。

这套工具离线运行：不连接数据库、后端和供应商，只读冻结的求解结果，所以不会产生任何业务副作用。它会调用真实模型，产生模型费用。

## 三个 Python 环境

| 环境 | 用途 | 说明 |
|---|---|---|
| `.venv` | 生成用例、批量运行、出报告 | 需要 LangGraph；生成用例还需要后端的求解器 |
| `.venv-pt` | 纯评分与核对器的测试 | 只依赖 Pydantic |
| `.venv-evo` | GEPA 演化 | 单独环境，装有 `gepa==0.1.4` 和与 `.venv` 相同版本的 Agent 依赖；线上进程不安装 GEPA |

重建 `.venv-evo`：

```powershell
uv venv .venv-evo --python 3.12
uv pip freeze --python .venv\Scripts\python.exe | Where-Object { $_ -notmatch '^-e |@ file:|^shopsteward' } | Set-Content var\main-constraints.txt
uv pip install --python .venv-evo\Scripts\python.exe -c var\main-constraints.txt "gepa==0.1.4" langgraph langchain-openai langchain-core openai pydantic httpx pytest pytest-asyncio
```

## 用例集

`posttraining/datasets/ops-synthetic-v1/` 是由 `generate` 命令确定性生成的 60 个合成用例，八个场景族，以确定性求解器的输出为标准答案。它衡量的是解释是否忠于求解结果，不衡量求解器本身。

| 划分 | 数量 | 用途 |
|---|---|---|
| `smoke` | 12 | 跑通流程 |
| `evo-train` | 12 | 优化器读取文字反馈 |
| `evo-val` | 12 | 优化器只读取分数，用来选候选 |
| `gate` | 24 | 发布对比；优化器永远不接触 |

每个用例要求说清三件事，并用可核对的结构化说法表达：推荐哪个候选、该候选是否还有缺口、等待会从第几天开始缺货。与求解结果矛盾的说法是关键失败。

## 命令

以下命令在 `posttraining/` 目录运行，先设置 `$env:PYTHONPATH = "src"`。

```powershell
# 重新生成用例（内容不变时文件哈希不变）
..\.venv\Scripts\python.exe -m shopsteward_pt.strategy_eval generate --out datasets/ops-synthetic-v1

# 不联网的全流程自检
..\.venv\Scripts\python.exe -m shopsteward_pt.strategy_eval run --cases datasets/ops-synthetic-v1 --out ../var/strategy-eval-check --partition smoke --limit 3 --fake

# 真实模型，小批量；同一 --out 目录里已完成的运行会被跳过，可以分批追加
..\.venv\Scripts\python.exe -m shopsteward_pt.strategy_eval run --cases datasets/ops-synthetic-v1 --out <结果目录> --partition smoke --limit 3 --model deepseek-flash --key-file <密钥文件> --max-model-calls 150

# 只重新出汇总表
..\.venv\Scripts\python.exe -m shopsteward_pt.strategy_eval report --out <结果目录>

# 演化（必须用 .venv-evo）
..\.venv-evo\Scripts\python.exe -m shopsteward_pt.strategy_eval evolve --cases datasets/ops-synthetic-v1 --strategy adaptive_multi --max-metric-calls 60 --revision <新版本名> --run-dir <目录> --key-file <密钥文件>

# 在 gate 划分上配对比较两个文本版本（先用 run 分别跑出两个版本的结果）
..\.venv\Scripts\python.exe -m shopsteward_pt.strategy_eval gate --out <结果目录> --strategy adaptive_multi --candidate <新版本名>
```

`--strategies` 默认四种全跑：`fixed`（R0）、`single`（R1）、`static_multi`（R2）、`adaptive_multi`（R3）。`--max-model-calls` 是整批的调用上限，剩余额度不够跑完一次完整运行时不再开始新的运行。密钥文件只含一行密钥，不要放进仓库。

## 多供应商寻源场景

`posttraining/datasets/ops-sourcing-v1/` 是第二套用例，用来比较“每个供应商一个分 Agent”和“一个 Agent 读完全部资料”。60 个场景，每个场景有 2 到 5 家虚构供应商，每家有报价单、通知函、合作条款和履约记录。

循环是这样的：主流程发出一份供货需求（门店、商品、日期、缺口）；审查者读某一家供应商的资料，返回一张报价卡，只报事实和出处，不选供应商也不定数量；代码把报价卡转成求解器的报价，由求解器比较并给出候选和推荐。场景的标准答案有两层：每家供应商的报价卡，以及求解器对真实报价卡给出的推荐。

数据来源：

| 内容 | 来源 | 说明 |
|---|---|---|
| 需求和零售价 | M5，即预测模块已在用的 500 条冻结序列 | 取测试期内每天都有销量、日均 4 到 40 件的整周；零售价按固定汇率 7.1 和成本占比 0.7 折成进货价，这两个数是假设 |
| 承诺交期与实际天数 | DataCo Smart Supply Chain，CC BY 4.0 | 按配送方式取承诺天数和实际天数分布，只用来生成履约记录。该数据的实际天数近乎均匀分布，本身可能是模拟的 |
| 供应商、文档文字、条款 | 虚构 | 由类型化事实渲染，所以标准答案精确可知 |

原始文件不进仓库。仓库里只有切片文件 `sources.json`，里面记录了来源、许可和原始文件哈希。每个场景族对应一种读错就会改变决策的情况，例如按箱报价、已生效或未生效的调价通知、被撤销的通知、交期调整、报价过期、暂停供货、商品不在报价单里、门店不在配送范围。

```powershell
# 从原始数据重建切片（只有换数据或改筛选规则时才需要）
..\.venv\Scripts\python.exe -m shopsteward_pt.strategy_eval sources --m5-raw <M5 原始目录> --m5-series <series-manifest.json> --dataco <DataCoSupplyChainDataset.csv> --out datasets/ops-sourcing-v1/sources.json

# 由切片确定性生成场景
..\.venv\Scripts\python.exe -m shopsteward_pt.strategy_eval generate --sourcing --out datasets/ops-sourcing-v1

# 不联网自检
..\.venv\Scripts\python.exe -m shopsteward_pt.strategy_eval review --cases datasets/ops-sourcing-v1 --out ../var/review-check --partition smoke --fake

# 真实模型；--arms 默认两种都跑，同一 --out 里已完成的运行会被跳过
..\.venv\Scripts\python.exe -m shopsteward_pt.strategy_eval review --cases datasets/ops-sourcing-v1 --out <结果目录> --partition smoke --model gpt-6-luna --base-url https://api.openai.com/v1 --key-file <密钥文件> --max-model-calls 60
```

`split` 是每家供应商一次调用，互相看不到对方的资料；`joint` 是一次调用看到全部供应商。两者用同一段指令和同一份输出约定。结果写入 `reviews.jsonl`（每次运行一行）和 `cards.jsonl`（模型返回的报价卡），汇总在 `review-summary.md`。

### 在 Agent 运行时里跑完整循环

`review` 是直接调用模型的对比工具。`source` 才是完整循环，走真实的 Agent 运行时（预算账本、调用记录、工具、上下文构建），代码在 `agent/src/shopsteward_agent/cases/sourcing.py`：

1. 根流程先让求解器算一次“不采购”，得到缺口，据此生成供货需求。
2. 每家供应商一个审查者，只能用 `read_supplier_document` 读自己那一家的文档，返回报价卡。
3. 代码把关：报价卡必须能解析、属于这家供应商、每个要求的字段都引用了它确实打开过的文档里的原文。不过关的重读一次，配置了 `supplier_escalation` 模型时由它重读；仍不过关的供应商标为未审查，不进入求解。
4. 调用方提供的求解器用通过的报价生成候选和推荐。
5. 沿用现有的解释流程（默认 `fixed`）解释这份方案。

```powershell
# 不联网自检
..\.venv\Scripts\python.exe -m shopsteward_pt.strategy_eval source --cases datasets/ops-sourcing-v1 --out ../var/source-check --partition smoke --fake

# 真实模型；--model 负责解释，未另行指定时也负责审查
..\.venv\Scripts\python.exe -m shopsteward_pt.strategy_eval source --cases datasets/ops-sourcing-v1 --out <结果目录> --partition smoke --model gpt-6-luna --key-file <密钥文件>

# 便宜模型初读，较强模型复读和解释
..\.venv\Scripts\python.exe -m shopsteward_pt.strategy_eval source --cases datasets/ops-sourcing-v1 --out <结果目录> --partition smoke --model gpt-6-luna --reviewer-model gpt-5-nano --second-model gpt-6-luna --key-file <密钥文件>
```

`--bundle` 和 `--review-bundle` 选择解释与审查所用的文本版本，默认都是 `seed`。审查者的提问是独立的文本制品，位于 `agent/src/shopsteward_agent/cases/bundles/supplier-review/`，和专家提问一样带哈希、不可覆盖；输出约定在代码里，不可演化。`--api-mode` 默认 `responses`：`gpt-6-luna` 在聊天补全接口下不支持“工具调用加推理”。

结果写入 `endtoend.jsonl`（每次运行一行）和 `endtoend-runs.jsonl`（完整运行结果），汇总在 `endtoend-summary.md`。一个场景算端到端成功，需要五个环节全部通过：需求与场景一致、每家供应商都拿到了通过把关的报价卡、求解器会读到的字段全部正确、推荐与标准推荐一致、解释说全了必须条件且没有与方案矛盾的说法。

这条循环目前只在评测包里被调用，还没有接入后端入口和前端。

被把关拒绝的报价卡会留下记录：`endtoend-runs.jsonl` 里每次阅读（`attempts`）带有 `problems`（代码）、`reasons`（哪个字段、哪份文档、哪句引文没找到）和 `answer`（被拒的原始回答）。复读时审查者会收到这些理由。

### 单独跑一个环节

完整循环每个场景约 8 次模型调用，而且一个环节的波动会盖住另一个。`stage` 命令对照标准答案只跑一个环节（2026-10-09 加入，设计见[寻源循环的自进化设计](../superpowers/specs/2026-10-09-sourcing-rsi-design.md)）：

- `--stage explain`：把标准答案的报价卡和求解器方案交给解释者，只跑解释，1 次模型调用。通过的标准与完整循环的解释环节相同。
- `--stage read`：一个审查者读一家供应商，含把关和一次复读。通过指求解器会读到的字段全部正确。

```powershell
# 不联网自检
..\.venv\Scripts\python.exe -m shopsteward_pt.strategy_eval stage --stage read --cases datasets/ops-sourcing-v1 --out ../var/stage-check --partition smoke --fake

# 解释环节，每个场景重复 3 次
..\.venv\Scripts\python.exe -m shopsteward_pt.strategy_eval stage --stage explain --cases datasets/ops-sourcing-v1 --out <结果目录> --partition evo-val --replicates 3 --model gpt-6-luna --key-file <OpenAI 密钥文件>

# 阅读环节，用 DeepSeek
..\.venv\Scripts\python.exe -m shopsteward_pt.strategy_eval stage --stage read --cases datasets/ops-sourcing-v1 --out <结果目录> --partition evo-val --model deepseek-flash --base-url https://api.deepseek.com --api-mode chat_completions --key-file <DeepSeek 密钥文件>
```

`--bundle` 选这个环节的文本版本。结果写入 `stage-<环节>.jsonl` 和 `stage-<环节>-runs.jsonl`，汇总在 `stage-summary.md`，其中“Failures”一列按失败种类计数。单次运行有波动，比较两个版本时每个场景至少重复 3 次。

演化某个环节的文本用 `evolve --stage`（必须用 `.venv-evo`）。验证集的每一项默认重复 3 次；任务模型和反思模型可以在不同的服务上：

```powershell
..\.venv-evo\Scripts\python.exe -m shopsteward_pt.strategy_eval evolve --stage explain --cases datasets/ops-sourcing-v1 --max-metric-calls 200 --revision <新版本名> --run-dir <新的运行目录> --model gpt-6-luna --base-url https://api.openai.com/v1 --api-mode responses --max-output-tokens 16000 --key-file <OpenAI 密钥文件> --reflection-model deepseek-v4-pro --reflection-base-url https://api.deepseek.com --reflection-api-mode chat_completions --reflection-key-file <DeepSeek 密钥文件>
```

读 `review` 的汇总表时注意：“Decision right”是求解器用模型的报价卡得出的推荐与标准推荐一致的场景数；“Cards safe”是求解器会读到的字段全部正确的报价卡数；“Truncated calls”是输出额度用完的调用数，这类失败不是读错。每条记录带提示词哈希，改了指令或输出约定之后的结果会单独成行，不要跨行比较。

## 结果文件

每个结果目录包含：`runs.jsonl`（每次运行一行摘要）、`traces.jsonl` 和 `results.jsonl`（评分器的轨迹与结果）、`analyses.jsonl`（合并后的说法与各子任务输出）、`summary.md` 和 `summary.json`。

汇总表里的“Mean score”是给优化器排序用的信号：有子任务失败、出现关键失败或与求解结果矛盾时为 0，否则等于必须条件的覆盖比例。它不是质量成绩，对外报告请用“Success”一列的计数。

## 文本制品

专家的提问收在 `agent/src/shopsteward_agent/cases/bundles/case-experts/<版本>.json`，带内容哈希，已保存的版本不可覆盖。只有六个组件可以演化：三条专家提问和三条角色指引。安全指令、输出格式、工具和角色工具白名单在代码里，优化器碰不到。四种策略被问的始终是同一组文本。

启用某个版本：设置 `AGENT_CASE_TEXT_BUNDLE=<版本>`，默认 `seed`。回滚就是把它改回去。每次运行的结果里记录所用版本及其哈希。

## 边界

- 用例是合成的，没有锁定测试集，结论只能表述为开发级结果。
- 发布对比是演示级的配对检查，不是统计意义上的非劣证明。
- 自由文字的说法没有被自动评分，需要人工复核。
