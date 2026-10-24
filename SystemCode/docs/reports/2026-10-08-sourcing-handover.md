# 会话交接：多 Agent 调研、多供应商寻源场景与端到端循环

写于 2026-10-08 下午（Asia/Shanghai）。读者是接手这条工作线的下一个对话，以及项目负责人。本文覆盖 2026-10-08 当天的第二段工作；同一天更早的工作见[上一份会话交接](2026-10-08-session-handover.md)，整个项目的总交接仍是仓库根目录的 [HANDOVER.md](../../HANDOVER.md)，本文没有改动它。

## 1. 现状一句话

为了找到多 Agent 真正合适的用例，新建了“多供应商寻源”场景和一条完整循环（主流程发需求、每家供应商一个分 Agent 审资料、代码把关、求解器出候选、主流程解释），已在真实的 Agent 运行时里用 OpenAI 模型端到端跑通；循环还没有接入后端入口和前端，所有代码都在工作区里，没有提交。

## 2. 项目负责人这次做的决定

接手后按这些执行，不需要再问：

- **方向**：现有的 Case 专家任务不适合多 Agent，新建多供应商寻源场景，尽量用真实的公开数据。
- **顺序**：多 Agent 与单 Agent 的比对先搁置；先把框架搭完整、保证端到端能跑；然后开始细化 RSI（自进化），并考虑引入其他技术。
- **模型密钥**：可以用本机的 OpenAI 密钥文件 `openai.txt` 调模型，它在仓库之外，本机路径不写进仓库。把路径当密钥文件传入，不要打印，不要复制进仓库。
- **上一份交接里仍然有效的决定**：交付标准是概念验证；真实运行先小批量再放大；没有要求提交代码，不要自行提交、重置或清理工作区；课程最终交付截止是 2026-10-25 23:59，提交前在 Canvas 复核。

循环的形态（分 Agent 只报事实，候选方案由求解器生成）是我提出的，项目负责人没有反对并让我继续搭，但没有明确表态确认。

## 3. 等项目负责人决定的事

1. **RSI 从哪里下手。** 我的建议见第 10 节。问题是先写一份细化设计，还是直接做。
2. **后端和前端什么时候接。** 现在接，还是等 RSI 做完再接。
3. **DeepSeek 余额。** 2026-10-08 约 11:17 起返回 `402 Insufficient Balance`。充值，还是之后都用 OpenAI。
4. **引入哪些技术。** 我给了建议（第 9 节），项目负责人还没表态。
5. **上一份交接第 3 节的三件事仍未答复**：默认策略是否从按需专家换掉、是否启用 `gepa-r1`、是否分批提交。那一节的“下一步先做哪个”已被本次的方向取代。

## 4. 调研结论

问题是：现在用多 Agent 的场景是否合适，什么用例才适合。

文献的共同结论：

