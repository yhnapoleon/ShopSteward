# ShopSteward 当前开发交接

### 最新实施检查点：本地预测首轮实验与服务（2026-09-08）

**先读[首轮实验与研究分析报告](../ShopSteward-forecast/docs/reports/forecast-experiment-analysis.md)。** 已完成真实数据准备、训练、冻结测试与本地推理服务；当前不是“尚未开始训练”。实现代码位于独立工作树 `ShopSteward-forecast`，分支 `codex/b1-local-forecast`，本次文档整理前代码 HEAD 为 `c160644`。原 `ShopSteward` 的 YH 开发代码和服务没有合并/切换到该版本；在原目录阅读时，请进入同级 `../ShopSteward-forecast` 继续实现或运行命令。

#### 模型与结果

- M5 官方原件已获取并记录来源/hash；固定 500 条门店商品序列、970,500 行、1941 天。用历史销量与日历构造 33 个特征，将未来 1–7 天观测销量作为直接多步回归目标；不预测采购量，不声称恢复缺货后的真实需求。
- 4 配置 × 8 外层窗口、64 次拟合完成；选择 **LightGBM Poisson / 31 leaves / 188 rounds**。搜索约42.5分钟；最终模型只训练至2016-03-27，测试2016-03-28至05-22，期间不更新参数。
- 正式七天累计 MAE：mean28 **3.57275**，模型 **3.41619**，改善 **4.382%**；95%配对时间块改善区间 **[0.457%, 7.852%]**。唯一未通过门槛是改善不足5%，因此 **candidate，offline_model_validated=false**，不能把候选模型经普通配置切到active。
- 日MAE改善4.627%、日RMSE改善8.325%；但销量加权累计MAE恶化8.292%，业务取整后累计改善只有2.970%。8周中2周恶化；h5始终对应周五，距离和星期混杂。详细切片、关键大销量序列、原因假设和研究优先级见分析报告。
- 模型 `m5-lgbm-direct7-004bc1ba9223756a04b1`；模型文件SHA `965708ba9757dbc2751200be361598e1b87e44a6951cb29cca3a6fcc595cc580`。服务制品包SHA `300f2fc3057baf1b684f6dee761b5ee0686c62e32c3d8f9c640d4742b47ba033`。统计对照版本 `m5-baseline-mean28-2518321ecc3552d67f9e` 明确标记baseline/candidate。

补充数值口径：离线原取整辅助指标改善2.970%；按在线有序float64累加重算为2.943%（基线52/4000窗口取整不同，模型无差异）。不影响未取整主指标4.382%与candidate结论；后续经营评估须统一口径，旧正式摘要保持不变。

#### 实施进度与验证

| 工作项 | 状态与证据 |
|---|---|
| A1–A5 数据/特征/基线/训练/冻结评测 | 完成并通过审查。A5元数据两轮修复后复审通过，正式模型和测试结论未变 |
| A6 HTTP服务 | `ad0a5d8`，完成并独立审查通过。Bearer、版本/hash、56–365日完整历史、自然日/DST、1MiB/并发边界和原生加载已实现 |
| B1 绑定/观察历史/不可变预测明细 | `e5fd244` + `9645faa`，完成并通过审查，迁移 `forecast_b1_0012` |
| B2 独立预测worker/队列/原子发布 | `c160644`，实现与本地验证完成，**独立审查待完成**，迁移 `forecast_b2_0013` |
| B3/B4 生命周期/业务API与配置 | 待实施；公开active资格校验属于B4，不因已有内部active发布分支而视为完成 |
| B5/B6 REPLAY/经营评估 | B6纯指标校验helper已完成；隐藏需求回放、真实270场景与故障验收待完成 |
| C1–C5 前端/LangGraph/全栈恢复 | 本次预测能力仍待接入与验收；既有Agent/业务功能独立保留 |

ML最终 **151 passed**，包含真实100起点训练/推理特征一致性；A6复审另跑28项通过（与151有交集，不累加）。Ruff、涉及文件格式、契约、wheel构建通过；旧Forecast schema、9个非ML路由与SC01初始化样例保持兼容。额外全ML格式扫描有4个既有文件格式差异，未做无关改动。

真实HTTP在100次预热后，分别采样100次，并发1/4的p95为 **95.9/381.3ms**，重启后同请求预测ID/原始曲线/总量一致；验收自有8052进程已停止。首次四并发1.265s不达标，后通过一次构造多日特征改善，预测值不变。见[服务验收](../ShopSteward-forecast/docs/reports/forecast-service.md)和[启动说明](../ShopSteward-forecast/ml/README.md)。

B2单元/API **51 passed**，专用PG相关回归 **78 passed, 1 deselected**，迁移head/check、bigint和部分唯一索引验证通过。排除项为全库历史Plan哈希断言：持久测试fixture累积后521条中117可重建、404不匹配。B1此前48/48语料验证不能替代B2的本次排除项；后续需独立审查并用干净隔离库重做非空历史兼容性验收，不应写成全回归通过。

#### 环境与接续顺序

- 独立测试PG：`shopsteward-forecast-test-20260908`，`127.0.0.1:55435`。`shopsteward_test` 已到 `forecast_b2_0013`，`shopsteward_sim_test` 保持既有模拟器head。另备有forecast acceptance专用双库，其backend仍按准备时0011，后续须核对并迁移；不要混用会清理fixture的测试库与acceptance库。
- 本机私有环境为 `var/forecast/test.private.env` 与 `var/forecast/acceptance.private.env`；模型在 `var/forecast/artifacts/`，完整预测与原件也在忽略目录。不要提交令牌、原件、模型或未来日销量到Git/业务接口。原开发PG55432、8000/8001和知识容器本轮未切换。
- 接续先读分析报告及B2实现报告，完成B2独立审查/洁净Plan验收，再按总计划推进B3→B4→B5/B6→C1–C5；不重复A1下载、正式搜索或最终测试。新模型研究须另建版本与预注册测试协议，不能继续在已查看测试集上选参后宣称独立通过。
- 质量不足不阻断受控shadow技术联调；模型与统计基线当前均candidate，普通active路径不能绕过门槛。如何在保留资格约束下完成候选模型的隔离经营对照仍需在B5/B6明确记录，不能伪造validated状态。
- 总状态：数据/制品可用，ML服务验收完成；`offline_model_validated=false`、`backend_ready=false`、`replay_ready=false`、`agent_ready=false`、`b1_ready=false`。知识检索的pilot/MVP标志是另一个工作包，未因预测实验改变。

完整设计与分工：[设计](../ShopSteward-forecast/docs/superpowers/specs/2026-09-08-local-forecast-design.md)、[总计划](../ShopSteward-forecast/docs/superpowers/plans/2026-09-08-local-forecast.md)、[A模型](../ShopSteward-forecast/docs/superpowers/plans/2026-09-08-local-forecast-model.md)、[B后端](../ShopSteward-forecast/docs/superpowers/plans/2026-09-08-local-forecast-backend.md)、[C产品/Agent](../ShopSteward-forecast/docs/superpowers/plans/2026-09-08-local-forecast-product.md)。原计划的未勾选框不能覆盖本节实际执行状态。完整本机任务报告/复审在 `.superpowers/sdd/2026-09-08-local-forecast/`，正式可传递的摘要在docs。

以下保留其他工作包的历史交接，其中旧“真实预测未实现”“最新head”等描述按记录日期理解，当前预测进度以上述检查点为准。

**首要交接入口：[Knowledge服务器部署完整手册](docs/runbooks/knowledge-server-handoff.md)。** 已按用户要求整合为单文档14个主题章节，覆盖部署/完整配置/启动/跨机网络/backend与LangGraph接入/语料与关系/验收/备份恢复/排障/选型/回填模板，无需先阅读其他子文档；源码及原始报告在末尾作为参考。当前可开展环境准备和隔离试部署，完整搬迁验收仍待补。

