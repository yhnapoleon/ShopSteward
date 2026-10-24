# 上云准备B：独立检索服务 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 本地运行与未来云端相同的HTTP知识服务，具备真实解析、可靠入库、词法候选、关系证据及可测试的模型适配接口。

**Architecture:** 新增uv workspace成员knowledge；backend保留文档权威并通过outbox投递，knowledge使用独立PG数据库和索引。接口模型无业务DB依赖，运行时/解析依赖放可选extra；backend只依赖轻量契约与HTTP客户端。

**Tech Stack:** Python、pydantic、FastAPI、SQLAlchemy/asyncpg、Alembic、httpx、PostgreSQL；首个真实词法实现OpenSearch CJK/BM25，协议端口可接后续pgvector/Qdrant；parser选择性复用RAilG，保留MIT来源。

**Spec:** [云设计](../specs/2026-09-07-cloud-knowledge-and-corpus-design.md)、[主计划](2026-09-07-knowledge-precloud.md)。这里选择OpenSearch作为本地真实词法适配，不构成最终云VectorDB决定。

## Global Constraints

完整继承主计划Global Constraints。B3单独负责backend新增迁移及共享文件，避免并行迁移分叉。knowledge服务不得对业务stores/products建立跨库FK；用外部ID与metadata revision投影。K0 OpenSearch 2.17.1只用于反例复现；可交付镜像在B4实施时核查官方支持与兼容并锁定digest。

## B1：进程边界、契约及端口

**Files:** 新建`knowledge/pyproject.toml`、`knowledge/src/shopsteward_knowledge/{__init__,contracts,ports,config,api}.py`、`knowledge/tests/{conftest,test_contracts}.py`；修改根`pyproject.toml`/`uv.lock`加入workspace；新建`docs/api/knowledge-service-v1.openapi.json`与`docs/api/examples/knowledge-search-response.json`。

契约根依赖只需pydantic；`service` extra包含API/DB/迁移，`parsers` extra包含实际采用的解析库，`opensearch` extra包含索引client。backend导入contracts不能启动API、连接DB、载入模型或导入IH。新包pytest配置testpaths=tests、asyncio_mode=auto，tests通过workspace安装后的包导入。

**Interfaces:**

- `OriginalRef`：version_id、sha256、mime、storage_key、size_bytes。
- `EvidenceLocator`：kind=page/paragraph/table/cells、page（可空）、section_path、paragraph_range（可空）、sheet/cell_range（可空）；不能为DOCX假造固定页码。
- `Candidate`：设计第5节全部字段；`metadata_revision`统一映射K1的metadata_version；`text`必填非空；scores分通道，未执行的通道为null或不出现，不能填0伪装已执行。
- `SearchScope`：principal_ref、store_id、as_of、expires_at、allowed_versions（每项version_id/generation_id/metadata_revision）；空列表意为无授权结果。
- `SearchRequest`：query、scope、profile_id、deadline_ms；`SearchResponse`：request_id、profiles、index_watermark、timings_ms、degraded、warnings、candidates。
- `EmbeddingPort.embed(texts: list[str], *, input_type: Literal['query','document'], profile: dict, deadline_ms: int) -> list[list[float]]`，async。
- `IndexPort.upsert(generation_id: str, chunks: list[dict]) -> None`、`search(request: SearchRequest) -> list[Candidate]`、`delete_generation(generation_id: str) -> None`，均async。每次upsert相同chunk ID幂等。
- `BlobPort.put(key: str, data: bytes, sha256: str) -> None`、`get(key: str) -> bytes`，async；使用local volume首适配。

HTTP接口由backend服务身份调用，不直接暴露数据库凭据给Agent：

| 接口 | 契约 |
|---|---|
| POST `/internal/v1/ingestions` | manifest+原件，Idempotency-Key；实际任务落库后202/job_id |
| GET `/internal/v1/ingestions/{job_id}` | 持久化状态、错误码、attempt、generation与manifest hash |
| POST `/internal/v1/projections` | 版本化metadata快照/归档tombstone；同revision同hash幂等、低revision拒绝覆盖 |
| POST `/internal/v1/search` | SearchRequest→SearchResponse，无模型仍可词法 |
| POST `/internal/v1/evidence` | scope+最多20个chunk身份，返回同一Candidate证据结构 |
| GET `/health/live`、`/health/ready` | 存活；DB迁移/已启用索引依赖检查 |

