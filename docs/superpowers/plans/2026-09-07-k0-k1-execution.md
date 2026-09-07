# K0–K1 执行范围与选型门槛

2026-09-07。用户本轮授权开始K0–K1并重新比较embedding、vectorDB、图谱和取回方法。本文件细化当前执行范围，优先于原总体计划中跨阶段的示例。

## 工作划分

1. K0：40份合成资料、60核心问题＋12关系问题；逐文件复用清单；RAilG解析/切块/关键词/过滤实际兼容检查；embedding、搜索存储、关系查询的官方资料比较与可执行评测入口。
2. K1：实现独立于检索引擎的上传、元数据、不可变原件版本、授权读取、分页、归档与恢复后端；不实现K2索引worker、K3混合检索、K4Agent或K5前端。
3. 验证仅在专用测试环境。现有开发API/worker/数据库不自动迁移或重启。

## K1阶段契约收敛

原总体计划将202和索引JobRun同时写入K1示例，但实际消费者在K2。为避免登记无法处理的任务，本期上传完成返回201，明确`ingestion_status=UPLOADED`、`indexing_status=NOT_INDEXED`；不宣称解析或索引已开始。原件与元数据在本期可用。K2接入真实消费者时再增加受理任务与202入口，并同步契约。

- 创建文档、追加原件版本均支持Idempotency-Key，同键同请求返回原结果，同键不同内容409；重放前重新授权。
- GET列表/详情/版本/原件，PATCH元数据，POST control(archive/restore)本期实现。reindex、search、activate_index_version属于K2，保持planned，不注册成功的空实现。
- 文档保存latest_version_id与metadata_version；后续有效索引/生效发布指针另设，不能把最新上传当作已经生效或已经可检索。
- 原件版本不可变，包含SHA256、mime、长度、受控存储key、创建身份、有效期；本期不抽取业务数值。
- 本店共享与仅本人两种可见性。实体链接只接受当前店铺已存在的SKU/供应商标识，关系来自业务表。私有内容仅owner可读；admin沿用既有全店管理发现规则，但不得默认读取他人private正文。普通用户仍要求store授权。
- 原件上传以固定格式白名单、20MiB流式限制、Office ZIP体积/条目上限与基本格式校验处理；TXT/MD/CSV拒绝非法UTF-8、PDF/Office损坏返回明确422。20文件批量由客户端逐文件调用，本期不建设UI。
- 原件存储与数据库不共享事务，使用唯一随机版本key；事务失败可留下孤儿文件但不误删已有引用文件。不得由用户文件名决定路径。测试覆盖重试/并发，原件下载固定附件Content-Disposition与nosniff。
- 所有数据库用例短事务，文件流/内容校验不持有Store锁；版本分配/元数据更改/归档以文档行锁与expected_metadata_version处理竞争。
- 测试优先使用现有专用shopsteward_test，禁止SQLite替代PG验收；不改用户开发库，不启动第二个business worker。

## 技术选择规则

- RAilG默认BGE-M3 dense 1024维/OpenSearch 2.17.1/按原始分组合仅作基线；不等于完整BGE-M3 sparse/multi-vector能力已接入。
- 比较BGE-M3、Qwen3-Embedding、OpenAI embedding候选；无授权配置/可运行模型时不编造向量召回成绩，不静默下载大模型或使用其他项目密钥。
- 比较OpenSearch、PG+pgvector、Qdrant；K1不依赖任何一个。验证过滤发生的位置、维度/索引限制、中文词法召回和多版本一致性，不能只看向量查询速度。
- 比较metadata、BM25、向量、RRF混合、可选rerank、父段落还原；同预算、同作用域、同一数据集，分开记录解析与检索影响。
- 图关系先使用明确业务键/文档链接和PG JOIN；C/D对照共享关系事实。只有实际多步任务收益明确才考虑图数据库；不将结构化过滤收益误报为GraphRAG收益。

## 本轮完成标准

K0报告逐项区分已运行、静态核查、未配置不能运行；冻结评测和来源清单可重现。K1用户可上传/管理/读取原件，并有真实PG与HTTP验证、权限/幂等/并发测试。原backend/Agent/simulator必要回归、Alembic与runtime契约检查通过；报告保留跨阶段未实现边界。

## 选择与实施的依赖顺序

