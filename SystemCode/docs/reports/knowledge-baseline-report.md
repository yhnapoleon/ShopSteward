# K0 知识资料与复用基线

2026-09-07。本报告区分源码能力、隔离实验和未运行项；K1实施与验证单列。技术规格和选择矩阵见[选型研究](../research/2026-09-07-knowledge-technology-options.md)，本轮范围见[K0–K1执行计划](../superpowers/plans/2026-09-07-k0-k1-execution.md)。

## 1. 当前架构决策

文档原件、元数据、版本、权限、业务实体链接由现有backend/PostgreSQL负责。检索是可重建投影：元数据查询、关键词、向量和关系查询可以分别演进。K1不引入embedding、vectorDB、图数据库，也不要求模型在线。

| 数据 | 首选取用 | RAG/图的补充作用 |
|---|---|---|
| 实时库存、现价、现金、订单、到货、预测版本、Plan与审批状态 | 现有backend API/SQL、精确ID与确定性计算 | 文档只解释背景，不能覆盖业务事实 |
| 供应商条款、商品保存/包装说明、SOP、活动要求 | 带门店、有效期、实体ID的文档管理；术语/编号先词法 | 同义问法与跨条款问题用混合检索；完整条件与来源定位必须保留 |
| 复盘、异常说明、培训FAQ、会议记录 | 可追溯原文与结构化标题 | 适合语义召回；意见/猜测与事实分开，不能把相关性变成因果 |
| 供应商→报价/SKU→Mission、文档明确适用于某SKU/任务 | PG关联或有界递归 | 关系引导找证据；同事实集比较后再决定是否有图数据库收益 |
| 数量阈值、准入条件、替代品适用限制、时间窗 | 类型化条件、确定性规则 | 可附关系边和原文证据；图路径本身不执行规则，也不证明可传递替代 |
| 用户私有笔记与Agent记忆 | 现有私有知识存储与owner授权 | 不默认进入门店共享RAG或共享图摘要 |

暂定试验顺序：PG元数据/实体关联＋词法 → BGE-M3与Qwen3-Embedding-0.6B的dense对照 → 相同词法候选做RRF → 有收益才加rerank。云small/large和Qwen4B是条件式对照。数据库选择先比较中文质量和维护代价：PG+pgvector较少服务，OpenSearch较多词法功能和RAilG适配复用，Qdrant适合独立向量负载。没有语义实测前不宣布最终模型或数据库胜者。

## 2. 环境与来源

- ShopSteward起始Git：`YH / 6fb71fa`；IH/railg：`c7048a3b4d3d8546a7e8d2f7cd5fbdf1b7df232d`，工作树有修改。20个候选文件逐一记录SHA256、dirty和适配要求，见[复用清单](../research/2026-09-07-knowledge-reuse-manifest.json)。K1独立实现文档管理，没有复制RAilG聊天/认证/配置加载器。
- Windows、Python3.12.13、约32GB系统内存、Intel Arc Graphics。没有根据显卡名称假定CUDA或推理吞吐；未安装/运行本地embedding模型。
- Docker Desktop原已运行；使用单独容器`shopsteward-k0-opensearch`，仅监听`127.0.0.1:19200`。OpenSearch2.17.1、Lucene9.11.1，JVM512MiB、容器上限2GiB。这是实验配置，不是生产资源建议。
- 镜像digest：`sha256:1193b7c29c5d63028523728243cc4da047ac49f697a8f8105e5aeee2f89bcc4c`。旧2.17.1只验证RAilG基线；生产版本另选受维护发行版并重复兼容检查。
- K0依赖在`var/k0/.venv`隔离安装，完整版本保存于[机器结果](../api/knowledge-k0-baseline-result.json)；没有把RAilG整栈加入backend。源项目未执行配置加载，未读取其API密钥。

## 3. 已运行的兼容实验

