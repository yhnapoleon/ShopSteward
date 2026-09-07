# ShopSteward 知识检索技术候选与选择门槛

日期：**2026-09-07**。状态：**官方资料与本地源码只读研究，尚未实测，未作最终选型**。

范围依据：[knowledge-retrieval-design](../superpowers/specs/2026-09-07-knowledge-retrieval-design.md)、[knowledge-data-and-graph-scope](../superpowers/specs/2026-09-07-knowledge-data-and-graph-scope.md)。沿用中文为主、中英混合经营资料，每店首版不超过 **1,000 份活动文档**、现有 PostgreSQL 17、Windows CPU/可选云 API 的约束。GPU、模型文件、pgvector 扩展及搜索服务是否已可用均未验证。

外部规格只依据下文就近链接的一手官方文档、模型卡；访问日期均为上述日期。`latest/main/current` 是在线资料，实施时须锁定发行版和模型 revision，不能当成旧部署已经支持的能力。本轮未读取 `.env` 或密钥，未下载模型、安装服务、调用付费 API、运行性能或效果实验。只产出本文件。

## 1. 决策摘要：复用 RAilG 算法，不继承未经验证的默认选型

**建议把原设计的“默认新增 OpenSearch + BGE-M3”调整为 K0 的候选组合。** 文档管理、版本发布、权限、结构解析与引用契约先保持稳定；embedding、词法引擎、向量存储分别选择，不能把替换任一层当作整套方案的优劣证据。

| 当前条件 | 优先试验/选择 | 进入下一档的条件 |
|---|---|---|
| 首批资料少，精确 SKU/供应商/版本查询为主 | PG 元数据、结构化字段、实体关联和可解释词法基线；语义调用可关闭 | 同义/跨条款组确有漏召回，再加 embedding；不是所有文件都向量化 |
| 可安装与 PG17 匹配的 pgvector，中文词法方案通过验收 | PG + pgvector；先测过滤后精确向量排序，再决定 HNSW | 分块规模、并发或建索引对业务 PG 的干扰超过预算，才考虑独立服务 |
| 中文全文、短语、字段权重/高亮成为核心，PG 词法方案不达标 | OpenSearch 作为 PG 的可重建检索投影 | 词法改善与迁移节省足以覆盖新增服务运维；锁版本验证 filter/mapping/融合 |
| 向量与稀疏/多向量检索是主要负载，需要独立扩展 | Qdrant + PG 权威元数据 | 中文 BM25 的具体运行路径通过验收，且维护投影的一致性代价可接受 |
| 资料不能外发 | BGE-M3 与 Qwen3-Embedding-0.6B 的本地候选；无可用模型时保留词法路径 | CPU 首次建库、单查询和内存达标后才启用；4B 不设为本机默认 |
| 已获准外发且有可用预算/端点 | OpenAI small 作云成本基线，large 作质量对照 | 冻结集改善、网络尾延迟及隐私要求均通过，才选择云默认 |
| 已有供应商/SKU/任务关系，主要是 1～3 跳 | PG JOIN/有界递归 + 原文证据 | Neo4j 需证明遍历/维护收益；Microsoft GraphRAG 需另有全局主题归纳需求 |

这些是项目建议，不是厂商性能结论；**1,000 文档不是 1,000 向量**，也不是引擎硬上限。要按分块数、保留版本数、店铺总数、权限选择率与并发测量。

### RAilG 静态核查与迁移影响

来源根目录：`D:/HuaweiMoveData/Users/13736/Desktop/IH/railg`，HEAD `c7048a3`，存在未提交改动；以下描述本轮读到的工作树，不声称仅凭该 commit 可复现。

