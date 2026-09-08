# 上云准备C：Agent集成与搬迁演练 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 证明本地Agent能使用独立知识服务的证据，并可在干净环境按同一构建物恢复这套链路。

**Architecture:** Agent调用现有backend只读工具，由backend签发检索范围、事务外调用Knowledge API并批量复核。用独立本地Compose项目模拟远端服务；业务原件及权威PG、派生服务PG及索引分别导出/恢复。

**Tech Stack:** 现有Agent框架/工具租约、httpx、独立knowledge服务、Docker Compose与标准PG备份/恢复工具；不用新增聊天框架或全功能前端。

**Spec:** [云端与语料设计](../specs/2026-09-07-cloud-knowledge-and-corpus-design.md)、[主计划](2026-09-07-knowledge-precloud.md)、[服务接口及生命周期](2026-09-07-knowledge-precloud-service.md)。

## Global Constraints

完整继承主计划Global Constraints。真实进程测试只启动并停止自身创建的进程；本地端口建议8018/8020，绑定127.0.0.1，启动前检测冲突但不结束占用进程。Compose使用独立项目shopsteward-knowledge-precloud，不更改现有infra/compose.yaml。

## C1：只读Agent证据闭环与200份导入

**Files:** 新建`backend/app/agent_bridge/document_evidence.py`、`backend/tools/import_knowledge_corpus.py`、`backend/tests/integration/test_agent_document_evidence.py`；修改`backend/app/agent_bridge/tools.py`、`composition.py`、`backend/app/core/config.py`、`backend/pyproject.toml`及契约导出。必要时更新`agent/tests/test_adapters.py`，不重写Agent图或个人memory模块。

**Interfaces:**

- Agent工具`search_documents(query: str, limit: int = 6, entity_ids: list[str] | None = None)`与`read_document_evidence(chunk_ids: list[str])`，单次最多20块；参数不接受调用方自选principal/store或宽权限集合。
- `retrieve_document_evidence(settings, principal_id: str, store_id: str, query: str, *, request_id: str, deadline_ms: int = 8000) -> dict`：自己开短事务读scope→HTTP→短事务复核，调用者不得传入持有写事务的session。
- `filter_current_candidates(candidates: list[dict], current: dict[str,dict]) -> list[dict]`：current以version_id映射有效generation_id、metadata_revision及visible；不匹配的结果剔除且响应标stale/degraded，不重新放宽范围补k。
- CLI `import_knowledge_corpus.py --manifest <path> --target-test --dry-run`验证路径/hash/映射不写入；去掉dry-run后通过K1 API逐份上传、提交index-jobs、等待READY并显式发布。输出fixture→实际document/version/SKU/Supplier映射、请求收据及失败列表。

- [ ] 为晚到旧metadata候选写RED，以及private正文、归档、无证据、搜索超时、证据文本注入与业务金额取用用例。

```python
from app.agent_bridge.document_evidence import filter_current_candidates

def test_metadata_change_while_search_is_in_flight_drops_stale_hit():
    candidates = [{"version_id": "V1", "generation_id": "G1",
                   "metadata_revision": 2, "text": "旧条款"}]
    current = {"V1": {"generation_id": "G1", "metadata_revision": 3,
                       "visible": True}}
    assert filter_current_candidates(candidates, current) == []
```

- [ ] 用现有runner执行新增测试并确认RED：

```powershell
& ./.venv/Scripts/python.exe backend/tests/integration/test_knowledge_runner.py tests/integration/test_agent_document_evidence.py -q
```