B1仅创建完整模型、OpenAPI生成与HTTP测试壳，未接消费者的接口不能返回成功，返回503/NOT_READY；B3/B4各自接通后才标implemented。

- [ ] 建以下RED与超额budget、缺少locator、未知字段拒绝用例；为model_validate准备完整JSON fixture，内容来自设计中的模拟证据而非gold。

```python
from shopsteward_knowledge.contracts import SearchScope

def test_empty_scope_does_not_mean_all_documents():
    scope = SearchScope.model_validate({
        "principal_ref": "P1", "store_id": "S1",
        "as_of": "2026-09-07T00:00:00Z", "expires_at": "2026-09-07T00:00:30Z",
        "allowed_versions": [],
    })
    assert scope.allowed_versions == []
```

- [ ] 执行`uv run --package shopsteward-knowledge --extra service --group dev pytest -c knowledge/pyproject.toml knowledge/tests/test_contracts.py -q`，先确认模块/模型未实现RED，再以pydantic extra=forbid实现模型与有界字段，复测并校验导出OpenAPI。
- [ ] SearchScope只能由backend生成；API服务凭据从环境读。日志保留request_id/耗时/错误类别，不默认输出整份原件或密钥。引用content_sha256明确是所返回text的UTF-8 hash，原件sha另存original_sha256，避免混用。

## B2：解析、引用和parent恢复

**Files:** 新建`knowledge/src/shopsteward_knowledge/parsing/{__init__,models,pdf,office,text,chunking,parent}.py`、`storage/local.py`、`THIRD_PARTY_NOTICES.md`、`knowledge/tests/test_parsing.py`、`knowledge/tests/test_parent.py`；实际复制时更新`docs/research/2026-09-07-knowledge-reuse-manifest.json`的destination/hash，不改IH。

**Interfaces:** `parse_original(ref: OriginalRef, content: bytes) -> ParseResult`；ParseResult包含blocks、coverage、warnings及status=COMPLETE/PARTIAL/OCR_REQUIRED/UNSUPPORTED。`chunk_blocks(blocks: list[dict], profile: dict) -> list[dict]`；每块ID来自version+parser/chunker profile+locator+text hash。`expand_parent(chunks: list[dict], hit_id: str, *, radius: int, max_chars: int) -> dict`返回text、chunk_ids、truncated，始终含hit。

- [ ] 把K0丢失hit反例写成RED；不要求新块恰好沿用旧bug的中间区间。

```python
from shopsteward_knowledge.parsing.parent import expand_parent

def test_parent_keeps_hit_beyond_fiftieth_chunk():
    chunks = [{"id": str(i), "text": f"条款{i}", "ordinal": i,
               "version_id": "V1", "generation_id": "G1", "parent_id": "P1"}
              for i in range(60)]
    result = expand_parent(chunks, "55", radius=2, max_chars=1000)
    assert "55" in result["chunk_ids"]
    assert "条款55" in result["text"]
```

- [ ] 运行knowledge/tests/test_parent.py确认RED；先按manifest精确找到hit位置，再取有界同parent/version/generation邻域，预算不够保留hit并标truncated。越版本或hit缺失抛明确错误，不猜位置。
- [ ] 将K0真实PDF/DOCX/XLSX/CSV/MD/TXT送parse_original；纯扫描返回OCR_REQUIRED；混合扫描保留文本页并PARTIAL；Office chartsheet保留存在/未解析状态，不能把上传可接受等同内容已完整抽取。
- [ ] XLSX同时读取公式与缓存信息，记录sheet与cell range，缺缓存不填0、不重算；PDF保留真实页号；DOCX使用段落/表格索引，表头连同数据传递；UTF-8正文不做丢弃错误字符的解码。
- [ ] 用同一原件重复解析验证固定profile下locator与chunk ID可重现；原件hash不符拒绝。local BlobPort只接受受控相对key，测试原目录迁移后仍能取回相同bytes。
- [ ] 全部解析/parent单元检查通过后，用A2 200份真实原件跑覆盖报告，分别报解析失败和检索失败；parser工作在worker独立进程，不阻塞API事件循环。

## B3：可靠投影、任务与发布

**Files:** 新建`backend/app/knowledge/{index_models,indexing,publisher,service_client}.py`，修改`repository.py`、`schemas.py`、`router.py`与DB就绪检查；backend新增迁移文件名`knowledge_index_delivery`前缀的唯一revision（先读取head再生成）。新建`knowledge/migrations/`独立Alembic链，以及`knowledge/src/shopsteward_knowledge/{db,models,ingestion,worker,publication}.py`；测试`backend/tests/integration/test_knowledge_delivery.py`、`knowledge/tests/integration/test_ingestion.py`。