### 最新Git与文档交付（2026-09-08）

- 已本地提交、推送YH并创建 [PR #10](https://github.com/yhnapoleon/ShopSteward/pull/10)（YH → main，更新时OPEN、未合并）。功能 `96ee2a0`；同步main `2406371`，保留同学前端经营概览/文档中心，唯一HANDOVER冲突已保留双方记录；单文档手册 `e65e066`。
- 本次完善仅同步PROJECT_CONTEXT/HANDOVER。无关的 `docs/proposals/` 聊天体验提案仍留在本地，不随本轮交接提交；私有env、DB/卷、var内映射/发布收据不经Git传输。
- 完整手册已通过14个目录跳转、引用路径、10个脚本路径及9组CLI示例参数检查；Compose静态配置通过，pilot200离线校验通过且business_writes=0；独立源码审查未发现新的操作阻塞。Linux/云端部署命令尚未在目标主机执行。
- 提交前backend unit/API含语料254 passed，knowledge323 passed/15 skipped，Agent30 passed/3 skipped；同步main后backend非重语料216 passed。各批次有交集，不累加；前端契约通过，附加typecheck因本机缺少ECharts依赖未通过，已在PR记录。扩展语料已设Git字节保留，1657文件暂存字节及pilot200/full1124原件大小/hash核验通过。

### 接续必须注意的限制

- **先做服务器试部署与跨机接入，仍保留pilot_ready=false、MVP_ready=false。** 服务器负责Knowledge API/worker/PG/OpenSearch及持久存储；现有业务backend/DB/原件发布权威和Agent保持原职责，Agent通过backend获取候选。
- 普通导入可经本地8018 backend访问18020云API隧道；关系导入、benchmark、C3 verifier和自动Agent脚本固定8018/8020。必须确认8020实际指向目标服务器，避免误测本机旧服务；具体隔离端口步骤见完整手册第6、8、9节。
- **恢复已知阻塞：** bundle当前仅接受public应用schema，直接导出含 `agent_data` / `agent_checkpoints` 的当前Agent库会被拒绝。需补完整schema枚举/锁定/导出/恢复校验并真实演练，不能删除schema或保护检查来绕过。新服务器正常重新入库与搬迁旧双库是不同流程，见第10节。
- 当前导入CLI默认lexical-v1且无profile参数；启用embedding后仍需显式hybrid index-job、新generation与正常发布，再切读取profile。数据库/embedding/区域继续按固定输入实测，不把已实现适配或4项路由通过当作选型/质量结论。
- 后续共同完成真实关系导入、归档/换版/租约/重启、空目标恢复、并发与质量评测；公开资料还缺76份并待人工审阅。后续若更改源码或配置，同步完整手册。下方旧阶段的未提交/未实现/进程描述按历史记录理解。

### 最新执行检查点：知识检索本地准备（2026-09-08）

- 本地准备已进入实施，独立knowledge包、K2投递/发布、Agent证据工具、迁移、容器/恢复/基准工具已落盘；实施起点HEAD `602a6c6`，功能提交 `96ee2a0` 已在YH创建，开发8000/8001及开发库未改动。详情见[验收状态](docs/reports/knowledge-precloud-readiness.md)。
- 实际语料pilot200、全量924逻辑文档/1124版本、300题；公开来源24份，目标100份仍缺76份。CSV等宽修复后实际解析1124全部COMPLETE，共16205块；800条合成关系通过唯一原文chunk绑定。dev-only查询单独导出，gold不进入检索输入。原K0/旧K1契约hash保持不变。
- 文档编辑CAS `metadata_version` 与证据修订 `evidence_revision` 分离；追加原件保留旧发布，权限/实体等元数据变更须重新索引发布。失败任务使用新generation，只有READY完整证据可发布；未来/有界发布保留旧版其余有效区间。
- Docker已由用户启动；独立knowledge API8020/PG55434/OpenSearch19201已实际构建、迁移并就绪，镜像digest已记录。业务测试库0011、knowledge库knowledge_0002已验收；投递35+证据30混合测试通过（25项实际PG、40项非PG）。pilot200已完成真实上传、索引和发布。
- **Agent接入现有LangGraph完成本轮4场景联调**：库存查询→业务工具；文档查询→搜索并主动补搜；提前排队的引用追问→展开；混合问题→先库存后文档。r5取到映射/生效批次/双码追踪原文。完整结构化引用可持久化，最终权限/关系来源再次复核。正文标识抄错另经确定性校验回放修复，未伪称新模型运行。见[接入图、代码与实际轨迹](docs/reports/agent-document-langgraph-integration.md)。
- **整体pilot_ready=false、MVP_ready=false。** 还需真实关系导入、生命周期/重启、空环境双库恢复、并发基准及质量评测。embedding/rerank本轮关闭，现有Luna有界生成调用已实际使用，云检索选型/区域尚未决选。
- 接续保留knowledge容器；验收8018/API/publisher/Agent自建进程已关闭。测试租户 `knowledge-test-agent-0908020841-STORE01` 和 `var/precloud/agent-0908020841` 收据可复用；避免先运行会清理该测试库的integration fixtures。后续按[运行手册](docs/runbooks/knowledge-local-and-cloud.md)导入关系并恢复演练，扩采76份公开来源与人工评测继续。

### 最新计划：上云前本地准备（2026-09-07）

- 用户要求制定本地准备计划；已交付[总计划与L0现场检查](docs/superpowers/plans/2026-09-07-knowledge-precloud.md)、[A语料与评测](docs/superpowers/plans/2026-09-07-knowledge-precloud-data.md)、[B独立检索服务](docs/superpowers/plans/2026-09-07-knowledge-precloud-service.md)、[C集成与恢复演练](docs/superpowers/plans/2026-09-07-knowledge-precloud-readiness.md)。本次仅计划落盘。
- 下一执行顺序L0→A1/B1并行→A2/B2/B3/B4→C1/C2→C3。首个云pilot需200份真实原件和完整本地链路；A3的1000份/300题可继续并行，不阻塞首个云试验。无模型时验真实词法，协议模拟不计模型效果。独立knowledge包/DB/迁移与backend权威数据分开，个人memory不改作RAG。
- 计划包含新增来源metadata、outbox、索引状态/发布指针迁移；实施时按实际head生成新迁移，不能仅修改0010固定NOT_INDEXED约束的响应而漏DB变更。开发服务、数据库与云资源本次均未操作。

## 文档中心前端接入（2026-09-08）

接入既有K1接口：文档中心提供上传、标题/分类/状态/实体筛选、资料编辑、版本分页、原件下载、归档恢复、权限状态和原提交恢复。入口在“资料与简报”，直达 `/?view=documents`；不解析、索引或调用Agent。

基于相同文件树的main合并提交4944104复核，类型/构建/契约/格式通过；最终24项联合验收通过：文档受控10项、真实隔离API/PG与浏览器2项、原经营概览12项。首次/重试上传在校验文件期间切场景时，不再发出旧页面写入。真实验收前后经营state相等，开发库与既有业务未写入。后端、Agent、算法、模拟器、infra和依赖未改；AppDialog仅修正每实例标题ID。详见[验收记录](docs/reports/frontend-documents-verification.md)。保留本机3000；临时3013/8018在验收后停止。

### 最新修复：模拟器驱动当前环境（2026-09-07）

console 默认联动创建；成功导入后 backend 返回持久的当前场景，已打开前端每2.5秒自动跟随，资金/库存/事件和新任务 Agent 均使用该场景。保留历史数据，修复跨场景审批、分页及 Agent 异步响应污染。用户原 SANDBOX 已在实际前端显示现金1000、库存20，未改变其数据。

最终隔离浏览器5项通过（含官方 Luna）；backend相关23项、查询/契约11项、console异步3项通过；类型/构建/契约/Ruff通过。隔离服务已关闭，3000/8000/8001与原worker继续运行；最终API根PID39108，操作前核对。无迁移或提交。行为、复现及证据见[环境同步验收](docs/reports/environment-sync-test-report.md)。此前“完整联调”未覆盖外部创建自动切场景的缺口已在本轮补齐。

### 最新现场：Windows 全栈运行与官方 Luna E2E（2026-09-07）

最终补充：监控接口已从实际配置返回 Agent 启用状态（修复旧硬编码false）；队列/监控/API **33项追加回归通过**，在线 session 与 monitoring 均为 true。

- **已拉起**：前端 http://127.0.0.1:3000 、新版 API 8000、simulator 8001、business worker 与 Agent worker。官方模型 `gpt-5.6-luna`，`AGENT_API_MODE=responses`，并发1；用户指定密钥文件仅在私有配置中引用。
- **已迁移**：开发 PG 已从 `0009_agent_scopes` 升到 `0010_knowledge`，新版数量修订和K1知识接口已部署到8000。迁移前开发库备份为 `var/full-stack-20260907/before-knowledge-migration.sql`；原件路径未变。Docker Desktop一直由用户启动，本轮未启动/重启它。
- **验证**：backend+Agent 308通过、simulator23通过；业务浏览器8项、真实Luna3项、受控恢复1项分批通过。真实模型已覆盖解释、试算、修订后用户采购、澄清刷新恢复、偏好保存、取消与主动解读。类型/构建、Ruff、迁移漂移与契约通过。
- **重启**：API/业务worker/Agent worker/Nuxt/simulator全部重启后，4店铺与3会话完全一致；7个成功Run和1个取消Run、消息、偏好及精确账本均保留。SC01保持现金400/应收200/现货70/在途0/预留0。
- **进程**：最新记录 `var/windows-stack-20260907-133412/processes.json`，日志同目录。PID仅作定位，操作前核对身份。复现入口 `infra/start_windows.py`；脚本拒绝占用的3000/8000，不覆盖.env、不自动迁移、不终止未知进程。
- **Git**：`YH / b7db9a0` 加本轮未提交修改；未推送。前次交接中的 `6fb71fa` 和工作区状态已过时。
- **待办**：K2解析/索引、云端语料与模型存储实测、K3–K5、真实预测仍按原独立工作包推进。报价CSV仍是本地工具；少买后再次建议补足的后端语义未更改。本轮测试会话最后关闭主动解读，用户可按需开启；业务自动检查保持运行。

完整说明：[测试/启动报告](docs/reports/frontend-agent-fullstack-test-report.md)、[重启状态证据](docs/api/frontend-agent-restart-result.json)、[桌面截图](docs/reports/frontend-agent-desktop.png)。以下同日旧阶段的“当前”说明按其历史版本理解。

### 最新需求补充：云端知识检索（2026-09-07）

- 用户允许文本出云；要求助手寻找/合成有意义的大规模资料；偏好云端DB/知识关系与embedding、本地Agent读取带正文及元数据的候选。区域选择回答为“暂不限定，按实测选择”。
- 已落盘[云端与语料设计](docs/superpowers/specs/2026-09-07-cloud-knowledge-and-corpus-design.md)、[公开来源目录](docs/research/2026-09-07-knowledge-public-source-catalog.md)。1000逻辑文档、另约200版本和300题均为新增目标；首批目录10个来源家族，不等于原件已经入库。原K0数据/hash/评测不变。
- 后续云端query/document embedding均走可替换API；云PG关系/metadata投影与向量候选引擎同区部署，现有backend保留业务/权限/版本权威。本地Agent由backend取证据，无需本地embedding。关系模型不要求独立Neo4j。模型/DB/区域需要实测，尚未配置付费账号或预算、未部署。新方向不改变下述已完成K0/K1和运行现场。

### 当前交付：K0知识基线 + K1文档管理后端（2026-09-07）

- **K0已完成可运行无模型基线与选型设计**：40份合成原件版本（38逻辑文档）、60核心问、12关系问；20份RAilG候选源文件清单与SHA256。冻结语料900项校验通过。RAilG解析生成165块，扫描/混合PDF缺失已归档；实际复现bool.should无匹配仍返回、父块50条截断丢失hit两个迁移问题。
- **RAG数据边界**：条款、商品说明、SOP、活动要求、复盘用于文档取回；库存/现价/现金/订单/Plan/审批仍走现有backend与确定性计算。结构关联先PG JOIN/有界递归；C/D同事实12题路径结果相同，未证明需要独立图数据库。
- **embedding/vectorDB尚未最终选型**：BGE-M3、Qwen3-Embedding-0.6B/4B、OpenAI small/large及PG+pgvector/OpenSearch/Qdrant已完成官方资料比较与试验门槛。没有可用模型配置，真实dense/RRF/rerank、pgvector/Qdrant未实测；K1保持检索引擎独立。
- **K1已实现9操作/6路径**：原件上传/追加、元数据筛选分页、详情、版本、鉴权下载、PATCH、归档/恢复。上传201，UPLOADED/NOT_INDEXED，不登记空索引任务；所有写入幂等，变更CAS；private正文仅owner，admin可发现元数据但不能读他人正文。新增两张知识表、不可变版本触发器和同文档latest指针FK。
- **验证**：PDF/Office审查修复后全量backend/Agent/跨服务PG **302 passed、0 skipped**；随后chartsheet兼容修复的最终知识模块 **78 passed**；最终真实HTTP/重启 **22项通过**；simulator **23 passed**。Ruff、164文件格式、迁移漂移、依赖锁与契约通过。具体运行批次和局限见[测试报告](docs/reports/knowledge-k1-test-report.md)与[机器汇总](docs/api/knowledge-k0-k1-verification-result.json)，不将分批检查虚报为一次304项全量。
- **运行现场**：代码与专用测试库head为`0010_knowledge`；开发库只读确认仍是`0009_agent_scopes`。原8000/8001服务健康均200，未迁移或重启。8016验收API与本轮K0 OpenSearch已停止；后者容器保留供显式复测。Docker Desktop仍只由用户手动启动。**新文档API尚未部署到原8000进程。**
- **下一步K2**：修正RAilG两个已复现缺陷，接真实解析/索引worker、OCR_REQUIRED/PARTIAL状态、稳定引用定位、可回滚generation发布和关键词取回；之后K3才做模型/存储实测，K4接Agent，K5做文档中心。原件事务失败/重放可能产生孤儿文件，GC尚未实现。没有全文RAG、Agent文档工具或前端文档UI。
- Git起始/当前HEAD：`YH / 6fb71fa`；本轮修改在工作区，未提交/推送。下方Simulator/Agent记录为历史阶段，旧HEAD与“当前”表述按其日期理解。

入口：[本轮执行计划](docs/superpowers/plans/2026-09-07-k0-k1-execution.md)、[技术比较](docs/research/2026-09-07-knowledge-technology-options.md)、[K0报告](docs/reports/knowledge-baseline-report.md)、[语料说明](docs/evaluation/knowledge/README.md)、[K1 API/配置](backend/app/knowledge/README.md)、[Knowledge契约](docs/api/knowledge-v1.openapi.json)。

### 前端基础联调版（2026-09-07）

已按v0.3原型实现Nuxt三视图、真实状态/方案/确认/回执、暂停恢复、事件推进、警报与账本、Agent会话协议和本地报价工具。前端不维护模拟业务账本。仅新增一处普通用户revision接口，复用原Agent规划逻辑，无算法/资金/审批规则变更、无迁移；缺少此接口时有兼容降级。真实模型仍关闭，报价后端与少买后的再建议语义留给后端同学继续确认。

接入与边界：[frontend/README.md](frontend/README.md)。验证：[前端联调记录](docs/reports/frontend-integration-verification.json)、[实际业务终态](docs/reports/frontend-business-state.json)。本版本包含此前Mac环境适配；提交与合并状态以Git及对应PR为准。下方旧进度按其日期理解。

### macOS本机开发适配与复现（2026-09-07）

新增[macOS开发入口](docs/local-macos-development.md)与[实测记录](docs/reports/macos-development-verification.json)：依赖、四个开发/测试数据库、API/业务worker/simulator与Nuxt骨架已在Apple Silicon验证。后端+Agent 226项、模拟器12项测试通过，SC01和服务/数据库重启复核通过。修复SQLAlchemy asyncio依赖及Agent非Windows测试循环工厂，新增本机服务脚本和前端锁文件。基准为 `9382779` 加这些未提交改动，未推送或合并；未调用真实模型，前端仍为框架页面。以下Windows现场与早期状态保留其原适用范围，不能当作这台Mac的当前进程信息。

### 当前交付：持久 Simulator + Dashboard（2026-09-07）

- **Docker Desktop 由用户手动启动。** 助手只检查和使用已经运行的 Docker，不自行启动。
- Dashboard：<http://127.0.0.1:8001/console/>。可配置初始现金/库存/需求/采购条件，支持独立模拟与后端联动创建；销售、需求修订、部分/全部到货均落入 simulator 数据库与源事件流。SC01 固定剧本仍可用。
- 后端联动创建只导入店铺；Mission 创建与 Plan 审批仍使用 backend 原 API。页面观察 Mission、Plan 推荐量、警报与已同步源序号。已保留验收场景及对应 Mission/Plan，可直接打开演示。
- 实际开发迁移：simulator `sim_0003_controls`，backend `0009_agent_scopes`。原 8 个 simulator run 保留；验收另建场景，没有清库。Agent 关闭，没有模型调用。backend API 8000、simulator 8001、business worker 均已启动。
- 当前启动记录：backend API/worker 在 `var/simulator-console-20260907-095640/`；重启后的 simulator 在 `var/simulator-console-20260907-100657/`。PID 只用于定位，后续操作先核对进程归属，避免重复 worker。
- 启动：仓库根目录 `.venv/Scripts/python.exe simulation/tools/start_console.py --migrate --with-backend`；backend 已运行时省略 `--with-backend`。日志隐藏后台保存，不覆盖 `.env`，凭据仅服务器持有。
- 自动验证：simulator 23 passed（4.81 秒）、backend＋Agent 226 passed（80.82 秒），无失败或跳过。真实 HTTP 验收 13 项、重启持久/幂等 3 项通过；浏览器创建、销售、需求修订、部分/全部到货及刷新持久化已验证；Node UI 异步回归 3 项通过。详情见 [测试报告](docs/reports/simulator-console-test-report.md) 和 [机器证据](docs/api/simulator-console-acceptance-result.json)。
- 独立审查已复核事务、幂等、来源权限和本地 HTTP 边界；当前阶段没有 RAG、真实数据集、退款回款、随机流量或故障注入。下一步优先将产品前端与 Agent 接到同一组场景进行业务验收，再决定数据集回放/RAG。
- Git 基准 `YH / 4389747`（Agent Skelon），本次实现未提交/推送；产品 `frontend/` 未修改。旧文段的端口、迁移和未提交说明保留各自历史适用范围。

资料：[运行与操作说明](simulation/README.md)、[实施计划](docs/superpowers/plans/2026-09-07-simulator-console.md)、[控制台 runtime 契约](docs/api/simulator-console.runtime.openapi.json)、[研究依据](docs/research/2026-09-07-simulator-console-research.md)。

最终验收补充：浏览器独立场景 `run_40f1141f33c6443c99c8ed851537f2b4` 在销售 3 件、需求改为 80 后刷新，仍为现金 1000 元、应收 60 元、现货 17、源序号 2；联动场景 `run_ace55c8511fc4ae08030afffcc15e524` 经原后端审批采购 40 件，页面分 12/28 件收完，最终现金 600 元、现货 60、在途 0、源/后端序号均为 3。[浏览器证据](docs/api/simulator-console-browser-result.json)已保存。

收尾修复：未知写入重试入口不再被读取错误覆盖，确定失败会解锁表单；场景加载期间禁用旧控件，操作绑定已加载 run；旧事件分页响应不会污染切换后的场景；启动器优先使用环境变量中的 backend 认证配置。回归命令为 `node simulation/tests/console_ui_regression.cjs`（3 项通过）。

接续顺序：先让产品前端对接现有 backend 和持久场景，再单独配置/启用 Agent worker 验证事件跟进、解释与审批闭环；这两项尚未完成。随后按业务需求决定真实数据集回放及 RAG。后续接手先检查服务健康和进程归属，本节运行信息是本次交付快照，不代表服务永久在线。

更新：2026-09-07（持久 Simulator 与 Dashboard 首版交付及交接补齐）。配套入口：[PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)。先读PROJECT_CONTEXT理解项目、架构和历史，再读本文掌握当前开发现场；两份文件足以确定范围、设计约束、进度和下一步，实施某个接口时再查具体源码或契约。

### Agent 阶段交付与测试归档（历史记录，2026-09-07）

**已完成的代码：** `agent/src/shopsteward_agent/` 提供真实 LangGraph、可配置模型、租约保护的 PG checkpoint、Hermes 派生记忆规则和扩展接口；`backend/app/agent_bridge/` 提供会话/Run、独立 worker 装配、授权工具、知识版本及持久跟进。支持澄清/恢复/取消、同会话排队、唯一最终回复、跨会话 USER/NOTES 与补货任务 SKILL 的显式增改删。业务工具支持只读 what-if 和本轮数量上限修订，新 Plan 仍由既有用户审批 API 确认。

**已保存的最近测试结果：** backend+agent 联合226项通过（91.65秒），simulator 12项通过（3.49秒），均无失败、无跳过；Ruff、160个文件格式检查、Alembic漂移、契约检查、Agent wheel/sdist 构建通过。真实模型完成3轮知识闭环（24个Run/51项检查），此前非记忆基线14项通过，真实进程恢复套件7项通过。早期失败与后续修复复测均保存在详细证据中。本次仅归档和补齐索引，未重跑业务/模型验收。

| 接手时需要的资料 | 保存地址 |
|---|---|
| 安装、配置、迁移、启动与调用流程 | [agent/README.md](agent/README.md) |
| 综合测试报告（含回归、审查修复、局限） | [docs/reports/agent-v1-test-report.md](docs/reports/agent-v1-test-report.md) |
| 自动验证结果（机器可读） | [docs/api/agent-v1-verification-result.json](docs/api/agent-v1-verification-result.json) |
| 真实模型/进程报告 | [docs/reports/agent-v1-process-report.md](docs/reports/agent-v1-process-report.md) |
| 真实进程原始验收结果与历次尝试 | [docs/api/agent-v1-process-result.json](docs/api/agent-v1-process-result.json) |
| 实施记录与审查修复 | [docs/reports/agent-implementation-progress.md](docs/reports/agent-implementation-progress.md) |
| 设计与计划（顶部有实际交付对照） | [设计](docs/superpowers/specs/2026-09-07-agent-framework-design.md)、[A0～A8计划](docs/superpowers/plans/2026-09-07-agent-framework.md) |
| 研究与依赖来源 | [调研](docs/research/2026-09-07-agent-framework-research.md)、[Hermes许可](agent/THIRD_PARTY_NOTICES.md) |
| 已实现接口 | [Agent契约](docs/api/agent-v1.openapi.json)、[完整runtime](docs/api/backend.runtime.openapi.json)、[实现清单](docs/api/implementation-status.json) |
| 可重复使用的验收程序 | [backend/tools/verify_agent.py](backend/tools/verify_agent.py)、[契约导出程序](backend/tools/export_agent_contract.py) |

**接下来的具体工作：** 按启动说明配置并迁移目标开发库、切换 API 和两类 worker，然后接入聊天页面。外部 RAG、真实预测、语义摘要、自动技能学习及原计划剩余故障矩阵另行推进；特别是“记忆提交后HTTP响应丢失”尚未做真实进程注入。当前首版不代表完整P0或生产负载验收。

**现场保留：** 当前源码40操作/36路径，新增Agent为11操作/8路径；迁移head `0009_agent_scopes` 仅在专用测试/验收库应用。原开发库与8000/8001服务未切换，8024验收API与自建worker已停止。工作区代码、报告与文档尚未提交或推送，接手时需一并保留。

### 历史验证与运行记录

B0-07阶段已完成组合故障、并发和真实进程验收，自动修复两处锁竞争缺陷。backend 146项、simulator 12项通过，无跳过；最新业务[测试报告](docs/reports/b0-07-test-report.md)、[进程证据](docs/api/b0-07-process-result.json)与[验证汇总](docs/api/b0-07-verification-result.json)。验收脚本已停止自己创建的API/两个worker/simulator；PostgreSQL容器继续运行。历史B0-05/06证据保留。

此前已落实[数据字典](docs/data-dictionary.md)中的7个GET，runtime为29操作/28路径，无新表/迁移。backend 186项、simulator 12项全部通过；真实HTTP读取持久SC01、分页、权限和只读性通过，临时8014 API已停止。见[测试报告](docs/reports/frontend-data-test-report.md)、[HTTP证据](docs/api/frontend-data-http-result.json)和[验证汇总](docs/api/frontend-data-verification-result.json)。设计稿planned标签保留历史含义，实际状态以runtime和实现清单为准。

**运行状态区分：** 原开发 API 于此前 13:15 在 8000 启动（当时 29 操作/28 路径），simulator 使用 8001。本次 Agent 工作没有停止或替换这些进程，也没有迁移原开发库。新代码在 `shopsteward_test` 和独立 `shopsteward_agent_acceptance` 库迁移并验证；8024 验收 API 与自建 worker 均已停止。启动新版需按 [Agent README](agent/README.md) 配置、迁移并启动 API/两类 worker，不能把原 8000 实例视为已部署新版。

## 1. 用户已经明确的工程原则

**B2-A Agent 首版框架已实现（2026-09-07）：** LangGraph 主图、独立 Agent worker、真实 OpenAI 模型、租约保护的 PG 检查点、受限业务工具、跨会话 USER/NOTES 与可维护的补货任务 Skill、持久后台跟进已贯通。对话支持只读 what-if 和显式方案修订，新版本仍由用户通过既有审批 API 确认。当前源码导出 40 个操作/36 条路径，迁移 head 为 `0009_agent_scopes`。启动见 [agent/README.md](agent/README.md)，验证范围见 [Agent 测试报告](docs/reports/agent-v1-test-report.md) 和 [真实进程报告](docs/reports/agent-v1-process-report.md)。代码尚未提交；原开发库与 8000/8001 服务未切换到此版本。外部 RAG、真实预测、聊天页面、自动从结果学习技能与语义摘要尚未实现。

**唯一原则：结构正确，功能完整满足要求，且没有赘余的设计。**

- 审查意见是待验证的建议，不能因为CC或其他审查者提出就全部执行。
- 修复真实缺陷；重构必须解决实际维护问题或支撑明确需求，并衡量新增复杂度。不要为“五件套”、目录对称、消除全部包级双向依赖或展示抽象能力而重构。
- 当前为模块化单体。跨模块原子事务、共享模型归属及部分双向依赖可以保留；未要求独立部署的业务模块不必提前满足可单独抽离条件。
- 功能验收看业务结果和异常路径，测试数量、代码行数、目录层数都不是完成度指标。已有测试验证与本次变更相关的真实风险即可，不围绕实现细节堆测试。
- 不为未来Agent/ML接入提前建设插件系统、通用工作流引擎或复杂模拟平台。现有HTTP与业务契约足够支持渐进接入。
- 用户指定工作包后，完成该范围内实现、必要验证和交接更新；阅读交接材料本身不表示要开始所有后续阶段。已有授权范围内的常规可逆工作不必反复请示。

## 2. 当前开发现场

最新 B2-A 验证：backend+agent 联合226项、simulator 12项全部通过且无跳过；Ruff/格式、迁移漂移、契约检查及 Agent wheel/sdist 构建通过。真实模型完成三轮知识闭环及进程恢复检查，详见 [Agent 测试报告](docs/reports/agent-v1-test-report.md)。原计划的语义摘要与完整进程故障矩阵尚未全部交付，不能把首版框架等同完整产品P0。

| 项目 | 本次核对结果 |
|---|---|
| 工作资料根目录 | `D:/HuaweiMoveData/Users/13736/Desktop/AIS/Group_Project` |
| 应用仓库 | 上述目录下的`ShopSteward`；命令需在正确目录执行 |
| 分支 / HEAD | `YH` / `ab01ae3`，`backend more retreive`；Agent调研期间由外部提交推进，本轮助手未执行提交 |
| 已提交基础 | B0-01至B0-07、首批7个前端只读查询及相关测试/契约、初版Agent研究文档 |
| 未提交工作 | Agent 包、backend agent_bridge、3个迁移、业务方案约束适配、测试、依赖锁、契约、研究及交接 |
| 下一阶段 | 按 Agent README 切换开发环境并接聊天页面；扩展语义摘要、外部 RAG/预测、技能自动学习需独立工作包 |
| 暂未接入 | 真实预测、外部 RAG、自动学习技能、聊天页面；Agent/LLM/显式记忆与任务 Skill 已实现 |
| 原开发API | `http://127.0.0.1:8000`，本轮未切换；新 Agent 代码在隔离验收进程验证 |

接手先执行`git status --short`、`git log -1 --oneline`、`git branch --show-current`。不要把未提交改动当垃圾清掉，也不要假定远程仓库包含它们。本次没有提交、推送或远程最新状态核验。

## 3. 项目和设计的必要摘要

ShopSteward是面向小商家的持续经营助手，首条业务线为活动备货与现金安全。当前先交付不依赖AI在线的backend主干B0：记录经营事实、比较采购候选、提出方案、用户审批、执行并根据新事实继续检查。Agent负责解释、推理和跟进，不能取代账本、确定性约束或审批。

采用FastAPI模块化单体、独立API进程、独立worker、PostgreSQL。simulator是独立HTTP进程，拥有自己的持久世界、数据库、账号及迁移；backend通过契约调用，不能直接读取simulator表。多个API/worker实例共享同一模拟世界。

当前实际代码按`api/core/db/scheduling/operations/missions/planning/alerts/execution/reporting/agent_bridge`组织，没有`app/modules/`、`app/workflows/`、`app/integrations/`或`api/routes/`层。PlanRow、ScheduleRow、TimelineRow、InboundRow仍在`missions/models.py`；纯候选规则在`planning/engine.py`，哈希规范化在`planning/canonical.py`，风险规则在`alerts/rules.py`。跨模块用例暂由jobs/repository/accounting等函数承担，不为目录整齐搬模型。

### 必须保持的业务与事务约束

1. 金额用整数分，数量用整数件，当前币种CNY；现金、预留、应收、现货、在途分别记录。可用现金为现金减预留，应收不作为可用现金。
2. Plan保存不可变DecisionSnapshot、候选、proposed_purchase及`sha256:`摘要；规范化采用decision-v1、UTC秒级时间。q=0时proposed_purchase为空，不能创建采购Action。
3. 审批只接受decision、expected_plan_version、expected_state_version、proposal_hash，审批人从Bearer身份取得。审批和发送前分别核对当前状态、Mission/策略、来源新鲜度、输入期限、到货窗口和现金底线。
4. 审批事务登记Approval、唯一Action与持久JobRun；发送前才预留资金并记录EXECUTING/执行版本。每个门店最多一个未决采购占用执行门控；自己的预留不能让原方案误判失效。
5. 写事务按store→mission/plan→action→job锁顺序；领取/续租只锁任务。规划/看板使用短一致快照，旧计算结果可丢弃并安排重算。HTTP不能包在本地写事务里。
6. 派生业务写入与JobRun完成或失败必须同事务受实际租约/token保护。租约丢失不能撤回外部请求，也不能把采购判为失败；当前持有者核对原Action。
7. 网络超时/PENDING保留UNKNOWN、资金预留和门控。核对先查询原Action；只有实际404且供应方保证幂等时才使用原ID、原payload、原键重发，不能创建第二个采购。
8. HTTP受理回执和PURCHASE_ACCEPTED共享Action级唯一账本效果。GOODS_RECEIVED累计不超过已确认订单；缺少本地确认时先在事务外查询回执，再整批原子入账。来源事件要求连续游标，重复内容无重复效果，矛盾内容不得覆盖旧事实。
9. 冲突事件整批回滚后另存证据和ACTION_EXCEPTION；非法JSON、null、NaN、HTTP409不能被当成404或普通超时无限重试。manual_review停止自动改账，目前没有人工强制改账接口。
10. Action SUCCEEDED表示采购受理及资金/在途入账，不表示已到货。取消未发送采购可直接停止；已发送采购即使Mission取消或Plan过期仍继续核对；有未决Action时不能complete。
11. 警报知晓不表示解除；恢复要有新鲜且可判断的证据。UNKNOWN数据保留原业务风险并标记DATA_STALE。GET不创建检查、不采购、不推进模拟时间。
12. 租约、心跳、超时、重试使用真实时间；经营事件使用simulation_time。只有拉取事件并追平源头才能证明同步新鲜，空页也可证明追平，单次推送不证明已经追平。

### worker当前扩展方式

`app/bootstrap.py`统一调用四个`make_handlers(settings)`工厂，发现重复job_type即报错。当前8种handler：worker_probe、initialize_scenario、sync_events、check_mission、execute_purchase、reconcile_action、advance_scenario、check_freshness。`--profile agent` 单独注册 agent_followup，默认并发1；business profile 保留上述8类。Agent 跟进在领取前扫描持久触发，模型忙碌时扫描可能延后，业务扫描循环仍独立运行。

Handler的职责：

| 阶段 | 事务和用途 |
|---|---|
| before_claim(db) | 领取事务前调用，自管短事务；共享回调每次run_once只执行一次。异常则不领取，停止信号阻止继续执行。当前用于恢复到期且无活跃任务的孤立Action |
| run(db, job) | 在发布事务外读取/计算/调用HTTP；需要发送登记时先完成短事务再发送 |
| apply(session, job, prepared) | 发布派生结果，与JobRun完成在同一租约事务内 |
| after_complete(session, job, result) | 同一完成事务内登记后续任务或历史 |
| on_error(session, job, error) | 原业务事务回滚后的失败事务；当前只对retry_safe且未报告丢租约的任务调用。先写业务证据，最后repo.fail验证租约；验证失败或钩子异常时全部回滚。钩子不得HTTP或自行提交 |

业务异常解释在对应handler内，Runner不识别某个采购任务名或EventActionConflict。on_error自身失败会保留RUNNING供租约恢复。before_claim保留Action恢复用途。B0-06的周期派发由Runner.serve的独立扫描循环调用dispatch_due，不占执行槽位；run_once不运行周期扫描。

## 4. 已完成和验证到什么程度

| 阶段 | 已实现内容 | 当前边界 |
|---|---|---|
| B0-01 | API/身份/统一错误、DB迁移、独立worker、持久队列/心跳/租约 | 技术探针不代表业务完成 |
| B0-02 | catalog/初始化、State、事件/账本、连续游标、独立simulator | 正向采购/到货已在B0-05补齐 |
| B0-03 | Mission管理、固定预测、候选比较、不可变Plan、手动检查及重算 | 真实模型未接入 |
| B0-04 | 四类警报的基础、知晓/恢复/历史、一致看板；动作异常由B0-05接入 | B0-06补齐周期新鲜度派发，GET仍不写警报 |
| B0-05 | 精确审批、预留/发送、原Action核对、唯一采购/到货入账、显式advance及SC01 | 周期自动运行由B0-06补齐，故障注入仍仅为受控测试 |
| B0-05后收口 | core哈希、API公共定义/B0Router、通用钩子与工厂、文档对齐 | 当时未迁移数据库；原有未提交内容保留 |
| B0-06 | 固定锚点周期派发、Schedule接口/生命周期、源同步/新鲜度、事件合并及租约恢复 | backend迁移0006_periodic |
| B0-07 | 组合竞争/故障测试、101门店锁竞争、双worker中断/停机/源恢复、自动SC01与精确重启回放 | 有界本机运行，非长期负载或生产SLA；无新接口/迁移 |

B0-07阶段验证：backend **146通过**（19 API、16单元、111真实PostgreSQL/跨服务集成），simulator **12通过**，无跳过；Ruff通过，backend app/tests/migrations/tools共99个Python文件格式通过；backend及simulator Alembic无漂移；53个设计示例、2个Plan hash通过。见[verification-result](docs/api/b0-07-verification-result.json)。

B0-07阶段另运行独立API、两个worker与simulator，完成两轮各8个同键并发审批、自动SC01、RUNNING源任务所属worker强杀、来源中断与告警恢复、双worker停机跨周期及不少于90秒的有界观测。重启全部服务后Action、供应商回执、六条完整来源事件及精确账本均不变。细节与参数见[报告](docs/reports/b0-07-test-report.md)。这不等于长期负载验证；B0-06的11.6秒自动检查结果仍保存在原[periodic-smoke-result](docs/api/b0-06-periodic-smoke-result.json)。

历史B0-05的122/12测试记录及显式SC01/restart证据保持原文件，不冒充本轮结果；旧结构收口没有重跑smoke的限制仅适用于那一轮。

SC01固定验收：成本10元/件、售价20元/件、现金底线300元、候选0/20/40/80。初始现金1000元/现货20/需求60；采购40受理→到货40→销售10→需求从50上调到70→采购20受理→到货20。最终现金400元、应收200元、现货70、在途0、预留0；采购账本2条、到货2条。80件候选会使现金降至200元，必须淘汰。活动尚未销售/结算完成，不自动结束Mission。

### 当前接口边界

当前源码导出40个操作、36条路径，包含29个B0操作与11个B2-A操作；原完整设计稿26操作与前端补充设计7操作属于设计基线，实际清单以runtime为准。

| 入口组 | 当前接口 |
|---|---|
| 首批前端查询 | GET `/api/v1/me`、`/api/v1/stores`、`/api/v1/sales`、`/api/v1/sales/summary`、`/api/v1/actions`、`/api/v1/inbounds`、`/api/v1/ledger-entries` |
| Agent | 会话创建/列表、消息提交/读取、Run读取/恢复/取消、followup配置、知识读取/编辑；见 [Agent契约](docs/api/agent-v1.openapi.json)；内部工具网关仅接受绑定Run租约的凭证 |
| 健康/运维 | GET `/health/live`、`/health/ready`、`/api/v1/monitoring/status`、`/api/v1/job-runs/{job_run_id}` |
| 经营/展示 | GET `/api/v1/catalog`、`/api/v1/dashboard`、`/api/v1/alerts`；POST `/api/v1/alerts/{alert_id}/acknowledgement` |
| Mission | POST/GET `/api/v1/missions`；GET `/api/v1/missions/{mission_id}`；POST其`/control`、`/checks`；PATCH其`/schedule`；GET其`/plans`、`/timeline` |
| 方案/执行 | GET `/api/v1/plans/{plan_id}`；POST其`/decision`（approve=202、reject=200）；GET `/api/v1/actions/{action_id}` |
| 内部/演示 | POST `/internal/v1/events/batches`、`/dev/v1/scenarios`、`/dev/v1/scenarios/{run_id}/advance` |

用户Bearer有viewer/operator/approver/admin角色及store授权；operator可创建/检查/暂停恢复/知晓警报，approver可审批/完成取消，admin可访问开发入口。内部事件要求独立service身份及scenario_run_ids授权；service不能冒充用户审批。命令幂等键包含principal、operation和请求路径资源/内容，不因重放绕过当前资源授权。

simulator有create run、list events、purchase、query purchase、advance五个业务接口和ready；服务token仅backend使用。advance四阶段为到货、销售10、需求70、再次到货，多步中途阻塞整批回滚；所有GET不推进世界。

## 5. 后台调度与B0-07验收结果

1. **持久周期派发。** Mission Schedule继续保存在missions/models.py；源计划source_schedules按scenario_run_id/job_type保存5秒sync_events和60秒check_freshness周期。dispatcher发现候选时以FOR UPDATE OF store SKIP LOCKED在LIMIT之前跳过忙门店；释放发现阶段短锁后，再逐项短事务锁store→mission/schedule→job，重查到期，入队/合并和推进next_run_at同事务。停机跨周期合并为最新发生点并跳到下个未来锚点。每类每轮最多100条。
2. **配置与生命周期。** PATCH `/api/v1/missions/{mission_id}/schedule`返回Schedule，要求operator/门店授权、幂等键、interval_seconds（5～3600）、enabled、expected_schedule_version。新Mission默认启用，旧禁用Mission迁移时保持禁用。暂停清空到期时间并保留enabled偏好，恢复重新计时，完成/取消关闭。配置及生命周期变更提升schedule.version；周期派发不提升版本、不修改运行中的任务。
3. **持续来源与新鲜度。** 同源/类型只有一个活跃Job；周期触发、初始化、advance、Action完成、CLI都走合并。分页及运行中的新显式请求用持久rerun_requested在完成事务中登记后继；事件全部补齐。空页追平刷新last_success_at，失败保存last_error。check_freshness可为ACTIVE/PAUSED Mission留DATA_STALE，不清除原业务风险；源恢复后唤醒ACTIVE Mission重新核验报价/预测等输入。
4. **事件与恢复。** 事件入账后在同一事务中合并受门店状态版本影响的ACTIVE Mission检查及目标版本；重复事件不重复唤醒。RUNNING检查仍以recheck_required在完成事务创建后继；旧租约不能提交派生结果。扫描循环独立于执行槽位，慢HTTP不会阻止到期登记。源事实和已发采购核对不随Mission暂停/取消停止。
5. **验收。** 新测试覆盖周期锚点/停机合并、多派发并发、事务回滚、事件唤醒、分页/运行中请求合并、手动同步重放、源错误/新鲜度、饱和槽位与其他worker推进、旧租约回滚、Schedule权限/版本/生命周期。自动三进程SC01和重启已验证。

**B0-07已完成：** 新增8个集成用例，覆盖不同键竞争审批+丢响应核对、来源重试耗尽后周期恢复、规划中事件突发与暂停恢复、暂停/取消中先到货后超时，以及101门店候选公平性和忙门店Action恢复。复现并修复两处生产缺陷：LIMIT之前未跳过锁导致候选饥饿；孤立Action恢复等待门店锁导致整个领取前钩子卡住。真实进程验收与独立审查通过，具体断言、修复及边界见报告。该阶段尚未开始 B2 Agent；现已在后续 B2-A 接入。B1预测、RAG、多SKU/多供应商优化仍未开始；下一工作包按用户指定，不承诺负载下5/30/60秒时延上限。

实现计划与决定见[2026-09-07-b0-06.md](docs/superpowers/plans/2026-09-07-b0-06.md)。无需重新实现Schedule、source同步或现有Action恢复。

B0-07计划见[2026-09-07-b0-07.md](docs/superpowers/plans/2026-09-07-b0-07.md)。在仓库根运行 `.venv/Scripts/python.exe backend/tools/verify_resilience.py` 可复现验收。要求8010～8013空闲且无其他活跃worker；创建新开发场景并保留数据与var目录日志；使用租约6秒/心跳2秒/来源过期8秒覆盖值，最后只停止自身进程。

**B0-07后数据边界核对（2026-09-07）：** 用户询问应保存哪些数据、前端可读取什么。本次读取7份飞书正文及2块相关画板，并对照21张应用表的源码和22个runtime操作，形成[数据存储与前端访问边界](docs/data-and-frontend-boundaries.md)。结论是核心类别可明确；缺销售查询/汇总、采购列表/当前到货明细、经营流水及身份/店铺发现。当前售价、活动/仓储深度、真实数据接入、财务范围及Agent产物契约仍需按文档所列边界定下。该文是范围核对和建议，不是新增API已实现或数据库迁移已批准；本轮没有改业务代码/数据库/飞书，也不改变B0测试报告的适用版本。

## 6. 已知边界与CC复核结论

### 首批前端数据契约交接

边界核对后的设计与实现已完成：7个只读GET复用现有表，不需要新增表或迁移。字段类型、来源、空值、权限及时间口径见[数据字典](docs/data-dictionary.md)；分页、快照、错误与聚合规则见[设计规格](docs/superpowers/specs/2026-09-07-frontend-data-contract-design.md)。销售汇总只表示已记录事件；采购受理与到货状态分离；经营流水不是完整财务总账。真实商品售价、仓库/批次、回款/退款及Agent范围没有被这批查询替代。

[补充OpenAPI](docs/api/frontend-data.openapi.json)保留7个操作的设计基线、22个schema和14个响应示例，8个既有共享schema与runtime完全一致。校验器已改为核验路由实际注册和实现清单、runtime响应兼容及原算术/负例；本轮全部通过。backend全量186项（19 API/48单元/119集成）、simulator 12项通过，无跳过；新增40项覆盖查询/日期/投影等分支。实现与验收细节见[测试报告](docs/reports/frontend-data-test-report.md)。在根目录运行`.venv/Scripts/python.exe backend/tools/verify_frontend_reads.py`可复现只读HTTP验收，要求8014空闲及原B0-07场景仍在；它只启动自有API，最后停止，不重新运行场景或进程故障测试。

### 既有审查结论

- 接受并完成：纯digest放core；路由公共定义集中；4个缺失操作元数据补齐；错误模板统一含409；runner业务特判改为有具体用途的两个钩子；make_handlers统一注册。
- CC“每个模块完整五件套”不准确；“删Store局部导入即可”需先在顶部补Store；“约40行零行为变化”不适用于租约失败路径。移动Python模型定义通常不需要数据库迁移，当前不搬是收益不足，而不是必然需要迁表。
- 模块级立即执行的导入图无循环，不代表所有业务包可独立部署；函数内延迟导入及跨包依赖仍有实际用途。scheduling/repository.py的monitoring_status仍读取SourceCursor，只有Runner已移除业务特判。
- 记录即可，非后续阶段前置：Plan/Schedule/Inbound模型归属、operations.apply_event放在repository、跨用例事务复杂度、smoke在运行时包且依赖开发库/本地路径、int64上限常量重复、local版本UUID与digest两种生成方式、simulator剧本和持久化耦合。出现实际扩展/打包需求再决定处理。
- manual_review仅留证并停止自动改账，暂无人工覆盖接口；simulator没有在线故障注入入口。看板读取时的新鲜度会随时间变化，持久警报由Mission检查或周期check_freshness更新。

## 7. 本机运行与必要验证

已配置环境的历史记录：Windows/PowerShell，Python3.12.13，PostgreSQL17.11，依赖锁在根目录uv.lock；虚拟环境在根`.venv`。API默认8000、simulator8001，PostgreSQL绑定本机55432。backend库shopsteward / 测试库shopsteward_test；simulator独立库shopsteward_sim / 测试库shopsteward_sim_test及独立账号。

迁移头：backend `0006_periodic`，simulator `sim_0002_purchases`。凭证在Git忽略的`backend/.env`、`simulation/.env`、`infra/.env`；backend的SIMULATION_TOKEN与simulator的SIM_SERVICE_TOKEN对应。不要打印/写入文档/覆盖已有配置。新机器按两个模块README准备数据库和配置，不能假定根目录资料、虚拟环境或.env随Git带来。

当前默认值（本地.env可以覆盖）：worker并发4、poll1秒、租约30秒、续租10秒、任务超时120秒、停机等待10秒、来源新鲜30秒、Plan TTL900秒、固定预测TTL3600秒。普通安全任务最多3次尝试，临时失败2/4秒重试；Action核对5/10/30/60秒，是另一层机制。

### 启动（已有配置时）

**当前已有API运行，以下是服务未运行时的启动说明。** 本次重启仅处理已核验属于本项目的API进程，未启动或重启worker/simulator；本文更新时没有重新核验这两个服务的在线状态。API健康不等于自动同步/任务执行正常，只读页面数据可用性和新鲜度仍需分别判断。

最近一次API以仓库`.venv/Scripts/python.exe -m app`、工作目录`backend`隐藏启动，启动器PID为`38492`（历史定位信息，后续操作前重新核对进程身份和端口归属）。本次日志位于Git忽略目录：`var/backend-api-20260907-131524.stdout.log`和`var/backend-api-20260907-131524.stderr.log`。没有覆盖.env、执行迁移、提交或推送。此次交接更新只复核HTTP可用性，186/12业务测试结果仍指上面的接口实施验收，没有再次运行全量测试。

从仓库根启动数据库：

```powershell
docker compose --env-file infra/.env -f infra/compose.yaml up -d --wait
```

三个独立终端，分别进入对应目录：

```powershell
# simulation目录
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m simulator
```

```powershell
# backend目录：API
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m app
```

```powershell
# backend目录：worker
..\.venv\Scripts\python.exe -m app.worker
```

API不自动启动worker、不自动迁移。开发Swagger为http://127.0.0.1:8000/docs；production默认关闭docs与dev路由。接手时先确认端口和进程归属，不盲目启动第二份或终止不明进程；升级0006_periodic前停止旧worker；迁移会合并重复未完成只读源任务，保留一个任务及后继追平请求，不修改采购账本。历史验收自建进程已停止；当前8000 API已按用户要求重新启动，其余服务按实际在线情况决定是否启动。

### 验证命令（按变更需要执行）

backend目录；集成测试只允许专用测试库，未设置时会skip：

```powershell
$entry = Get-Content '.env' | Where-Object { $_.StartsWith('DATABASE_URL=') }
$env:TEST_DATABASE_URL = ($entry.Substring(13) -replace '/shopsteward$', '/shopsteward_test')
$simEntry = Get-Content '../simulation/.env' | Where-Object { $_.StartsWith('SIM_DATABASE_URL=') }
$env:TEST_SIM_DATABASE_URL = ($simEntry.Substring(17) -replace '/shopsteward_sim$', '/shopsteward_sim_test')
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m ruff check app tests migrations tools
..\.venv\Scripts\python.exe -m ruff format --check app tests migrations tools
..\.venv\Scripts\python.exe -m alembic check
..\.venv\Scripts\python.exe -m app.export_openapi
..\.venv\Scripts\python.exe ../docs/api/validate_contracts.py
```

simulation目录设置TEST_SIM_DATABASE_URL后执行`..\.venv\Scripts\python.exe -m pytest -q`。新测试库需先按模块README迁移；上面的alembic check读取当前DATABASE_URL，不代表自动检查或迁移测试库。

两套测试共用本机实例，backend集成测试还访问simulator测试库；不要让多个代理同时清理/运行同一套测试库。部分测试夹具会清任务/命令，并把测试Action终止以隔离恢复扫描；这些操作不能用于开发库。

真实HTTP联调可在三个服务运行后于backend执行 `..\.venv\Scripts\python.exe -m app.smoke_periodic`；重启三服务后加 `--verify-restart`。也可在仓库根运行 `.venv/Scripts/python.exe backend/tools/verify_periodic.py` 自动管理自己的三进程，两轮验收后全部停止（要求8000/8001空闲）。脚本会创建开发场景及模拟采购，不是只读诊断；结果保存在独立B0-06文件，不覆盖B0-05历史证据。持续worker已有自动源同步，CLI sync-events仍可立即请求同步并合并已有任务。

## 8. 新对话接手顺序与交接维护

1. 读PROJECT_CONTEXT与本文，先确定用户本轮任务；不要把历史建议自动提升为当前待办。
2. 核对Git、已有未提交文件、相关源码和运行环境；保留当前数据契约与交接改动，暂不清理记录级问题。B0-05至07现已在HEAD中，旧报告中的基准提交仅描述当时现场。
3. B0-07已经完成，阅读报告后执行用户新指定的工作；不要再次把组合验收列为未开始。
4. 修改完成后更新PROJECT_CONTEXT的状态/设计变更和本文的现场/待办/验证日期；保存可区分测试、真实HTTP和重启验收的证据，不覆盖历史结论的适用范围。

主要入口：[backend开发设计](docs/backend-development.md)、[simulator契约](docs/simulation-contract.md)、[接口设计/用法](docs/api/README.md)、[实际实现清单](docs/api/implementation-status.json)、[backend启动说明](backend/README.md)、[simulator启动说明](simulation/README.md)。这些用于深入实施，不是先理解交接必须逐份读取的材料。


## 2026-09-11 v6 产品接入完成

主 ShopSteward 已接入独立 v6 ML 服务、后端预测 API/持久化/规划适配、首页预测面板，以及 LangGraph `get_forecast` 取证和引用校验。开发与测试库迁移到 `0012_forecast_v6`；现有采购审批不变。按用户最新要求，界面及 Agent 统一使用“模型推演，仅供参考”，原始日期放详情。

本机 `http://127.0.0.1:3000` 已启动，模型服务8053、后端8000、模拟器8001。便携模型包 `var/forecast-v6/bundle` 已随Git发布，组员按ml/README.md安装验证；私有启动配置沿用现有模型虚拟环境。完整 API、数据模式、规划适用范围、启动方法及验证见 [v6接入报告](docs/reports/forecast-v6-product-integration.md)。真实 Luna 问答已跑通库存→预测→方案并保存结构化预测引用。