| 检查 | 实际结果 | 迁移要求 |
|---|---|---|
| RAilG schema/read/write/dimensions契约与chunker round-trip上游测试 | 26 passed | 说明所选依赖可运行这些算法；不代表整个IH栈通过 |
| 实际创建RAilG OpenSearch mapping | 通过 | 后续增加显式store/version/generation字段 |
| CJK分析器输入“冷链断电” | 输出单字与bigram，包含“冷链” | 保留分词快照，SKU独立keyword字段 |
| 带scope的原始bool.should查询完全不存在的词 | **仍返回可见但不相关文档** | 有scoring子句时显式`minimum_should_match=1`；不能将非空等同命中 |
| 相同查询只增加minimum_should_match=1 | 正确空结果 | 改动仅在实验adapter，未改IH工作树 |
| Lucene kNN内同时过滤store/version/ACL，其他范围有更近向量 | 只返回允许的当前版本 | 使用手写4维向量的协议探针；不是embedding质量评测 |
| 一个context60块，命中index55，调用原Store.fetch_siblings和construct_parents | 只取前50块，返回22～28块，**丢失命中块** | 必须以命中定位取有界邻居/manifest段落，返回前校验包含原hit，并标注截断 |

上游测试第一次执行因pytest将相对cache_dir解析到IH根目录产生缓存写入拒绝警告；随后关闭cacheprovider，以绝对临时目录复测26 passed、无警告。此事不影响算法结论，复现命令禁止往IH写缓存。

## 4. 语料解析与关键词结果

[冻结语料与说明](../evaluation/knowledge/README.md)：40份原件版本（38个逻辑文档），供应商12、商品8、SOP8、活动6、复盘6；8 PDF、6 DOCX、4 XLSX、4 CSV、11 MD、7 TXT。核心60问为40 dev/20 test，关系12问为8/4，未混合分母。标注由助手逐题独立编写，真人复核仍为pending。

生成器经过900项只读完整性检查；原件/canonical/manifest可逐字节重建，重复构建保留相同内容的mtime。外来文件保留并拒绝覆盖。相同路径与case引用均带hash，见[冻结证据](../evaluation/knowledge/freeze-evidence.json)。

实际只对`sources/`的原件调用RAilG extractor和chunker，没有将canonical或gold正文建索引。40份产生165个chunk，采用RAilG默认100 token启发式块尺寸、20行context、零overlap；无OCR、embedding、rerank或parent。结果如下：

- 38份原件的全部标注正文在抽取文本中保留（忽略空白比较）；这不是版式/单元格定位完整性评分。
- `K0-S04-v1`扫描PDF产生0个chunk；`K0-P02-v1`混合PDF仅第1节保留，第2页条件缺失。未删除这些问题以提高成绩。
- XLSX本次仍使用`data_only=True`，有缓存格可读缓存、无缓存格为空；未执行公式。公式字符串、缺缓存状态和实际sheet/range定位需要K2专门适配。
- DOCX/CSV/XLSX正文可抽取不等于已经支持引用定位；RAilG只有page/header信息，不能把sheet当真实PDF页码、也不能冒称有单元格/CSV行证据。

词法基线使用CJK/BM25、严格metadata授权/版本集合、`minimum_should_match=1`；每问原句直接检索top50 chunks，去重取前5个文档版本。没有自然语言实体解析或问题专用调参。下列Recall是**文档版本宏平均Recall@5**，不是回答准确率：

| 核心组 | dev有gold文档题数 | dev Recall@5 | test有gold文档题数 | test Recall@5 |
|---|---:|---:|---:|---:|
| exact | 8 | 100% | 4 | 100% |
| keyword | 8 | 87.50% | 4 | 100% |
| synonym | 8 | 75.00% | 4 | 100% |
| synthesis | 6 | 100% | 2 | 75.00% |
| no_answer（有诊断/冲突证据者） | 1 | 100% | 1 | 100% |
| business_mixed（需要文档证据者） | 4 | 70.83% | 3 | 100% |
| 合计 | 35/40 | **88.10%** | 18/20 | **97.22%** |

dev MRR@5=0.8143、nDCG@5=0.8170；test MRR@5=0.9444、nDCG@5=0.9375。其余5个dev/2个test为空gold或纯业务路由题，不计普通Recall；这7题关键词仍返回候选，因此**非空检索结果不能作为“有答案”判据**。无答案/冲突的生成行为与业务工具路由未执行，必须在K4另验。所施加scope的泄漏为0；这只是该fixture过滤器的结果，生产权限仍由K1/后续检索层分别验收。