- [ ] 实现工具注册与只读分支。先检查execute_tool及外层事务范围，将新远程读取分支放在事务外；不要为了复用现有函数签名把网络放进session.begin。保持原业务写工具及lease fence，远程返回后核对当前run仍可用，超时/失租约不能保存成功结果。
- [ ] 新增开关KNOWLEDGE_SERVICE_ENABLED、URL、service key配置、HTTP timeout；未启用时不注册文档工具，不返回伪造空成功。文本不带执行权，候选中的“忽略规则/发起采购”不能创建任何business Action。
- [ ] 以A2 manifest dry-run检查200份hash/合法metadata；建立专用模拟租户，业务实体seed仅在强制测试库下运行，随后原件/索引/发布全走真实API。每文件幂等key来自语料版本+fixture version，不以标题判重；中途失败重跑可续传。
- [ ] 用真实HTTP分别展示条款问答证据、近似SKU排除、版本切换、无答案、库存问题走业务工具；模型未配置时用脚本化工具调用验协议，报告“Agent工具闭环通过，真实生成未运行”，不把脚本答案冒充LLM回答。
- [ ] 原Agent记忆/补货工具及租约相关回归通过；导出runtime契约和工具目录，新增工具引用到准确原件版本。

## C2：构建、配置、导出和恢复

**Files:** 新建`knowledge/Dockerfile`、根`.dockerignore`、`infra/compose.knowledge.yaml`、`knowledge/.env.example`、`infra/knowledge_local.py`、`backend/tools/export_knowledge_bundle.py`、`knowledge/tools/restore_bundle.py`、`knowledge/tests/test_bundle.py`、`docs/runbooks/knowledge-local-and-cloud.md`。

**构建约定:** 根目录为build context，uv锁文件安装knowledge的service/parsers/opensearch extras；镜像入口可选API或worker，非root用户，挂载原件/解析产物数据卷。构建上下文排除.env、var、.venv、IH、评测gold与无关原件。API依赖DB/schema的ready，迁移以单独显式命令执行，API/worker不会各自争抢自动迁移。

**本地服务:** Knowledge API建议127.0.0.1:8020；独立PG建议55434；词法索引建议19201。每端口启动前检测空闲；默认只启用本任务服务，不启动第二个业务backend/worker。只有知识服务需要打包，Agent继续本地运行。

**Interfaces:**

- `verify_bundle(root: Path) -> dict`验证bundle-manifest.json列出的相对路径/sha256/大小，返回files_verified、bytes_verified；错误抛ValueError。
- bundle包含原件、解析产物、profile清单、publications/relations的导出快照及两个数据库的迁移revision；业务权威备份与服务派生备份分组。原件storage_key与DB引用对应，不能只备份VectorDB。
- export CLI `--target-test --output <empty-task-dir>`从专用测试库导出；不复制.env。restore CLI `--bundle <dir> --target-test --verify-only`只校验；实际恢复仅接受独立空目标，不覆盖源库/现有卷。

- [ ] 加bundle校验RED；临时fixture完全由本测试创建。

```python
import json
import pytest
from shopsteward_knowledge.bundle import verify_bundle

def test_restore_rejects_missing_original(tmp_path):
    (tmp_path / "bundle-manifest.json").write_text(json.dumps({
        "files": [{"path": "originals/missing.raw", "sha256": "0" * 64, "size": 1}]
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="missing"):
        verify_bundle(tmp_path)
```

`verify_bundle`实现文件为`knowledge/src/shopsteward_knowledge/bundle.py`，与restore CLI共享；补充篡改hash、绝对路径/..越界、数据revision不兼容与实体映射缺失测试。

- [ ] 执行knowledge/tests/test_bundle.py先RED后实现，确保校验先于任何恢复写入；输出只含目标名称/计数/hash，不含PG连接密码。
- [ ] 本地配置模板列URL、storage root、启用profile、embedding端点/模型/维度、成本计数器开关；不填写真实key。保留query/document profile明确区分，无key可运行词法模式。
- [ ] `knowledge_local.py`增加check/build/start/status/stop命令，记录项目名和自己启动的进程ID；Docker未运行时明确说明并退出，不调用Start-Process启动Desktop。Windows后台辅助进程隐藏窗口。
- [ ] 容器版本实施时按官方文档验证并锁digest；本计划不提供未经当前兼容验证的最新版号。build完成后记录镜像digest与lock hash。
- [ ] 导出前暂停本任务publisher/ingestion写入并等在途任务结束，取得一致快照再拷贝原件；不暂停原业务服务。无法暂停时需要一致性watermark方案，此首版不以两个不同时刻的dump冒充一致备份。
- [ ] 新建独立restore Compose项目及空卷，恢复原件/PG，再从原件重建索引或恢复兼容快照；比较文件hash、发布指针、关系与若干固定查询结果。profile不兼容时强制新generation重建，不原地覆盖旧向量空间。
- [ ] 写运行手册：check→迁移→start→导入→验证→stop，及改URL/服务凭据/存储配置迁至云端的对应项。显示当前配置的作用域与目标，但不输出凭据值。