**数据:**

- backend `knowledge_delivery_outbox`：id、document/version ID、metadata_revision、operation、payload_hash、state、attempt、next_attempt_at、lease_owner/token/until、error；唯一业务幂等键。原件字节存文件，不塞outbox行。
- backend `knowledge_publications`：document/version ID、有效区间、generation_id、manifest_hash、metadata_revision、publication_revision；按as_of选发布证据，不能用latest_version_id替代。
- backend `knowledge_version_provenance`：version_id唯一FK、source_kind、source_family_id、scenario_family_id、source_url、publisher、jurisdiction、synthetic及原件hash；随原件版本写入后不可变。为UploadMetadata/AppendMetadata新增可选provenance对象，旧请求可省略；版本DTO返回它，既有原件不可变触发器保留。不能将来源metadata仅放云索引而丢失权威原件关联，也不能在现有extra=forbid请求中直接塞未定义字段。
- knowledge投影表、jobs、index_generations、chunks、relations。云表只用外部标识，不依赖本地business FK。
- 分离状态：job PENDING/RUNNING/RETRY_WAIT/SUCCEEDED/FAILED；generation BUILDING/READY/FAILED；publication只有backend确认后可见。旧K1的上传状态保持UPLOADED；新增独立index详情字段，迁移放宽indexing_status CHECK并明确NOT_INDEXED/QUEUED/INDEXING/READY/PARTIAL/FAILED，不能向历史客户端偷偷复用不兼容含义。

**Interfaces:**

- `request_index(session, principal, version_id: str, profile_id: str, key: str) -> dict`只在本地事务登记outbox/请求；新增POST `/api/v1/documents/{document_id}/versions/{version_id}/index-jobs`返回202和本地request_id。
- 新增GET `/api/v1/documents/{document_id}/index-jobs/{request_id}`返回持久化进度；读取授权沿用K1。
- GET文档详情增加publication_revision与发布概要，使客户端可以取得发布CAS的当前值；不存在发布时revision=0。新index-jobs/发布写端点沿用K1写权限、owner/private规则及Idempotency-Key。
- `deliver_once(settings) -> bool`由独立`python -m app.knowledge.publisher`循环运行：claim事务提交→HTTP→ack事务；不启动第二个现有业务worker。
- `ingest_once(settings) -> bool`由`python -m shopsteward_knowledge.worker`执行：claim→解析/索引→READY；每次完成核对lease token。
- `activate_generation(session, principal, version_id, generation_id, manifest_hash, expected_publication_revision) -> dict`：先在事务外取得READY证明，再在事务内CAS核对本地最新metadata/有效期及证明对应请求；新增POST `/api/v1/documents/{document_id}/publications`。READY不自动等于已发布，未来版本按as_of过滤。
- 同版本新generation失败保留旧发布；不同原件版本的重叠有效区间必须显式确定替换范围，不能默认“更新日期较晚者胜”。
- `projection_decision(existing: dict | None, incoming: dict) -> Literal['apply','replay','stale']`放publication.py：比较metadata_revision，同revision还须payload_hash相同，否则抛ValueError；真正写库仍需CAS/行锁，不能仅靠这个纯函数处理并发。

- [ ] 先写真实PG用例：同key同payload重放、不同payload409；旧projection revision不能盖新revision；断网重试；lease过期旧worker不能发布；READY到发布之间归档或改metadata使CAS失败。
- [ ] 在backend专用PG执行新增test_knowledge_delivery.py确认RED；knowledge集成fixture强制database=shopsteward_knowledge_test，错误库名立即拒绝，不跳过成通过。
- [ ] 实现outbox与云jobs唯一键、短事务claim及lease检查。幂等冲突按operation+key+payload_hash判断；不可只按文件hash合并不同版本任务。

```python
from shopsteward_knowledge.publication import projection_decision

def test_delayed_archive_predecessor_cannot_restore_old_projection():
    existing = {"metadata_revision": 3, "payload_hash": "archived-v3"}
    delayed = {"metadata_revision": 2, "payload_hash": "active-v2"}
    assert projection_decision(existing, delayed) == "stale"
```

