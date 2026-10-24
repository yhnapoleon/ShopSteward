# K1 文档管理后端交付与验证

2026-09-07。范围依据[K0–K1执行计划](../superpowers/plans/2026-09-07-k0-k1-execution.md)。K0数据/技术结论见[基线报告](knowledge-baseline-report.md)；API字段、权限、存储约束和TDD记录见[模块说明](../../backend/app/knowledge/README.md)。

## 实现范围

实现9个操作、6条路径：创建文档并上传原件，按店铺/类别/SKU/供应商/标题分页，文档详情，PATCH元数据，追加不可变版本，版本列表/详情，鉴权下载原件，归档/恢复。独立[Knowledge OpenAPI](../api/knowledge-v1.openapi.json)与[完整backend runtime](../api/backend.runtime.openapi.json)从实际路由导出，原有路径/响应schema与HEAD比较保持一致；完整runtime为49操作/42路径。

所有POST/PATCH使用Idempotency-Key，重放前检查当前授权；PATCH/追加/控制以expected_metadata_version和行锁处理并发。创建/追加返回201，`ingestion_status=UPLOADED`、`indexing_status=NOT_INDEXED`。没有入队不可消费的索引任务；也没有把latest_version_id解释成生效或索引发布版本。

门店共享和private资料复用现有Bearer身份，service不能使用user接口。private正文/版本只有owner可读，admin沿用全店发现权限可读元数据但不能下载或解除他人的私有状态。归档保留记录，阻止版本/原件读取，恢复后重新可用。每次下载重新授权，原件不静态挂载，附件带nosniff及private/no-store。

上传使用20MiB流式上限、64KiB元数据和64KiB头部限制，正文IO/校验不持有Store锁。文件名只作为显示名称，保存为独占创建的随机key；SHA256与精确字节长度持久化。TXT/MD/CSV为严格UTF-8；PDF、Office经过有界基本结构验证。原件不解析为库存、价格、规则或其他正式业务数据。

新增`knowledge_documents`和`knowledge_versions`两表，版本号唯一、latest指针有同文档复合FK、原件版本由PG触发器禁止UPDATE/DELETE；现有command_receipts保存幂等结果。迁移`0010_knowledge`，正式ready检查新增表与迁移头。实体链接先用JSONB规范ID集合和GIN索引，不部署图数据库。

## 已执行的验收与审查

- 初版K1：40项（21 PG/ASGI、18存储、1OpenAPI）；TDD有原始404、PATCH回放409、坏ZIP异常逸出和游标越界失败记录。对应修复和命令见模块README。
- 独立真实TCP HTTP：22项通过，含原件字节校验、跨店/匿名拒绝、撤权、追加、归档/恢复、精确重放、API重启；文档动作没有新增business_events、ledger_entries、actions或虚假JobRun。见[HTTP机器证据](../api/knowledge-k1-http-result.json)。仅启动并最终停止自身8016 API，没有worker。
- 首轮全模块回归的启动配置失误：跨backend/agent目录收集时pytest选中根配置，丢失asyncio auto，187 failed/79 passed；固定runner显式`-c backend/pyproject.toml`后消除。随后旧API清单因新增6条K1路径失败，按精确新清单与K1 phase更新，并未弱化为“包含即可”。
- 上述修正后的全量backend/Agent为265 passed、1 skipped（未提供TEST_SIM_DATABASE_URL）；simulator独立23 passed。最终设置专用sim测试库后补全回归，结果在下方最终验证记录中保存。
- 独立只读审查确认两个格式边界问题：整文件搜索`/Encrypt`误拒正常PDF；伪PDF/无关系与命名空间的Office包被误接受。修复要求：真实PDF结构与加密判断、Office基础关系/类型/namespace校验，以及有效原件正例和对应负例；最终回归后关闭审查项。

### 最终验证记录

1. 上述PDF/Office问题修复后，backend＋Agent＋跨服务PG全套 **302 passed / 0 skipped，119.27秒**；真实simulator测试库已通过runner显式配置。
2. 复审确认原两项已闭环，另发现合法chartsheet工作簿被误拒。以openpyxl实际生成并重新打开的固定工作簿作为回归输入，新增正/负例先得到 **1 failed / 1 passed**。修正为按worksheet/chartsheet/dialogsheet实际关系类型校验；只有worksheet要求sheetData。
3. 图表页修复后，最终知识模块 **78 passed / 0 skipped，20.11秒**（56存储、1契约、21真实PG/ASGI）。测试常量整理后图表页2项再次通过；没有把这次局部运行冒称为重新运行304项全套。
4. 最终代码的真实HTTP与API重启 **22/22通过**，机器证据已更新；simulator **23 passed，6.04秒**。K0上游契约/切块26项、核心60问、关系12问及900项语料校验分别见K0报告，不混入K1业务测试分母。
5. Alembic check无漂移；Ruff check和**164个Python文件**格式检查通过；uv锁定88包，当前环境83包依赖兼容。runtime与K1 OpenAPI验证、原有路径/schema不变检查、原业务设计契约和前端只读契约检查通过。汇总见[最终验证JSON](../api/knowledge-k0-k1-verification-result.json)。

新增生产依赖仅`python-multipart`与`pypdf`。图表页来源与标准说明见[固定回归原件](../../backend/tests/fixtures/knowledge/README.md)。所有审查修复针对实际反例；格式验证仍不包含渲染、OCR和完整OOXML schema。

最终独立复审确认三项P2均已闭环：合法chartsheet可读回、原件校验通过，单独篡改其MIME返回422；聚焦修复范围未发现新的重要问题。交接中新加的本地链接、最终源文件hash和导出契约均已核对。

## 当前使用与阶段边界

K1代码/测试库已具备文档管理能力；**现有开发库与8000服务没有自动切换**。使用新API前，需要在合适维护时机备份开发库/原件目录、迁移到0010并重启相应backend进程。此处是后续操作说明，本轮没有执行开发迁移或重启；8000、8001原服务健康读取为200。

原件目录默认相对API工作目录的`var/knowledge`，正式运行建议配置绝对持久目录`KNOWLEDGE_STORAGE_ROOT`并与PG一起备份。解析失败不应影响原件管理。数据库与文件系统不共享事务，事务失败或重放可能留下无引用原件；当前没有自动GC，需要后续按已提交raw_key及文件年龄安全回收。

K2待做真实解析/OCR状态、稳定页/章节/单元格定位、索引任务与原子generation发布、关键词检索和重建；K3待实测embedding/向量库/融合重排；K4待Agent取用与引用；K5待前端文档中心。K1没有宣称RAG问答、图谱推理、模型效果或文档批量UI已经完成。

## 复现

仓库根目录，使用本仓`.venv`和已由用户启动的PostgreSQL；以下runner强制专用测试库，不输出凭据：

```powershell
.venv/Scripts/python.exe backend/tests/integration/test_knowledge_runner.py migrate
.venv/Scripts/python.exe backend/tests/integration/test_knowledge_runner.py --with-simulator-db tests ../agent/tests -q --tb=short
.venv/Scripts/python.exe backend/tests/integration/test_knowledge_runner.py schema-check
.venv/Scripts/python.exe backend/tools/export_knowledge_contract.py
.venv/Scripts/python.exe backend/tools/verify_knowledge_http.py
```

`--with-simulator-db`仅在全量跨服务验证时读取simulation自身配置并改为`shopsteward_sim_test`；不迁移simulator开发库。共享backend测试库用例串行执行。HTTP验收要求8016空闲，原件和日志保存到`var/knowledge-http-*`，原件与测试数据保留供检查。