最终证据轮串行延迟dev p50约9.98ms/p95约13.35ms，test p50约9.66ms/p95约13.15ms；仅40文件、局部缓存和本机隔离服务，没有并发、冷启动、模型或父块费用，不能当生产SLA。首轮与补充源文件hash/公式页证据后的复测质量指标一致，未据test结果调参。test比dev高也不代表泛化优势；小规模助手合成集存在简单措辞/双语重复与样本偏差，下一轮应补真实匿名资料和人工审阅后再决定模型胜者。

## 5. SQL关联与有界遍历对照

[关系机器结果](../api/knowledge-k0-relations-result.json)。在真实PostgreSQL17.11、`shopsteward_test`连接的临时表上运行；只写连接内临时表，事务结束删除，不修改业务表。

C为固定1～3跳JOIN，D为`WITH RECURSIVE`有界路径；两者接收相同人工指定`query_plan`，使用同一28条关系事实、来源权限、有效期、条件与路径后处理。**12/12题C与D返回同样的gold路径（dev8/test4）**：单步适用、多步SKU/Mission/SOP关联、跨店排除、非传递替代、过期关系、未确认/被拒绝的因果边和不完整图范围均包含。

该结果证明这些已知小样本可用PG关系表达，未发现递归比等价JOIN多找对路径。它不测试自然语言到query_plan的可靠性、原文答案正确性、Neo4j性能或全局GraphRAG。关系中的人工证据还包含未OCR扫描页，因此“能走到关系”不能替代“能取回可核验原文”。C/D可共用资料检索与定位层；本轮不将路径成功计为端到端RAG成功。

结论：K1只保存规范SKU/供应商链接；K2/K3按需求增加来源明确的适用关系，优先PG JOIN。有实际灵活路径需求再开放有界递归；没有依据现在增加Neo4j或Microsoft GraphRAG。

## 6. 尚未运行与结论边界

目前没有配置可用embedding/rerank端点密钥，也没有已安装本地模型。因此真实dense/RRF/rerank质量、token费用与推理延迟均未测；不能把协议向量或官方模型卡成绩当本项目成绩。pgvector/Qdrant的ANN、跨引擎中文排名与压力测试也未运行。模型/存储最终选择保留为K3实验门槛，K0完成的是来源、数据与可运行无模型基线。

无模型时K1仍可登记、管理和下载原件；K2才增加真实解析/索引消费者和关键词取回。Agent取用、引用卡与前端文档中心分别按K4/K5安排。

## 7. 复现入口

仓库根目录，在已运行的隔离OpenSearch19200与K0环境中执行：

```powershell
var/k0/.venv/Scripts/python.exe -B backend/tools/verify_knowledge_baseline.py --source-root '<IH中的railg仓库路径>' --protocol-only
```

首次准备隔离Python环境可执行`uv venv --python .venv/Scripts/python.exe var/k0/.venv`，然后`uv pip install --python var/k0/.venv/Scripts/python.exe -r docs/research/knowledge-k0-requirements.txt`；缓存使用本仓`.uv-cache`。锁定文件只适用于本次Windows/Python3.12实验，不加入backend生产依赖。已停止的本轮容器可由使用者显式`docker start shopsteward-k0-opensearch`恢复；新机器先由用户手动启动Docker Desktop，再用相同digest、单节点、关闭测试安全插件、loopback19200映射、512MiB JVM/2GiB容器上限准备隔离实例。该配置仅供本地合成数据实验。

runner使用随机`shopsteward_k0_*`索引并在finally删除自己创建的索引，拒绝非loopback/非19200地址，不载入IH `.env`。`--protocol-only`可独立重复上述mapping/检索/父块实验；去掉此参数运行完整40文件/60问基线。保存结果包含全部依赖版本、源hash、引擎版本、配置与逐问返回。

关系基线使用应用环境，从仓库根运行：

```powershell
.venv/Scripts/python.exe backend/tools/verify_knowledge_relations.py
```

此入口在进程内读取backend自身配置并强制改为`shopsteward_test`，不输出凭据；无需安装图数据库。与其他共享测试库验证串行执行。运行结束保留机器报告，K0隔离搜索容器已停止以释放内存，容器本身保留供显式重启复测；业务PostgreSQL与Docker Desktop未停止。