| 发现 | 来源 |
|---|---|
| 可并行任务上集中式多 Agent 提升 80.9%；顺序型任务上所有多 Agent 变体下降 39%–70%；单 Agent 基线超过约 45% 后再加 Agent 收益转负 | [Towards a Science of Scaling Agent Systems](https://arxiv.org/abs/2512.08296v2) |
| 值得用多 Agent 的三种情况：子任务产生 1,000 token 以上且大多与主任务无关的上下文；可并行的独立方面；工具超过 20 个或跨不相关领域。代价是 3–10 倍 token。应按上下文边界拆分，不按问题类型拆分 | [Anthropic 2026 年 1 月指南](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them) |
| 并行分 Agent 各自做出的隐含决定会互相冲突；只读、定义清楚的调查类子任务可以接受 | [Cognition](https://cognition.com/blog/dont-build-multi-agents) |
| 模型越强多 Agent 优势越小；系统瓶颈在负责最难子任务的那个 Agent；先便宜方案、核对不过再升级的级联能提高准确率并降成本 | [Single-agent or Multi-agent Systems? Why Not Both?](https://arxiv.org/html/2505.18286v1) |
| 让模型做接口、算法做计算的混合框架，比让 GPT-4o 端到端求解的库存成本低 32.1% | [Ask, Clarify, Optimize](https://arxiv.org/abs/2601.00121) |

强弱模型怎么搭配，文献有分歧：Google 的研究（仅一个基准）发现分 Agent 的能力更重要；[另一项研究](https://arxiv.org/abs/2601.11327)（只读了摘要）发现协调者的能力更重要。我的理解是强模型要放在最难的子任务上，只能逐角色实测。

对照我们原来的任务，用已保存的 gate 运行记录算出（没有新调模型）：

- 三个专家拿到的上下文完全相同，没有上下文边界。
- 固定三专家的 24 次运行里，每一次都有某个专家独自说全了所有必须条件；63 个必须条件中 53 个被三个专家各说了一遍。
- 一次调用的基线是 23/24，远高于 45% 的饱和线；单次输入只有约 4,500 token。
- 证据专家设计上有文档检索工具，但评测环境没有实现，它无文档可查就向用户要，这正是“不必要的澄清”的来源。

结论是原任务上的多专家是把同一件事做三遍。

论文数字是通过网页抓取工具提取的，没有逐条对照 PDF 原文。

## 5. 这次做了什么

按时间顺序：

1. **多 Agent 调研**，结论见第 4 节。
2. **找公开数据并建场景。** 60 个寻源场景，188 份供应商资料。
3. **直接调用模型的比对工具**（`review`），比较“每家一次调用”和“一次调用读全部”。跑了 smoke 划分。项目负责人随后决定比对先搁置，这个工具保留但不再推进。
4. **回答“可以引入哪些技术”**，见第 9 节。
5. **在 Agent 运行时里搭完整循环**（`source_case`），加上端到端评测命令（`source`）。
6. **修了 Agent 模型适配器的一个已有缺陷**，见第 8 节第一条。
7. **真实模型端到端运行**，结果见第 6 节。

真实模型调用量：比对工具约 240 次（含丢弃的试跑），端到端约 300 次（含排查适配器缺陷时失败的调用）。没有逐次汇总，这是按运行数估算的。

## 6. 关键结果

都是 smoke 划分（12 个场景、42 份供应商资料），每个配置跑一次，属于开发级观察，不是统计结论。

### 6.1 循环怎么走

1. 根流程让求解器先算一次“不采购”，得到缺口，生成供货需求（门店、商品、日期、缺口量、哪天开始缺）。
2. 每家供应商一个审查者，只能用 `read_supplier_document` 读自己那一家的文档，返回一张报价卡：是否可供、单价、起订量、装箱、交期、有效期、报价单号、履约记录的两个计数，以及每项的原文出处。它不选供应商，不定数量。
3. 代码把关：报价卡要能解析、属于这家供应商、每个要求的字段都引用了它确实打开过的文档里的原文。不过关的重读一次，配置了 `supplier_escalation` 模型时由它重读；仍不过关就标为未审查，不进入求解。
4. 调用方提供的求解器用通过的报价生成候选和推荐。
5. 沿用现有的解释流程（默认 `fixed`）解释这份方案。

不让分 Agent 直接出方案的理由：数量取决于预算、现金和在途货，这些只有主流程掌握；每个分 Agent 只看得到一家，无法比较；报价卡的每个字段都能由代码核对。

### 6.2 端到端运行

结果在 [strategy-eval/2026-10-08-sourcing-e2e/](strategy-eval/2026-10-08-sourcing-e2e/)。

| 配置 | 端到端 | 需求 | 全部审查 | 报价卡正确 | 决策 | 解释 | 复读次数 |
|---|---|---|---|---|---|---|---|
| 全部角色用 `gpt-6-luna` | 8/12 | 12/12 | 12/12 | 42/42 | 12/12 | 8/12 | 0 |
| 同上，解释文本用 `gepa-r1` | 7/12 | 12/12 | 11/12 | 41/42 | 11/12 | 8/12 | 3 |
| `gpt-5-nano` 初读，`gpt-6-luna` 复读和解释（只跑 2 个场景） | 1/2 | 2/2 | 2/2 | 5/7 | 1/2 | 2/2 | 3 |

第一行平均每个场景 8 次模型调用、约 14.7 次工具调用、输入约 20,900 token、输出约 5,100 token，中位耗时约 33 秒。

从中得到三个具体问题：

- **解释漏说同一条。** 两组各 4 次失败，全部是没说“推荐方案是否还有缺口”（`gap:<推荐候选>=none`）。`gepa-r1` 没能补上：它当初是在 DeepSeek 上针对“不必要的澄清”演化的。
- **把关会误拒。** 按箱报价时单价要换算，原文里没有这个数；模型引用了换算后的数字，两次被拒，这家供应商被排除，决策随之出错。24 次运行里出现 1 次（`smoke-case_price-01`，供应商 D）。
- **把关拦不住读错。** `gpt-5-nano` 有两张卡引用合规但数值错（都是按箱报价读成按件），照样通过。

复读路径已被真实触发：`gpt-5-nano` 的 3 张被拒的卡交给 `gpt-6-luna` 重读，全部通过。

### 6.3 比对工具的结果（已搁置）

结果在 [strategy-eval/2026-10-08-sourcing/](strategy-eval/2026-10-08-sourcing/)。“分”是每家一次调用，“单”是一次调用读全部；这里是直接调用模型，文档直接放在上下文里，不经过工具。

| 模型 | 方式 | 决策正确 | 报价卡关键字段全对 | 无效卡 | 中位耗时 |
|---|---|---|---|---|---|
| `gpt-6-luna` | 分 | 12/12 | 42/42 | 0 | 6 秒 |
| `gpt-6-luna` | 单 | 12/12 | 41/42 | 0 | 13 秒 |
| `gpt-5-nano` | 分 | 7/12 | 33/42 | 4 | 52 秒 |
| `gpt-5-nano` | 单 | 4/12 | 21/42 | 15 | 102 秒 |
| `deepseek-flash` | 分 | 7/7 | 24/24 | 0 | 19 秒 |
| `deepseek-flash` | 单 | 8/8 | 27/27 | 0 | 30 秒 |

DeepSeek 两行因余额不足没有跑完。读法：够用的便宜模型在这个规模上两种方式都做满，分 Agent 只是更快；弱模型上分 Agent 明显更好，因为“单”方式下一次回答格式出错会废掉全部报价卡。`gpt-5-nano` 推理 token 多，按价格页估算每个场景反而比 `gpt-6-luna` 贵。

## 7. 场景与数据

数据集在 `posttraining/datasets/ops-sourcing-v1/`，60 个场景，划分与旧用例集相同（smoke 12、evo-train 12、evo-val 12、gate 24），各划分之间不共用 M5 序列。每个场景 2 到 5 家虚构供应商，每家有报价单（20 到 32 行）、通知函、合作条款、履约记录。

| 内容 | 来源 | 说明 |
|---|---|---|
| 需求和零售价 | M5，预测模块已在用的 500 条冻结序列 | 取测试期内每天都有销量、日均 4 到 40 件的整周，共 91 周 |
| 进货价 | 由零售价折算 | 汇率 7.1 和成本占比 0.7 是我设的假设 |
| 承诺交期与实际天数 | DataCo Smart Supply Chain，CC BY 4.0 | 只用于生成履约记录 |
| 供应商、文档文字 | 虚构 | 没找到带标准答案的公开供应商报价文档；由类型化事实渲染，所以标准答案精确可知 |

DataCo 的实际送达天数近乎均匀分布，“次日达”全部晚一天，数据本身很可能是模拟的；结果是履约记录里约 74% 的订单显示迟到。这只影响报价卡里的两个次要字段，数据源可以换。

十个场景族各对应一种“读错就会改变推荐”的情况：无陷阱的基线、按箱报价、已生效的调价、未生效的调价、交期调整、被撤销的通知、报价过期、暂停供货、商品不在报价单里、门店不在配送范围。生成时已验证每种读错确实会让求解器换推荐。报价过期按约定仍报为有报价并照抄日期，由求解器拒绝。

原始文件不进仓库：DataCo 在 `var/strategy-eval/sources/dataco/`（已被忽略），M5 在同级目录 `ShopSteward-forecast/var/forecast/data/raw/`。仓库里只有切片文件 `sources.json`，记录了来源、许可和原始文件哈希。

## 8. 踩过的坑

- **Agent 的 Responses 接口适配器有一个已有缺陷，已修。** 回传上一轮输出项时带了 SDK 的字段名 `async_` 和值为空的字段，接口返回 400。凡是“工具调用后再请求一次”的流程在这类模型上都会失败；之前没暴露，是因为实验都走 DeepSeek 的聊天补全接口。修复在 `agent/src/shopsteward_agent/model.py`，回归测试在 `agent/tests/test_model_protocol.py`。
- **`gpt-6-luna` 在聊天补全接口下不支持“工具加推理”。** 带工具的运行要用 Responses 接口，`source` 命令默认如此。不带工具的 `review` 命令走聊天补全没问题。
- **运行时会吞掉供应商报错。** 只留下 `AGENT_MODEL_FAILURE`。排查时在模型外面包一层打印异常的包装器。
- **`gpt-5-nano` 会把输出额度耗在推理上。** 8,192 的上限下大量调用被截断，默认已提到 16,000；汇总表有“截断调用”一列，这类失败不是读错。
- **输出约定的措辞会直接改变结果。** 最初“交付记录”一句有歧义，弱模型返回了整行数据而不是计数。修正后丢弃了之前的试跑并全部重跑。`review` 的每条记录带提示词哈希（当前是 `b6290f3f`），改了指令或约定后的结果会单独成行，不要跨行比较。
- **求解器最多接受三份报价。** 场景生成时保证了这一点；循环里通过把关的报价超过三份时结果是 `unsolved`。
- **运行时总会附带“向用户提问”的工具。** 审查者提问被记为失败（`asked_user`），不会真的去问。
- **上下文预算按 UTF-8 字节估算。** 产品默认的 24,000 对读中文文档的审查者偏紧，评测命令用的是 128,000。接后端时要给审查者单独的配置。
- **数据集是确定性生成的，测试会比对仓库里的清单。** 改供应商名单、报价单行数、近邻商品数都会改变 `ops-sourcing-v1`。要做更大的变体，用新的数据集名。
- **DeepSeek 余额已用完。** 恢复前不要安排 DeepSeek 的运行；先用一次调用确认。
- **上一份交接第 8 节的坑仍然适用**，尤其是测试数据库的启动方式和“不要同时跑 GEPA 搜索和批量运行”。

## 9. 关于“可以引入哪些技术”的建议

排序依据是课程要求：四组技术至少集成三组，而我们最弱的是“经营资源优化（启发式搜索或演化计算）”。现有求解器是有界枚举，GEPA 演化的是提示词而不是经营资源。

| 技术 | 用在哪 | 为什么 | 时机 |
|---|---|---|---|
| 结构化输出约束（JSON Schema 严格模式） | 分 Agent 的报价卡 | 实测弱模型大量报价卡因格式无效而作废 | 框架阶段 |
| 核对把关的级联 | 便宜模型初读，核对不过再升级 | “便宜模型做分 Agent 核”不掉表现的前提；现在的把关还不够，见第 6.2 节 | 框架阶段 |
| GEPA 扩到审查者文本和 Skill | RSI 的第一、二级 | 引擎已选定；新循环能给出逐环节、逐字段的文字反馈 | RSI |
| 失败转用例 | 真实运行的失败沉淀为新场景族 | 自进化需要一把会变难的尺子 | RSI |
| NSGA-II 或遗传算法做多商品多供应商联合补货，CP-SAT 给精确解作对照 | 求解层 | 直接对应“演化计算”；能做定量对比 | RSI 之后或并行 |
| 蒙特卡洛风险评估 | 用履约记录的延迟分布估计各候选的期望缺货 | 现在求解器不看供应商可靠性；加上后主流程在候选之间的选择才有实质内容 | 框架之后 |
| 保形预测 | 给 M5 预测加区间，把高分位需求作为一个情景交给求解器 | 补强“知识发现”组 | 可选 |

不建议现在引入：ACE 这类在线“经验手册”演化（第二个演化引擎，与“一个引擎、一道门”冲突）；A2A、MCP 协议化；微调、强化学习、更换 Agent 框架、LLM 协调器。

这些技术里哪些算课程的哪一组，仍需按课程口径确认。

## 10. 建议的下一步

按项目负责人定的顺序，框架之后是细化 RSI。我建议这样做，等第 3 节的答复：

1. **给新循环接上 GEPA。** 现有的 `strategy_eval/evolve.py` 只适配旧用例集上的四种策略，需要为 `source` 写一个适配器：评测一次就是在 evo-train 上跑端到端，文字反馈来自各环节的失败（哪张卡哪个字段错、解释漏了哪条）。可演化的文本有两份：解释用的 `case-experts` 和审查者用的 `supplier-review`。
2. **第一个靶子是解释漏说的那一条**，然后才是审查者文本。按第 6.2 节的用量，`gpt-6-luna` 上每评测一个场景约 8 次调用，100 次评测约 800 次调用。
3. **升级把关。** 被拒时把原因说清楚（现在只传了 `uncited:字段名` 这样的代码）；对便宜模型加“两次独立阅读一致才放行”。
4. **接后端和前端。** 我的想法是让审查者产出“待确认的结构化报价”，接到现有的“选报价、分析、确认采购”流程前面，原有审批链路不动。供应商文档从哪里来（知识服务还是 Case 附件）需要先定。
5. **之后再看**：第 9 节的求解层技术；把场景放大以恢复比对（供应商更多、报价单更长、或一次需求包含多个商品）。

上一份交接里没做完的事仍然没做：Skill 准入门槛的两档方案、前端浏览器测试重跑、日常数据库迁移、X3 到 X5。

## 11. 代码在哪里

分支 `YH`，HEAD 仍是 `30bed9f`，与远端一致。工作区有 52 个已修改的跟踪文件和 103 个未跟踪条目，包含更早的未提交工作。下表只列这次新增或改动的部分。

| 内容 | 位置 |
|---|---|
| 运行时里的循环（需求、审查者、把关、复读、求解回调、解释） | `agent/src/shopsteward_agent/cases/sourcing.py` |
| 报价卡约定、把关用的引用检查、报价卡转求解器报价 | `agent/src/shopsteward_agent/offer_cards.py` |
| 文本制品支持第二种制品（改动） | `agent/src/shopsteward_agent/cases/bundle.py` |
| 审查者的初始文本 | `agent/src/shopsteward_agent/cases/bundles/supplier-review/seed.json` |
| Responses 适配器修复（改动） | `agent/src/shopsteward_agent/model.py` |
| 公开数据切片 | `posttraining/src/shopsteward_pt/strategy_eval/sources.py` |
| 场景生成器（事实、文档渲染、标准答案） | `posttraining/src/shopsteward_pt/strategy_eval/sourcing.py` |
| 报价卡评分、调用求解器 | `posttraining/src/shopsteward_pt/strategy_eval/cards.py` |
| 端到端运行与分环节评分 | `posttraining/src/shopsteward_pt/strategy_eval/endtoend.py` |
| 比对工具（已搁置） | `posttraining/src/shopsteward_pt/strategy_eval/review.py` |
| 新增命令 `sources`、`generate --sourcing`、`review`、`source`（改动） | `posttraining/src/shopsteward_pt/strategy_eval/cli.py` |
| 数据集写入支持第二套用例（改动） | `posttraining/src/shopsteward_pt/strategy_eval/cases.py` |
| 数据集 | `posttraining/datasets/ops-sourcing-v1/` |
| 测试 | `agent/tests/test_case_sourcing.py`、`agent/tests/test_model_protocol.py`；`posttraining/tests/strategy_eval/` 下的 `test_sourcing.py`、`test_cards.py`、`test_review.py`、`test_endtoend.py` |
| 运行结果 | `docs/reports/strategy-eval/2026-10-08-sourcing/`、`docs/reports/strategy-eval/2026-10-08-sourcing-e2e/` |

后端和前端这次没有改动。

## 12. 怎么运行

环境与上一份交接相同：`.venv` 跑 Agent、后端和评测；`.venv-pt` 没有 LangGraph，端到端测试在那里会跳过；`.venv-evo` 用于 GEPA。

### 测试

从仓库根目录 `ShopSteward/` 运行。

```powershell
# Agent，不需要数据库
cd agent; ..\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider --basetemp=../var/strategy-tests/agent; cd ..

# 评测包：三个环境各跑一遍
.venv\Scripts\python.exe     -m pytest -c posttraining/pyproject.toml posttraining/tests/strategy_eval posttraining/tests/case_eval/test_strategy_trace.py -q -p no:cacheprovider --basetemp=var/strategy-tests/pt-main
.venv-pt\Scripts\python.exe  -m pytest -c posttraining/pyproject.toml posttraining/tests -q -p no:cacheprovider --basetemp=var/strategy-tests/pt
.venv-evo\Scripts\python.exe -m pytest -c posttraining/pyproject.toml posttraining/tests/strategy_eval -q -p no:cacheprovider --basetemp=var/strategy-tests/pt-evo
```

后端全量和带数据库的 Agent 测试，启动与停止测试数据库的写法见上一份交接第 6 节。

最近一次结果（2026-10-08 下午）：Agent 不带数据库 147 通过、3 跳过，带数据库 150 通过；后端全量 651 通过、3 跳过，与改动前一致；评测包三个环境分别是 40 通过 1 跳过、102 通过 4 跳过、35 通过；相关文件的 Ruff 检查和格式检查通过。优化器环境里有一次运行出现过 1 项失败，随后重跑 21 次都没有复现，没能定位是哪一项。

### 场景与循环

在 `posttraining/` 目录下、设好 `$env:PYTHONPATH = "src"` 之后运行。完整说明在[评测运行说明](../runbooks/strategy-evaluation.md)的“多供应商寻源场景”一节。

```powershell
# 不联网自检：整条循环用标准答案走一遍
..\.venv\Scripts\python.exe -m shopsteward_pt.strategy_eval source --cases datasets/ops-sourcing-v1 --out ../var/source-check --partition smoke --fake

# 真实模型端到端；同一 --out 里已完成的运行会被跳过
..\.venv\Scripts\python.exe -m shopsteward_pt.strategy_eval source --cases datasets/ops-sourcing-v1 --out ../docs/reports/strategy-eval/2026-10-08-sourcing-e2e --partition smoke --model gpt-6-luna --key-file <OpenAI 密钥文件> --parallel 3

# 便宜模型初读，较强模型复读和解释
..\.venv\Scripts\python.exe -m shopsteward_pt.strategy_eval source --cases datasets/ops-sourcing-v1 --out <结果目录> --partition smoke --model gpt-6-luna --reviewer-model gpt-5-nano --second-model gpt-6-luna --key-file <密钥文件>
```

`--bundle` 和 `--review-bundle` 选择解释与审查所用的文本版本。重新生成数据集用 `generate --sourcing --out datasets/ops-sourcing-v1`，内容不变时文件哈希不变。

## 13. 还没做、还没验证的

- **循环没有接入后端入口和前端。** 现在只有评测命令调用它。
- **只在 smoke 划分上跑过真实模型。** evo-train、evo-val、gate 都没有跑；每个配置只跑了一次。审查配置相同的两组运行里，复读次数分别是 0 和 3，单次波动不小。
- **只用了 OpenAI 的两个模型。** DeepSeek 因余额不足没有跑端到端。
- **把关的两个弱点没有修**，见第 6.2 节。
- **端到端结果没有接进 Rubric 评分轨迹。** 现在是 `endtoend.py` 自己的五个环节判定，没有生成 `CaseTrace`。
- **新循环还没有 GEPA 适配器，也没有 MAST 标签。**
- **结构化输出约束没有做**，只在第 9 节建议了。
- **文档是模板渲染的。** 版式单一，没有扫描件、PDF 或口语化的写法。
- **比对在这个规模上没有分出高下**，放大场景的工作没有做。

## 14. 文档索引

| 文档 | 用途 |
|---|---|
| [上一份会话交接](2026-10-08-session-handover.md) | 同一天更早的工作：四种协作策略、评测底座、GEPA 试点、测试数据库的用法 |
| [评测运行说明](../runbooks/strategy-evaluation.md) | 两套用例集、全部命令、怎么读汇总表 |
| [评测与演化报告](2026-10-08-strategy-evaluation.md) | 旧任务上四种策略与 `gepa-r1` 的实测 |
| [技术选型与自进化设计](../superpowers/specs/2026-10-08-technology-selection-and-evolution-design.md) | 已选定的技术、自进化阶梯、X1 到 X5 |
| [自进化总设计](../superpowers/specs/2026-10-03-memory-skill-workflow-evolution-design.md) | Skill、流程、界面自进化的完整设计 |
| [下一阶段运行手册](../runbooks/next-phase-agent-recovery.md) | Case 专家的配置项、产品里的使用流程 |
| [统一设计 v1.2](../superpowers/specs/2026-09-30-next-phase-integrated-design.md) | Multiagent × Context Engineering × Rubric 的目标设计 |
