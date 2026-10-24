# 知识检索上云前本地准备 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在本地得到可搬迁的知识检索服务、首批有效语料、可用证据接口和部署演练包，使第一次上云主要是在真实网络与模型下验证配置及性能。

**Architecture:** 现有backend继续管理原件、权限、业务ID及发布版本；独立knowledge服务管理派生索引、关系和入库任务。本地通过HTTP连接两者，在不同数据库及进程中演练未来云端边界；embedding采用可切换远端接口，无模型时先验证真实词法路径与明确标记的协议夹具。

**Tech Stack:** 已有Python/uv、FastAPI、SQLAlchemy、PostgreSQL、pytest、Docker Compose；新增独立knowledge包及其迁移目录。首个词法适配复用已验证的OpenSearch CJK/BM25路径；云向量引擎与模型待真实对照。新镜像/依赖在实施时核查官方支持并锁定，不将K0旧镜像当发布默认。

**Spec:** [云端与扩展语料设计](../specs/2026-09-07-cloud-knowledge-and-corpus-design.md)、[原K0–K1边界](2026-09-07-k0-k1-execution.md)。本计划细化前者第7节；若旧总体计划要求把检索全部放backend或默认OpenSearch+BGE，以此处云服务边界为准。

**Status:** 2026-09-08用户已授权实施，语料、独立服务、Agent接入与搬迁工具正在实现和审查。实际数据库、索引、构建与恢复验收等待用户手动启动Docker；整体未完成。详见[实施与验收状态](../../reports/knowledge-precloud-readiness.md)。

## Global Constraints

- Docker Desktop仍由用户手动启动。
- 允许资料正文、查询和候选片段发送给云端模型。
- 区域暂不限定，按本机端到端实测选择。
- 文档embedding和query embedding均优先云端API；本地推理只作可选成本/速度对照，不作为首版依赖。
- 本地Agent获得带正文与元数据的候选证据。
- 现有backend仍是文档权限、版本及业务ID权威；云PG存派生文档/关系/索引generation，不允许独立更改权威字段。
- 精确ID或只要当前库存/价格的请求直接走backend，零embedding调用。
- 默认词法/dense各50，最多30条重排，返回最多6份证据、6000 token上下文；初始检索总deadline8秒，Agent工具总上限10秒。这些继承预算待测，不是延迟承诺。
- 原K0目录及冻结hash不改；扩展语料与压力语料隔离，题集gold不进入解析/检索输入。
- IH只读；实际复制的RAilG文件记录原hash、许可及修改，不依赖IH本机路径或密钥。
- 新迁移的revision/down_revision按实施时head确定；不直接编辑已经验收的0010迁移。
- 只在专用测试库、独立索引、受控文件根演练；不改8000/8001，不并行清理同一测试数据库。
- 数据库事务内不进行HTTP、embedding、解析或大文件IO；个人记忆与经营文档语料保持独立。
- 云资源、真实模型、付费试验没有运行就明确标未运行；协议夹具的分数不能成为效果或速度成绩。

## 1. 当前已具备与实际缺口

本轮只读检查源码：K1有9操作和原件校验，但KnowledgeDocument的CHECK约束固定UPLOADED/NOT_INDEXED；不能只改响应枚举就宣称可索引。原件版本不可变、latest_version_id不代表发布指针。现有infra/compose.yaml只定义业务PG，尚无独立knowledge镜像/服务。backend/app/agent_bridge/knowledge.py处理USER/NOTES/SKILL个人记忆；文档证据工具应另建模块。

| 已有基础 | 本地需补齐 |
|---|---|
| K0 40版本/72题与来源清单 | 新200份试运行资料、逐步1000份质量集、独立300题 |
| K1上传/版本/授权/归档/幂等 | 来源补充metadata、可重试入库、发布状态和索引世代 |
| RAilG兼容反例和词法实验 | 可部署parser/索引适配，固定引用，修复两项已复现问题 |
| 现有Agent业务工具及租约 | 事务外HTTP检索、最终复核、引用和批量证据工具 |
| 独立PG测试入口 | knowledge独立测试库、进程/容器、打包与恢复演练 |

## 2. 工作包、依赖和停止点

为避免把语料写作、分布式状态与部署脚本塞进同一实施任务，本计划分三个可独立审查的子计划。各子计划链接本文件并继承全部约束。

| 编号 | 本地交付 | 依赖 | 对应详细计划 |
|---|---|---|---|
| L0 | 现场清单、专用测试配置、基线证据 | 无 | 本文件第3节 |
| A1 | 扩展语料schema、事实/来源/题集验证器 | L0 | [A：语料与评测](2026-09-07-knowledge-precloud-data.md) |
| A2 | 200独立文档及稳定导入manifest | A1 | A |
| A3 | 1000文档+修订版本、300题、关系与压力分组 | A2 | A；可与服务实现并行 |
| B1 | 独立knowledge包、HTTP契约及可替换端口 | L0 | [B：本地检索服务](2026-09-07-knowledge-precloud-service.md) |
| B2 | 解析、chunk、locator、parent与原件存储 | B1；A2提供规模验证 | B |
| B3 | outbox、worker、投影、generation发布/重试 | B1/B2 | B |
| B4 | 真实词法候选、关系取回及远端模型适配 | B3 | B |
| C1 | 本地Agent只读证据闭环 | B4 | [C：集成与搬迁演练](2026-09-07-knowledge-precloud-readiness.md) |
| C2 | 可重复容器构建、数据导出/恢复与启动脚本 | B4；可与C1并行 | C |
| C3 | 端到端验收报告和云端试验输入包 | A2/C1/C2 | C |