| 步骤 | 本轮产物 / 后续动作 | 决策依据 |
|---|---|---|
| K0-a 来源与问题冻结 | 逐文件SHA256；40份原件版本、60核心问、12关系问；gold与parser输入分离 | 不能拿官方榜单或IH私有资料替代ShopSteward问题 |
| K0-b 无模型基线 | RAilG原始协议反例、修正最小词法adapter、解析产物与逐问结果；SQL固定JOIN/有界递归同事实 | 先查解析丢失、权限与版本，再判断embedding是否能解决剩余失败 |
| K0-c 技术矩阵 | [官方选型比较](../../research/2026-09-07-knowledge-technology-options.md)、候选profile与通过门槛 | 模型、维度、分词、索引、融合拆开比较；未运行项明确留空 |
| K1-a 契约与持久化 | Document / immutable Version；最新上传指针；元数据CAS；既有Command收据 | 不提前绑定OpenSearch mapping、向量维度或图ID |
| K1-b 上传与原件 | 流式multipart；格式与体积限制；独占原件key；鉴权附件读取 | IO不占Store锁，解析/OCR属于K2 |
| K1-c 管理与权限 | 门店/分类/实体/标题筛选、游标、版本历史、私有资料、归档/恢复 | q仅标题字面查找；生效条款不是“最新版文件” |
| K1-d 验证与交接 | 真实PG、并发/幂等/撤权、真实HTTP与API重启、契约和原模块回归 | 独立审查后修复；只迁移测试库 |

## K2开始前固定的适配设计

以下是设计约束，尚未注册为运行时能力。

1. `DocumentVersion`是原件版本；`IndexGeneration`是一份原件在指定parser/chunker/embedding配置下的派生产物。一个原件可以有多个generation，失败generation不能修改已发布指针。
2. `EmbeddingProfile`至少记录provider、模型ID/revision、endpoint身份（不含密钥）、query/document instruction、tokenizer、pooling/归一化、维度、dtype、截断策略。相同维度不同模型不能共用向量列/索引空间。
3. `RetrievalProfile`记录词法分析器、字段boost、top-N、融合公式/常数、reranker和parent预算；改变它不一定重算embedding，但必须使结果缓存失效。
4. `SearchScope`由backend生成：principal、store_id、允许的document/version/generation集合、ACL/metadata revision、as_of和deadline。调用方不能传一个较宽集合绕过服务端授权。
5. 首个无模型路径是元数据→关键词→授权原文段落。扫描/混合PDF标记OCR_REQUIRED/PARTIAL；无缓存公式保留公式与缺值状态。K1接受原件不承诺K2可以完整解析它。
6. 把本轮发现的RAilG bool.should空命中问题和父块50条截断列为迁移回归。父块按同version/generation的manifest定位；任何扩展必须保留原始hit并明确截断，不能回退成不相关的中间段。

建议初始检索预算：词法/向量各top-50、RRF常数60（rank从1开始），去重后最多30条进入可选rerank，最终最多6个证据段、总上下文预算6000模型token。检索总deadline8秒、既有Agent工具总上限10秒；预算包括授权、SQL、网络、重排与父块，超时返回已授权的可用词法证据并注明降级。上述是待测起点，不是本机性能承诺。

## K3模型和存储的分阶段比较

- **模型独立试验**：固定同一parser/chunker输出，先做过滤后精确余弦排序，避免ANN掩盖embedding差异。BGE-M3 dense1024与Qwen0.6B1024/512为第一批；有合适资源才试Qwen4B；云端点获准且可用后small/large作对照。Qwen必须使用官方query instruction；模型支持缩维时显式请求/执行，不只改配置数字。
- **存储试验**：复用已计算的同一批向量，比较PG exact、pgvector HNSW、OpenSearch、Qdrant；分别记录向量邻居ANN recall和实际证据Recall。中文词法采用各自明确记录的配置，PG原生排名不能标成BM25。
- **高维策略**：Qwen4B原生2560、OpenAI large3072不能直接建pgvector普通vector HNSW（当前限制2000）。先试官方缩维；需要保留原维再单独测halfvec表达式索引＋原float重算。不能把缩维、量化和ANN误差混成一个模型分数。
- **选择门槛**：权限/归档/未来版本泄漏为0；精确ID与业务数字查询走确定性路径；有证据组Recall@5目标≥90%，同时看MRR/nDCG、必要条件证据与无答案行为。语义层必须修复词法实际漏召回且不引入不可接受退化。资料小且PG路径达标时优先较少服务；中文全文或独立向量负载的收益明确后才选择外部服务。
- **不扩展本轮**：不因当前电脑未配置模型而借用IH密钥、下载数GB模型、部署Neo4j或启动完整GraphRAG。后续启用的实际端点/本地模型决定可执行候选集，语料与接口已预先准备。

## 关系查询的定位

图是一种关系表达与取回方法，独立图数据库是另一个部署决策。已有业务键和人工确认APPLIES_TO关系可先在PG表达；C固定JOIN与D有界递归使用同一关系表、同一入口/终点、同一时间/权限与条件。遍历只返回证据路径和限制，不自动发布“全部受影响任务”、替代资格或因果结论。关系来自文档时还要携带source_version/locator；MENTIONS、candidate或rejected边不能升级成已确认业务关系。

只有同事实的D相对C确实增加必要证据、且维护和运行成本可接受，才在K3之后引入可选遍历；Neo4j需要额外证明复杂路径工作负载的收益。Microsoft GraphRAG是抽取/社区摘要/查询方法，留给跨大量复盘的全局主题问题单独立项，不与K1数据模型绑定。