先以该测试和真实PG并发用例确认RED，再实现条件写入。publisher必须先提交claim事务，再进行HTTP，最后在新事务核对lease并ack；在HTTP完成/ack之前故意终止进程，重启验证远端收据重放且无重复generation。重试初始1秒指数退避，上限60秒、最多5次；429尊重有界Retry-After，4xx输入错误直接FAILED，手动retry新attempt继续原业务幂等键。

- [ ] 在K1追加版本/PATCH/归档/恢复事务中登记必要projection更新；修改metadata不必重新embedding相同文本。后端最终复核负责消除传播延迟期间的旧候选。
- [ ] SUCCEEDED前验证预期chunk数、manifest hash和search可见性；失败不发布空generation。旧generation不立即删除，至少保留到恢复演练完成；自动GC独立dry-run列出无人引用且超过宽限期的对象，再按明确ID清理。
- [ ] 运行PG事务、重启、乱序和版本选择测试；迁移前后检查原件不可变与K1幂等行为仍有效；同步导出backend与knowledge契约，新端点正确标K2，原K1端点phase不伪改。

## B4：候选取回、关系、模型接口

**Files:** 新建`knowledge/src/shopsteward_knowledge/retrieval/{__init__,search,opensearch,fusion,relations,scope}.py`、`providers/{__init__,embedding,rerank}.py`、`knowledge/tests/{test_fusion,test_provider_protocol}.py`、`knowledge/tests/integration/{test_search,test_relations}.py`；更新api.py接通search/evidence。

**Interfaces:** `rrf(lists: list[list[str]], *, c: int = 60) -> list[tuple[str,float]]`排名从1开始、重复ID一路只计一次、同分按ID稳定排序。`search(request: SearchRequest) -> SearchResponse`先scope再检索；`relation_paths(seeds: list[str], predicates: list[str], scope: SearchScope, *, max_depth: int = 3) -> list[dict]`基于PG条件边，只返回同scope证据。

- [ ] 加fusion RED与无匹配词法反例；包含store filter的should查询仍必须minimum_should_match=1。

```python
from shopsteward_knowledge.retrieval.fusion import rrf

def test_rrf_uses_one_based_ranks():
    scores = dict(rrf([["A", "B"], ["B"]], c=60))
    assert scores["A"] == 1 / 61
    assert scores["B"] == 1 / 62 + 1 / 61
```

- [ ] 运行新test_fusion.py确认RED后实现`Σ1/(60+rank)`，再用真实OpenSearch index验证CJK分词、无词匹配为空、scope空立即空、未来/历史/as_of版本条件；每次测试仅清自身随机索引。
- [ ] 使用httpx.MockTransport测试provider返回向量顺序、维度不符、NaN、超长、429、timeout、query/document instruction及缓存键。缓存键包括模型/profile、input_type、文本hash，不混用同维不同模型。人工4维向量只跑此协议检查，报告明确synthetic_protocol_only。
- [ ] 首个OpenSearch adapter同时实现profile对应的dense字段和带scope过滤的kNN写入/查询；用人工向量在真实索引验证最近邻、维度错误、同维不同profile隔离及“较近但不属于允许版本”的排除。后续接真实embedding即可复用这条路径，不能到首次上云才发现semantic分支仍是空实现。该检查证明DB协议，不证明语义效果。
- [ ] EmbeddingProfile保存provider/model/revision或服务时间、维度、instruction、归一化、截断/分块规则；未配置返回disabled，不暗中下载模型或切换其他项目密钥。实际可用端点用HTTP adapter接入，供应商差异由配置/适配层处理，不能假定所有API完全OpenAI兼容。
- [ ] 真实词法可以单独返回Candidate；dense不可用时degraded=true并说明。应用层RRF和可选重排使用同一授权候选，parent从manifest定位。token预算使用配置的生成模型tokenizer；未具备时报告估算方法和保守字符上限，不把字符数标成实测tokens。
- [ ] 关系用PG固定JOIN/有界递归同事实对照，检查方向、循环、例外、生效时间、未确认边；缺事实时只返回已知路径。业务实时关系由backend限定实体种子，不从旧云投影推断当前库存或活动状态。
- [ ] 以原K0及A2 dev问题运行真实词法与关系检查；保存candidate身份/定位/版本/分数/耗时。实体精确查询及纯数字业务请求的embedding调用数必须为0。此处真实dense/rerank若无账号仍留为未运行，C3分别展示可交付范围。

首个云试运行只需上述一个真实词法适配和可验证的embedding端口；pgvector/Qdrant实际adapter在模型/云实验任务按候选优先级追加，不能先做三套全功能服务再开始评测。