首个上云试运行门槛为L0+A1+A2+B1–B4+C1–C3。**A3是MVP质量目标，不阻塞用200份资料开展第一次云端试验。** 此拆分让采集、合成和模型实测交错推进；不必等全部1000份写完才测试云端可达性。上线MVP的质量验收仍需要A3的冻结集。

可并行：A与B；C1与C2；A3与云端首轮试运行。必须顺序：契约→持久化/发布→取回；首批资料验证→扩量；本地可重复启动→云部署。共享backend迁移由B3单点修改，不能多个任务各自猜下一revision。

## 3. L0：现场和回归起点

**Files:** 新建`docs/reports/knowledge-precloud-start.md`；使用已有`backend/tests/integration/test_knowledge_runner.py`，不新增第三套业务测试初始化程序。

- [ ] 读取git状态、迁移heads、配置名称、现有进程/容器归属，报告只保存脱敏状态；保护当前未提交代码。
- [ ] 若Docker未运行，进行文件/单元检查，待用户手动启动后补PG步骤；不自动启动Desktop。
- [ ] 复用shopsteward_test，新增knowledge服务专用shopsteward_knowledge_test；数据库连接从本项目配置内部派生，不打印密码。确需建库时用显式名称，不把默认开发库当测试库。
- [ ] 保存原K0 manifest/freeze-evidence的SHA256与现有K1运行时契约hash。
- [ ] 在隔离库执行一次适当的K1起点验证；后续按实际改动运行相关检查，不每个文档任务重跑全套。

仓库根PowerShell入口：

```powershell
& ./.venv/Scripts/python.exe backend/tests/integration/test_knowledge_runner.py tests/unit/test_knowledge_storage.py tests/unit/test_knowledge_contract.py tests/integration/test_knowledge_documents.py -q
```

预期现有测试通过；若失败先定位并记录，不把失败视作新增任务的预期RED。每次数据库迁移前核对库名，迁移后运行已有schema-check。各代码任务结束做限定文件diff审阅并记录验证；是否创建commit遵循当前用户指示及.git权限，不把提交当用户未提供的前置授权。

## 4. 上云前验收清单

- [ ] 200份独立且有意义的文档实际存在；统计不把镜像、版本和无意义模板副本当独立文档。
- [ ] 可经真实K1 API导入、查看状态、重试失败，不能只把fixture直接塞进索引绕过上传流程。
- [ ] 一条完整HTTP路径：本地Agent工具→backend→独立knowledge进程→真实索引→候选→backend复核→Agent证据。
- [ ] 引用可定位到同一version/generation原文；扫描/公式缺缓存/截断明确；无证据可返回空。
- [ ] 更新失败仍可用旧发布；重复/乱序任务与worker重启不产生重复发布，归档/版本切换立即影响最终可见候选。
- [ ] 关系每条边有来源及条件；当前业务数据走backend；模拟数据不会污染现有门店。
- [ ] 没有模型密钥时真实词法路径可工作，语义路径显示disabled；人工向量夹具只作协议检查。
- [ ] 构建物不含IH绝对路径、.env、测试答案和本机文件路径；镜像、锁文件、配置模板和迁移相匹配。
- [ ] 在新的空卷/新数据库中成功恢复原件+metadata+关系并重建或恢复索引；校验hash与查询结果。
- [ ] 输出实测本地解析耗时、块数、首建时长、峰值内存、磁盘、并发/失败明细；不把loopback延迟外推云端。

以上是本地可搬迁验收，不是云端生产完成声明。无需先完成完整文档UI、自动OCR、全局GraphRAG、Neo4j、自托管GPU、三种VectorDB全量适配或多地域高可用。

## 5. 云端账号具备后才做的验证

实际模型/计价和可用区域、两个候选端点的query/document embedding、真实dense/RRF/rerank效果、托管向量DB行为、跨区域p50/p95、总成本及最终CPU规格。先核验账号/额度/预算，按同一200份语料试运行；后续用1000份/300题选择默认配置。

允许文本出云的偏好已保存，无需重问。本地准备可以先进行；账号密钥在开始真实调用时通过环境配置提供，不写入计划或聊天。区域按实测，不预先购买GPU实例。

## 6. 预计工作量与交付方式

以下是工程排期估算，不是承诺：L0与契约约0.5–1人日；A1/A2约2–4人日；B2/B3约3–5人日；B4约1–2人日；C1–C3约2–3人日。A3的额外采集/内容审阅约3–6人日，随公开资料可获取性和去重结果变化。并行可缩短日历时间，但状态机、引用和恢复验收不能省略。

执行顺序默认先L0，然后A1与B1分工推进，每个任务先RED再实现再检查；内容任务以来源和一致性审阅代替无意义的“文档数量测试”。每批报告已完成、真实证据、剩余缺口和下一门槛，不把整体计划勾选成完成。
