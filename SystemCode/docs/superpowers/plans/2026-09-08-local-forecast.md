# B1 本地预测完整实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成本地公开零售销量预测、独立评测、模型服务及backend/frontend/LangGraph经营闭环。

**Architecture:** ML只进行无业务副作用的预测；backend的独立forecast worker发布可追溯结果并唤醒现有规划。前端和LangGraph均通过backend读取同一预测，采购由原审批/执行路径处理。模拟器新增独立REPLAY，区分未来环境需求与模型可见历史。

**Tech Stack:** Python >=3.11、uv、pandas/NumPy/PyArrow、LightGBM CPU、FastAPI/Pydantic、现有PostgreSQL/SQLAlchemy/JobRun、Nuxt/Vue/ECharts、现有LangGraph。

**Spec:** [完整设计](../specs/2026-09-08-local-forecast-design.md)。实施者必须先读设计再读对应子计划。

## Global Constraints

- 首版完整闭环：公开数据预处理 → 时间切分 → 基线/机器学习实验 → 冻结模型 → 本地 HTTP 推理 → backend 异步校验发布 → 现有规划/审批 → 前端查看预测与来源 → LangGraph 按权限读取和请求刷新 → 独立回放比较经营结果。
- 模型不直接决定采购量，不计算或更改现金账本，不审批，不使用 RAG 文本直接改预测。
- 全部门槛完成前状态为b1_ready=false。
- 本轮交付的是设计与实施计划；所有复选框为后续代码实施状态，不能在未执行时勾选。
- 不执行清库、覆盖私有env、自动启动Docker Desktop或重复已有服务。保留`docs/proposals/`及其他同学改动。
- 设计基准`YH/4ff1e2d`。执行时复查Git、迁移head、runtime和端口；若已变化，先更新对应接入映射。

---

## 1. 已确认需求与默认设计决定

用户已确认公开数据路线，并要求覆盖从模型目标到前后端/LangGraph调用的完整计划。采用M5主线、500序列、7天预测、简单基线+LightGBM、固定测试集、本地CPU和单SKU回放。详细阈值/初始条件为本设计预先定义的可执行默认值；不把它们写成用户逐项指定或已实测结果。

暂不加入多SKU资金优化、缺货需求恢复、在线训练、云模型训练和概率区间。完整设计包含这些边界的原因及后续位置；不以“扩展性”为由实施。

## 2. 三个子计划与顺序

| 阶段 | 计划 | 独立可验收交付 | 依赖 |
|---|---|---|---|
| A | [数据/训练/推理](2026-09-08-local-forecast-model.md) | 原件manifest、500序列、冻结时间评测、模型制品、真实HTTP服务 | 数据可取得 |
| B | [backend/REPLAY](2026-09-08-local-forecast-backend.md) | 持久预测、独立worker、日结束事件、业务规划/审批与回放 | A1数据契约、A5制品/A6HTTP |
| C | [前端/LangGraph/验收](2026-09-08-local-forecast-product.md) | 预测图表/历史引用、真实工具调用、全栈重启证据 | B1/B4公开契约、B5回放 |

建议单线执行：A1→A2→A3→A4→A5→A6→B1→B2→B3→B4→B5→B6→C1→C2→C3→C4→C5。进入B/C前可用合成契约夹具开发，但正式通过必须替换成A的真实制品。若执行者使用多个代理，各自拥有明确文件范围；共享PG测试必须串行。

## 3. 状态门槛

| 门槛 | 判定 | 不通过时 |
|---|---|---|
| G0 data_ready | 原件hash、ID/日期/单位、抽样/切分、泄漏测试全通过 | 停止正式训练，保留诊断报告 |
| G1 artifact_ready | 三基线与4候选实验可复现，制品可加载 | 不启动业务模型模式 |
| G2 offline_model_validated | 测试weekly MAE改善>=5%，各销量组退步<=10%，bias/稳定性符合设计 | 只允许隔离candidate演示，不默认激活机器学习模型 |
| G3 backend_ready | PG版本/租约/超时/重复发布/采购约束通过 | 前端只能显示不可用或shadow |
| G4 replay_ready | 闭日/零销量/隐藏数据/重启正确，条件性经营指标有报告 | 不声称经营增强有效 |
| G5 agent_ready | 真实Luna工具轨迹、预测引用、权限、刷新排队、浏览器通过 | 受控模型测试仅标协议验证 |
| G6 b1_ready | G0～G5均通过且经营代价门槛通过 | 保留各分项实际状态，不能拿测试数量替代 |

G2失败时不得在同一个测试区间调参直到过关。修改训练方案需新版本与新的评价协议；没有额外独立数据时明确原测试已被使用，不能再次称盲测。

## 4. 验收数据与输出路径

Git保存：`docs/evaluation/forecast/{README.md,m5-manifest.json,series-manifest.json,split-manifest.json,feature-schema.json}`，`docs/reports/forecast-{offline,backend,replay,fullstack}.md`和各自机器结果摘要。大原件、逐点预测、模型和本机日志保存在Git忽略的`var/forecast/`，通过manifest定位与重建。

需要产出但尚未创建的工程手册为`docs/runbooks/forecast-local.md`。不得把当前设计文档当作已经验证的启动手册。所有命令结果记录actual_started_at、结束时间、commit、依赖锁hash和非通过项目。

## 5. 实施前与交付时检查

- [ ] 读取本轮设计和全部子计划；复核现有工作区与服务身份。
- [ ] 固定原件、500序列和切分；完成A后报告真实模型指标。
- [ ] 在专用环境完成B，保留SC01原数值与历史Plan hash。
- [ ] 完成C的真实Luna、浏览器和全进程重启；按设计给出六个ready状态。
- [ ] 将配置/端口/CLI实测写入运行手册；更新PROJECT_CONTEXT/HANDOVER，区分代码已写、训练已跑、服务已部署。
- [ ] 每个可独立验证任务完成后进行聚焦diff与提交；提交前检查暂存清单，不包含env、模型原件、数据库和无关提案。推送/合并/切开发环境按当次授权处理。

当前计划没有运行训练、测试或迁移，没有更改服务和业务代码。下一实际任务为A1。