## C3：本地搬迁验收与云实验输入包

**Files:** 新建`backend/tools/verify_knowledge_precloud.py`、`knowledge/tools/benchmark.py`、`docs/reports/knowledge-precloud-readiness.md`、`docs/api/knowledge-precloud-verification.json`、`docs/evaluation/knowledge-expanded/cloud-experiment.json`。

**Interfaces:** `verify_knowledge_precloud.py --target-test --manifest <path> --output <path>`跑真实HTTP/进程场景并返回非零退出码表示必需场景失败。`benchmark.py --manifest <path> --queries <dev-path> --concurrency 1,5,10 --mode lexical`只测实际启用路径；输出逐查询阶段耗时、错误、profile、input hashes及环境标签loopback/local。

- [ ] 先加入验收报告判定RED：必需项缺失或未执行不能总体通过。

```python
from shopsteward_knowledge.readiness import ready_for_cloud_pilot

def test_protocol_success_cannot_replace_real_http_and_restore():
    checks = {"corpus_200": "passed", "real_http": "not_run",
              "restore": "passed", "versioning": "passed",
              "agent_tools": "passed", "build": "passed"}
    assert ready_for_cloud_pilot(checks) is False
```

`ready_for_cloud_pilot(checks: dict[str,str]) -> bool`放`knowledge/src/shopsteward_knowledge/readiness.py`；必需键固定为以上六项且都为passed。另设cloud_model_quality/cloud_latency/cloud_cost字段，处于not_run不冒充通过，也不阻塞本地pilot_ready；MVP_ready须A3和云实际效果验收，两个状态分开。

- [ ] 运行knowledge/tests/test_readiness.py确认RED，按固定必需键实现判定后复测；再编写真进程验收脚本，不能在健康/检索/重启步骤用mock替代。
- [ ] 必需场景：200份正常导入与断点续传；无匹配为空；跨门店/未来版本过滤；归档传播延迟的最终复核；发布失败旧版继续；worker失租约/重启；API超时降级；关系条件反例；原件/引用校验；独立空环境恢复；业务事件/金额/个人记忆没有被文档工具修改。
- [ ] 性能分query与ingest，记录实际文档/块/token或估算说明、解析覆盖、峰值RAM/CPU/磁盘、索引首建/增量、并发1/5/10、各阶段p50/p95和超时分母。不以完成一次请求声称SLA。
- [ ] 生成云实验配置：最多两个可用区域/端点；相同200份与dev题；模型最多两种；实际预算/单价在账户配置时填写，未填写则billable_run_enabled=false。不在JSON里写key、不默认无限重试。
- [ ] 根据本地峰值资源给出初始云CPU/RAM/磁盘范围及余量依据，列出模型远程耗时未知；云购买前不把估算写成必需规格。模型/存储对照复用向量缓存，不重复多次计费建同一语料。
- [ ] 完成相关backend/Agent/knowledge回归、迁移漂移、runtime契约及依赖锁校验；最终报告列准确命令、批次/分母、hash、未测项、仍存在的缺陷和pilot_ready/MVP_ready。

本地准备完成时，应能交付一份能在另一台机器复现的运行包和报告。完整文档UI、飞书自动同步、Neo4j、GPU模型托管、自动OCR和全球部署均不作为这份验收的必需条件。