| 本地证据 | 本项目含义 |
|---|---|
| `railg/config.py:34` 默认 BGE-M3、1024 维；rerank 默认开启；README 推荐第三方云端点 | 默认配置是接入选择，不是 ShopSteward 中文经营语料效果证据；第三方托管版本也不自动等同官方权重 |
| `railg/schema/mapping.py:76` 使用 OpenSearch Lucene HNSW；`build_settings` 使用 standard/CJK bigram 等自定义分析链 | 可复用分块/父块/证据算法；迁移 PG/Qdrant 要替换 store、DSL、分词和评分契约 |
| `docker-compose.yml:15` 固定 OpenSearch 2.17.1、heap 1GiB | heap 不等于进程总内存。2.17 文档已标记不再维护，生产候选需单独选受维护版本，不能直接把旧 compose 当部署决策。[官方 2.17 文档](https://docs.opensearch.org/2.17/search-plugins/knn/approximate-knn/) |
| `railg/providers/openai_compat.py:93` 只发送 `model/input`；`dims` 只验首个返回向量长度；按字符截断输入 | 改 `dims` 不会请求缩维。需适配模型指令、token 预算、`dimensions`/本地 MRL、归一化及每条返回值校验 |
| `railg/retrieval/builder.py` 把词法/kNN 放入 bool 子句；另有时间权重 | 不是 RRF。时间加权不能替代已生效版本筛选；参数与相似度阈值不能跨模型照搬 |

## 2. Embedding：规格可比较，中文业务效果尚未知

“小/中型号”在本研究指 Qwen3 **0.6B/4B**。上下文长度单位为模型 token，不能等同中文字数；长上下文上限不意味着应将整份合同编码成一个向量。

| 候选 | 官方规格与输入要求 | 中文/中英经营语料的试验价值 | Windows CPU / 云、成本与限制 |
|---|---|---|---|
| **BGE-M3** | Dense **1024 维**、**8192 token**；多语言，同时提供 dense、learned sparse、ColBERT 多向量；查询不要求额外 instruction；MIT。[BAAI 模型卡](https://huggingface.co/BAAI/bge-m3) | 与 RAilG 当前配置接近，适合作为迁移对照。先测 dense；其 learned sparse **不是 BM25**，多向量也不等于普通单向量索引 | 可自托管；CPU 吞吐、内存未测。不能把官方 GPU/FP16 示例视为本机可用。自托管没有逐 token API 账单，但有运行和维护成本 |
| **Qwen3-Embedding-0.6B** | **32～1024 维**（MRL），**32K token**，100+ 语言，Apache-2.0；检索 query 使用任务 instruction，文档不附同样指令。[Qwen 小模型卡](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) | 较小参数候选；试 1024 与 512 维，覆盖“少送/部分履约”、中英术语、否定和条件句 | 本地 CPU 候选不等于延迟承诺；需锁推理库、pooling、tokenizer、dtype。缩输出维度主要省存储/搜索，不能据此推导主干推理同幅加速 |
| **Qwen3-Embedding-4B** | **32～2560 维**（MRL），**32K token**，100+ 语言，Apache-2.0；官方建议多语言任务也优先试英文 instruction。[Qwen 中模型卡](https://huggingface.co/Qwen/Qwen3-Embedding-4B) | 与 0.6B 比较是否补回复杂条款证据；试 1024 与原生 2560 维，分开量化模型大小和缩维损失 | 仅在已有合适算力或获准托管端点时加入。4B×2 byte≈8GB 只是半精度参数估算，不含激活、运行时和缓存，更非本机最低内存/速度实测 |
| **OpenAI text-embedding-3-small** | 默认 **1536 维**，支持 `dimensions` 缩维；最大输入 **8192 token**。[Embeddings 指南](https://developers.openai.com/api/docs/guides/embeddings) | 云基线，试原生 1536 与 1024 维；用相同中文问题检验效果，不能以英文榜单代替 | 标准输入价 **$0.02/百万 token**；无需本地模型推理，但文档片段/查询发往服务商，受网络与限流影响。[官方模型价格](https://developers.openai.com/api/docs/models/text-embedding-3-small) |
| **OpenAI text-embedding-3-large** | 默认 **3072 维**，支持 `dimensions`；最大输入 **8192 token**。[Embeddings 指南](https://developers.openai.com/api/docs/guides/embeddings) | 试 1024/1536 与原生 3072 维，评估相对 small 的真实增益；不能预设更贵必然更适合 SKU/数字 | 标准输入价 **$0.13/百万 token**，同 token 量为 small 的 **6.5 倍**；只有新增召回/支撑收益值得成本时选择。[官方模型价格](https://developers.openai.com/api/docs/models/text-embedding-3-large) |

统一先比较 dense，固定结构块文本、标题/表头传播及余弦距离；各模型按自己的官方预处理执行。MRL 缩维后按所用实现重新归一化；BGE-M3 不自行假设支持任意截维。**同为 1024 维的不同模型仍属于不同向量空间**，query 与文档必须使用同一 profile。模型卡的 MTEB/C-MTEB 排名只说明其公开评测，本文不引用为本项目“准确率”。

### 维度与索引兼容：必须区分“能存”与“能建 ANN 索引”

pgvector 官方当前 README 列明：`vector` 类型可存至 16,000 维，但常规 **HNSW/IVFFlat 的 vector 索引至多 2,000 维**，`halfvec` 索引至多 4,000 维；采用完整精度存储、半精度表达式索引也是独立配置。[pgvector 类型与索引说明](https://github.com/pgvector/pgvector#hnsw)

| 输出 | PG `vector` 常规 HNSW | 高维处理候选 |
|---|---|---|
| BGE-M3 1024 / Qwen 0.6B ≤1024 / OpenAI small 1536 | 维度符合；仍需实际安装并验证 | 小数据可不建 ANN，先测过滤后精确距离排序 |
| Qwen 4B 原生 2560 / OpenAI large 原生 3072 | **不符合，不能直接建此索引** | 官方 MRL/`dimensions` 缩到 1024 或 1536；或 `halfvec` HNSW 候选召回后以原始 float 向量重算；或保留原维精确扫描/换引擎 |

半精度是**降低数值精度**，缩维是**减少坐标数**，两者不是同一实验。全精度重算也不能找回半精度/ANN 阶段已遗漏的候选。不要单为越过维度上限预先引入二值量化、复杂多向量链路。

OpenSearch 当前 `knn_vector` 的维度范围为 1～16,000，2.17 官方说明也列 Lucene/Faiss/NMSLIB 支持至 16,000；上述候选原维处于文档范围内，仍要验证实际版本、engine、距离和 dtype 组合。[当前 mapping](https://docs.opensearch.org/latest/mappings/supported-field-types/knn-vector/)、[2.17 kNN](https://docs.opensearch.org/2.17/search-plugins/knn/approximate-knn/)。Qdrant FAQ 给出 dense 至多 65,535 维，本项目候选远低于此范围；每个 named vector 的 size/distance 要固定，不能混装不同空间。[Qdrant FAQ](https://qdrant.tech/documentation/faq/qdrant-fundamentals/)、[Collection API](https://api.qdrant.tech/api-reference/collections/create-collection)

## 3. 检索存储：PG 与独立搜索服务的代价

| 维度 | PostgreSQL 17 + pgvector | OpenSearch + PG | Qdrant + PG |
|---|---|---|---|
| 强项 | 与权威元数据同事务、JOIN 和版本指针；可先精确向量查询 | 倒排词法与向量放在同一搜索服务；字段分析、短语、过滤，RAilG DSL 复用较多 | Dense/sparse、named vectors、多阶段检索与 RRF；向量负载可独立扩展 |
| 中文词法 | PG 原生 `ts_rank/ts_rank_cd` **不是 BM25**；需明确中文切词或 n-gram 方案、索引配置；不假设默认配置能得到中文词级召回 | 内置 CJK 使用字符 bigram，可比较 ICU；必须观察分词输出，保留 SKU `keyword` 字段 | 当前官方提供 BM25 稀疏编码/服务端路径；正文全文排名与 payload 文本过滤须区分；中文 tokenizer、客户端/服务端支持要逐项验证 |
| 过滤与 ANN | SQL 权限谓词可表达准确 scope，但 HNSW 先扫索引再过滤，严格 ACL 下可能不足 k；可试过滤后精确查、分区或 0.8+ iterative scan | 选 Lucene/Faiss 时把 scope 放进 kNN 内部 efficient filter；外部 bool/post_filter 可能使结果不足 k | 为 store/generation 等建立 payload index；filterable HNSW 使用过滤相关边，但多重严格过滤仍需测召回 |
| 版本与发布 | PG 内管理版本、generation、向量发布较直接；索引本身不理解“当前生效” | PG 发布指针与外部索引存在可见性窗口；新 generation 完整写入/可查询后发布，失败保留旧代 | 同样需要 PG→collection 投影、写入完成核验、发布与回收；collection alias 不能替代逐文档权限/有效期 |
| Windows 运维 | PG17 已有是优势，**pgvector 不随之自动存在**；官方 Windows 路径需 VS C++/nmake，与实际 PG 安装匹配。索引构建、VACUUM、WAL、备份与业务库争资源 | 有官方 Windows zip（含 JDK），也可容器；新增 JVM、磁盘、分片/刷新、备份、升级与认证配置；1GiB heap 不是完整资源预算 | 官方本地 quickstart 用 Docker，Windows 可能需 named volume；增加容器、持久卷、快照和版本管理；不把客户端本地模式结果当服务端基准 |
| 选用门槛 | 中文质量/延迟达标且业务 PG 不受显著干扰，优先保留少服务方案 | PG 词法不足，或全文能力/复用节省已证明值得新增运维 | 独立向量负载收益明确，且中文稀疏路径与 PG 同步成本均达标 |

表中能力依据：[PG17 文本排名](https://www.postgresql.org/docs/17/textsearch-controls.html#TEXTSEARCH-RANKING)、[pgvector 过滤](https://github.com/pgvector/pgvector#filtering)、[OpenSearch CJK](https://docs.opensearch.org/latest/analyzers/language-analyzers/cjk/)、[OpenSearch 过滤位置](https://docs.opensearch.org/latest/vector-search/filter-search-knn/index/)、[Qdrant 索引](https://qdrant.tech/documentation/manage-data/indexing/)、[Qdrant hybrid](https://qdrant.tech/documentation/search/hybrid-queries/)。部署依据：[pgvector Windows](https://github.com/pgvector/pgvector#windows)、[OpenSearch Windows](https://docs.opensearch.org/latest/install-and-configure/install-opensearch/windows/)、[Qdrant 本地 quickstart](https://qdrant.tech/documentation/quickstart/)。

**BM25 中文不能声称跨引擎等效。** Qdrant 当前全文文档写明默认有英文处理，提供 `multilingual` tokenizer，且示例明确此 tokenizer 选项不受 FastEmbed 支持；应核查具体服务端/云路径，不把开关照抄到本地客户端。[Qdrant 全文与分词](https://qdrant.tech/documentation/search/text-search/full-text-search/)、[服务端 BM25](https://qdrant.tech/documentation/inference/inference-bm25/)。比较必须记录 tokenizer、词典、大小写/全半角处理、停用词、词干、字段 boost、BM25 参数和 IDF 统计范围；一个 store 的 filter 不必然让 IDF 只按该店重算。先在共同作用域上比较引擎原生最佳方案，再用共同分词/候选列表隔离评分差异。

规模预算应使用 `N=各店各保留 generation 的 chunk 总数`。例如假设 1,000 文档×20 块=20,000 向量，float32 向量本体 `N×d×4`：1024 维约 **78MiB**、3072 维约 **234MiB**；这是算术示例，不是资源实测，未含 HNSW、文本、元数据、版本、WAL/副本。首版有限量并不能仅凭这些数字保证 CPU 延迟或内存可接受。

## 4. Retrieval 组合及不可替代的边界

| 层 | 建议用途/比较方式 | 必须保持的约束 |
|---|---|---|
| **metadata / SQL** | SKU、供应商、文档类型、有效期、已发布版本优先精确定位 | ID 使用规范业务键；同名不合并；精确读取 0 次模型调用。库存、现价、合计与计算仍由 backend/SQL 决定 |
| **词法 / BM25** | 编号、术语、否定、日期/单位等字面线索；查询“12箱”和“12件”应保留差异 | SKU 原文+规范 ID，数字/单位可作结构字段；BM25 命中数字不等于正确数值查询；不能靠相关分选择生效版本 |
| **dense + lexical + RRF** | 同义召回与字面匹配并行，按相同 chunk 身份去重融合 | 两路先施加同一 ACL/版本过滤；RRF 以排名融合，不是 BM25 原始分与 cosine 相加 |
| **rerank** | 对已授权 top-N 查询—片段对再排序，验证否定、例外与相关性 | 比较关闭、BGE-reranker-v2-m3、Qwen3-Reranker-0.6B；固定候选/输入长度。增加 CPU 或 API 延迟与外发文本；相关分不是事实蕴含概率 |
| **parent / small-to-big** | 用小块召回，按 manifest 还原标题、表头、条件、例外和相邻段落 | 同 document/version/generation，重新验权；预算不够必须明确截断；父块本来已在 Top-k 之外的部分不能伪称初始召回成功 |
| **graph-grounded** | 经实体/有界关系路径找到候选文档，再做相同检索并回看每条边证据 | 条件、有效期、来源与 assertion_status 随边返回；路径可达不保证替代有效、业务逻辑成立或因果关系 |

RRF 可在应用层固定为 `score(d)=Σ_i w_i/(c+rank_i(d))`，缺席某路贡献 0；实验约定 rank 从 1 开始、`c=60`、两路各取 top-50，最终评 Recall@5。它减少原始分尺度冲突，但仍需调候选深度/权重，不能作为可信度。OpenSearch 的原生 score-ranker/RRF **2.19 才引入**，RAilG 2.17.1 需应用层融合或另选版本。Qdrant 当前文档使用 **0 起始排名**，跨引擎复现须统一约定，不能只把相同常数填入就称相同算法配置。[OpenSearch RRF](https://docs.opensearch.org/latest/search-plugins/search-pipelines/score-ranker-processor/)、[Qdrant RRF](https://qdrant.tech/documentation/search/hybrid-queries/)

重排候选规格依据：[BAAI reranker 模型卡](https://huggingface.co/BAAI/bge-reranker-v2-m3)、[Qwen 0.6B reranker 模型卡](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B)。首轮以关闭为基线；候选缺失先修召回，不能指望 rerank 从空集合补回证据。parent 是上下文装配方法，可以复用 RAilG，但其原实现不自动满足完整还原与多版本授权。

## 5. 图：数据库、关联检索与 GraphRAG 方法分开选

| 方案 | 官方能力/性质 | 本项目适用与成本 | 采用条件 |
|---|---|---|---|
| **现有 PG 关系 / 递归** | JOIN、`WITH RECURSIVE`、路径及循环检测；已有业务键可直接使用。[PG17 递归查询](https://www.postgresql.org/docs/17/queries-with.html) | 文档 APPLIES_TO、已确认 SUPERSEDES、供应商→SKU→Mission；与 PG 授权/时间规则容易放在同一查询。需边数/深度限制，防循环及路径爆炸 | 先采用为 K0 表达方法；2～3 跳已满足需求时无需独立图数据库 |
| **Neo4j** | 属性图数据库，Cypher 支持可变长度/量化路径和路径谓词。[Cypher 路径](https://neo4j.com/docs/cypher-manual/current/patterns/variable-length-paths/) | 路径查询表达与图维护可成为收益；但新增 PG→图投影、版本/撤权同步与备份。CE 单实例；EE 额外集群、在线备份和安全能力，不能把 EE 能力计入免费 CE。[官方版本说明](https://neo4j.com/docs/operations-manual/current/introduction/)；[Windows 部署](https://neo4j.com/docs/operations-manual/current/installation/windows/) | 真实路径工作负载证明 PG 难维护或不达预算；同事实集上正确性不退化，且同步/运维收益明确。跳数多本身不是采用理由 |
| **Microsoft GraphRAG** | **索引与查询方法/软件管线，不是图数据库**。标准流程抽实体/关系、社区检测/摘要和 embedding，默认输出 Parquet 与配置的向量存储。[索引概览](https://microsoft.github.io/graphrag/index/overview/) | Local 将图结构与原文结合；Global 利用社区报告归纳全局主题。涉及抽取/摘要/更新的模型与人工审核成本；不能替代精确 SKU、实时金额 SQL，也不要求先部署 Neo4j。[Local](https://microsoft.github.io/graphrag/query/local_search/)、[Global](https://microsoft.github.io/graphrag/query/global_search/) | 只有反复出现“跨大量复盘的共同主题”等全局问题，并有单独评测、模型/维护预算后再试；本轮 72 问不足以批准全局 GraphRAG |

graph-grounded 首轮使用相同人工确认/业务记录关系，对照 SQL 限定与有界遍历，不能只给图方案更完整答案关系。每条边保留来源定位、限定条件、有效区间、状态和 revision；`MENTIONS` 不提升为 `APPLIES_TO`，A→B→C 不推出 A 可替代 C。图不完整时不能回答“全部受影响任务”。社区报告若混入不可见/过期文档，仅在最终输出过滤原文不足以消除泄漏：需按安全作用域构建、追踪依赖并失效/重建，成本也计入选型。

## 6. 权限、多版本、缓存、隐私与成本的共同契约

以下为项目实现约束，适用于所有候选；数据库支持 filter 并不等于应用已完成权限控制。

- **权限/时间**：服务端取得 `principal/store`，PG 决定允许的文档、有效 version/generation 与 `as_of`。空授权集立即返回空；两路召回、rerank 前、parent、图每条路径、最终引用/下载与缓存重放均校验。外部索引只作派生投影，撤权不能等其异步删除；不得通过补 k 放宽 ACL。
- **发布**：新 generation 构建、计数/manifest/搜索可见性核验后再原子切换 PG 指针；失败保持旧代。未来、过期、局部替换不能被“最近更新时间”覆盖。模型变更以新 profile/generation 双读对照后切换，不在旧向量列中混用空间。
- **缓存分层**：解析缓存键包含内容 hash、parser/OCR/表格及 chunk profile；embedding 键包含规范化块 hash、模型 ID/revision（云端若不可固定则记录服务标识与构建时间）、端点身份、tokenizer、query/document instruction、维度、dtype/量化、pooling/归一化与截断策略。结果缓存另含 principal/store、ACL/metadata revision、授权 generation 集摘要、`as_of`、词法/融合/rerank/parent profile；失效时间不越过下一生效边界。改 ACL 不必重算相同文本向量，但必须立即使结果/父块/关系/历史重放失效并重新验权；不能只以文件 hash 判断不用更新。
- **云边界**：云 embedding 外发块文本，云 rerank 外发 query+候选原文，GraphRAG 还可能外发抽取/摘要上下文。OpenAI 默认不使用 API 数据训练（除非主动选择共享），但滥用监控日志通常保留至多 30 天并存在例外；ZDR/MAM 需资格与批准，不能从“不训练”推导“零保留”。[OpenAI 数据控制](https://developers.openai.com/api/docs/guides/your-data)。区域/账号/端点可达性、合同与托管模型版本均待核验；本报告未调用任何云模型。
- **总成本**：embedding 费用约为 `(新增/变更块 token + 未命中缓存的 query token + 失败重试 token)/1e6 × 单价`。例如实际计费输入合计 100 万 token，small/large 标准价分别约 $0.02/$0.13；**不包含**生成、rerank、OCR、图摘要、存储、网络及运维，也不是“每千文档价格”。自托管计算 CPU 时间、峰值 RAM、能耗和维护工时；缩维降低存储不自动降低按输入 token 计价。隐私约束不满足时不以便宜为由转云。

## 7. 推荐试验矩阵与通过条件（待运行）

沿用 K0 **40 份合成资料、60 核心问（40 调参/20 冻结）+12 关系问（8/4）**；不可重新混合分母。精确、词法、同义、综合、无答案/冲突、业务混合分别报告；权限/版本等另设系统验收。补充用例覆盖 SKU 连字符/前导零、全半角、中英别名、12箱/12件、0.5/5、含税/未税、否定/例外、同名跨店、过期/未来/部分替换、无证据和关系不完整。新增压力语料不用于冒充新的独立效果样本。

按阶梯执行，避免一次展开所有引擎×模型×维度×重排组合；没有合法可用的运行条件就记 **未运行及原因**，不记 0 分，也不补造结果。

| 阶段 | 最小对照矩阵 | 控制变量/记录 | 选择门槛 |
|---|---|---|---|
| **T0 元数据与词法** | 精确 PG；PG 明确中文预处理+原生排名；OpenSearch CJK/BM25；Qdrant 明确运行路径的 BM25 | 相同文档/过滤/版本/定位；保存分词输出与字面命中反例，排名算法差异单独注明 | 精确 ID/版本 100%正确、0模型调用；权限/归档/未来版本泄漏为0；词法已达标可延后向量 |
| **T1 embedding 独立比较** | BGE-M3 1024；Qwen0.6B 1024/512；有资源才加 Qwen4B 1024/2560；获准云 small 1536/1024、large 3072/1536/1024 | 在同一过滤后精确向量排序器比较 dense，再与固定词法列表做同一 RRF；先关 rerank，统一 parent/上下文预算；模型预处理遵官方要求 | 同义/综合组相对 T0 有可解释改善，精确/数值/无答案组不退化；不按模型卡排名决定胜者 |
| **T2 存储/索引** | 只取 T1 入围1～2模型：PG exact vs vector HNSW；高维另测 halfvec；OpenSearch Lucene/Faiss按需；Qdrant filtered HNSW | 固定向量/profile，分开 ANN recall@k（对精确邻居）与证据 Recall@5；测40→1000文档、实际块数/版本、过滤剩余1%/10%/100%、并发1/5与冷/热缓存 | 在约定召回预算内满足延迟，且PG业务查询不受不可接受干扰；若exact已够快，不强制ANN |
| **T3 融合/重排/父块消融** | lexical vs dense vs RRF；入围组合 rerank关/BGE-v2-m3/Qwen0.6B；parent关/开 | 词法/向量各top-50，去重后固定top-30重排；相同最终证据/上下文预算。区分rank常数、截断和故障降级 | 有证据问题Recall@5目标≥90%（继承原设计目标，未实测）；重排须提高nDCG/MRR或实际支撑且不破坏总deadline；parent应补全条件而非只增加token |
| **T4 关系** | 原范围 A元数据词法/B混合/C SQL实体限定/D有界路径+同一检索 | 相同边与来源，报告单步/多步/条件反例/不完整组；逐边权限、有效期、来源定位、人工维护分钟数 | D必须比C多找对必需证据且不增加错误路径，才启用遍历；Neo4j与全局GraphRAG另过需求门槛，不在此自动部署 |
| **T5 运维/成本** | 入围组合首建/增量、模型缩维重建、版本发布失败、撤权、搜索/模型超时与重启恢复 | p50/p95、query与ingest分列、CPU/RAM/磁盘、PG负载、API token/重试/费用、维护时间；审计冷缓存与缓存失效 | 继承检索8秒内返回或明确降级、工具10秒总上限；所有权限/版本/引用及SC01边界通过，否则不能上线 |

每次记录：语料/问题集 hash、相关性标注与支持 locator、模型 revision、运行硬件/OS/库、维度/精度、引擎/插件版本、索引参数、分析器和所有缓存 profile。固定生成模型与证据预算，优先看检索/支撑，不让生成差异掩盖召回差异；冻结集只作验收，逐问报告改对/改错与原始分子/分母。72 问规模不足以宣称统计显著或代表真实经营收益。

**最终选择原则**：先过权限、版本、数值边界与超时硬门槛；质量接近时选总成本和维护负担较小者。PG、OpenSearch、Qdrant及各模型当前均未获得本项目实测胜出资格。若新增层没有可解释收益，保留较简单路径；后续依据真实误召回和运行数据再升级。
