# 本地上云准备：实施与验收状态

2026-09-08。**实施进行中，pilot_ready=false，MVP_ready=false。** 本报告区分已有代码、文件验证和真实服务验收。不能用单元测试或协议夹具代替数据库、HTTP全链路、构建和恢复结果。

## 当前交付

| 工作包 | 已实现 | 尚待验证或补齐 |
|---|---|---|
| L0 | HEAD602a6c6/YH基线、原K0与K1契约hash、隔离配置、专用PG起点 | 原开发库未迁移 |
| A1/A2 | 独立扩展schema、来源/事实/题集验证、200份pilot正常HTTP上传/READY/发布 | 真实关系边导入 |
| A3 | 900合成+24公开=924独立文档、200额外修订、300题；独立100条dev请求及输入hash | 还缺76份公开资料、独立人工审阅与真实检索效果 |
| B1/B2 | knowledge独立uv包、契约、六种格式解析、位置/父段落、原件存储 | 实际服务负载及扫描件OCR仍未实施 |
| B3 | backend outbox/发布、独立PG worker、租约/重试、来源与投影；双库迁移、25项PG边界验证 | 实际worker崩溃恢复 |
| B4 | 真实CJK词法索引及条款命中；可选云embedding/dense/RRF/rerank、有证据的有向关系、父段落补充 | dense/关系路径实际效果、系统评测与延迟 |
| C1 | 两个只读工具、现有LangGraph取证顺序/结果回流、HTTP授权复核、4场景Luna真实闭环 | 通用路由准确率和浏览器引用体验 |
| C2 | 独立Compose、非root镜像真实构建及digest、导出/校验/空目标恢复工具 | 实际双库恢复与查询对比 |
| C3 | 有界真实HTTP探针、并发1/5/10基准工具、失败关闭验收判定、云实验模板 | 生命周期/Agent/worker重启真实进程演练尚未完成 |

## 重要实现选择

- backend保留业务权限、原件及发布权威；独立knowledge PG管理派生投影、块、任务与有来源的关系。首版没有引入Neo4j；这也不表示已通过引擎效果比较。
- OpenSearch按词法配置/embedding profile共享索引，块存储ID包含generation；权限过滤使用version/generation/revision的联合身份。索引数量不随文档数量增长。只有指定generation可以删除。
- READY须有可搜索的完整候选manifest证明；HTTP200但分片失败/超时按降级处理。乱序和旧租约不能覆盖新generation。
- 文档更新的CAS计数与证据投影修订分开：追加新原件不应撤销旧发布；权限/实体/正文适用metadata变化需要新generation与显式重新发布。未来或有界替换保留旧版本未被覆盖的时间区间。
- 关系仅沿已确认、有来源、条件满足的有向边取回，最多3跳；不把可达性当作替代许可或完整影响范围。最终授权再次检查路径上每个来源版本。
- 新增关系导入器复用实际worker chunk配置，按上传后的真实version ID绑定原文，再核对当前发布与服务端文本/hash/locator后提交。800条合成关系已通过离线唯一原文绑定；尚未进行真实HTTP关系导入。`SUPPLIES`及显式`HAS_APPLICABLE_DOCUMENT`只定义有向取证路径，所有条件原样保留。
- 返回candidate有文本hash、原件hash、version/generation、locator、来源/模拟标志、检索通道和时间。parent补充保留独立块位置，不把拼接文本伪装成原来的单一块。
- 生成模型tokenizer尚未确定，当前使用明确标注的字符预算估算，不能将其写成实测6000 tokens。
- RAilG的解析/引用工作流经验用于接口设计；本轮新增解析实现没有复制RAilG源码，也不依赖IH绝对路径或其凭据，见knowledge/THIRD_PARTY_NOTICES.md。

## 已取得的执行证据

2026-09-08用户启动Docker后的新增实测：

- 独立API8020/PG55434/OpenSearch19201就绪；knowledge迁移 `knowledge_0002`，业务专用测试库迁移 `0011_knowledge_delivery` 且schema无漂移。镜像实际构建、UID10001、可写原件卷和基础镜像digest已验证。
- 200份pilot经正常HTTP入库并发布，独立库200个成功任务/200 READY generation，声明、PG与OpenSearch均5169块、零不匹配。最终只读快照 `var/knowledge-precloud/infra-final.json`，OpenSearch green，API readiness200，worker运行。
- 投递35+文档证据30混合测试：25项真实PG、40项非PG，全部通过。非重语料backend unit+API最终216 passed / 9.51秒，包含正文标识及跨轮累计关系路径回归；独立聚焦29 passed（重叠批次不相加）。Agent30 passed、3 skipped / 2.94秒。infra修复48 passed、1个Windows symlink skip。
- 现有Luna Responses真实4个Run、10次逻辑模型调用、6次工具调用：只查业务、供应商条款、提前排队的引用展开、库存与条款混合。r5原始结果与实际检查点证明检索主动补搜并取到关键条款；正文错误标识另外以确定性回放校验，不冒充新在线结果。完整证据见[Agent接入报告](agent-document-langgraph-integration.md)。
- 新工具说明已重新导出，10个delivery路径/10个service路径/2个文档工具的OpenAPI验证通过。旧K0/K1仍单独保留。

下面是Docker启动前的离线验证记录，保留其测量范围，不与新增批次累加：

- 现有K1起点：57 passed / 4.37秒。
- knowledge全体测试：322 passed、15 skipped / 8.42秒；跳过的PG/权限环境检查不计通过。
- backend最终非语料unit+API：187 passed / 9.53秒；语料独立批次45 passed（含7项导入器测试，有交集，不相加）。之前并行修复期间有两个旧测试替身失败，更新替身后上述最终批次已通过。
- backend文档投递/Agent边界的非PG批次：40 passed、25个PG项deselected / 3.68秒。
- Agent回归：26 passed，3 skipped / 3.31秒；跳过的真实模型测试不计通过。
- uv.lock已更新到93 packages，`uv lock --check --offline --cache-dir .uv-cache`通过。
- pilot200与扩展1124版本已通过导入器文件hash、大小、实体映射和严格UploadMetadata校验；business_writes=0。
- 修复183份CSV后实际解析：1124版本全部COMPLETE、16205块、1878743字符，18.710秒wall / 18.219秒CPU。Windows报告整个解析进程峰值working set为123805696字节（约118.1MiB），不包含DB/索引/worker容器。详见`var/precloud/parse-profile-final.json`；这是单次本机解析，不是索引首建或云端性能。原首个含CSV警告的快照已由本次取代。
- 800条关系均匹配唯一完整原文chunk，imported=0、无业务授权；真实服务确认未运行。完整输入hash与分批验证记录见[机器检查点](knowledge-precloud-verification.json)和[语料最终核验](../evaluation/knowledge-expanded/reports/finalization.json)。
- 只读运行时契约导出经OpenAPI验证：knowledge-delivery-v1、knowledge-service-v1与两个文档工具；原K1冻结契约另保留。

## 未执行项和复现入口

Docker已由用户手动启动，独立knowledge容器保留运行；验收8018/API/publisher/Agent自建进程已关闭。未改开发服务8000/8001、未迁移开发数据库、未创建云资源。已使用现有Luna配置执行有界生成联调，embedding/rerank未启用。空环境恢复仍需完成兼容PG客户端和独立空目标的实际验证。

1. 按[运行手册](../runbooks/knowledge-local-and-cloud.md)复用独立Compose项目和私有env。已就绪PG/索引/API为55434/19201/8020；再次Agent验收用8018，先检查端口。
2. backend测试库已通过 `test_knowledge_runner.py` 迁移与边界测试。现存200份语料租户 `knowledge-test-agent-0908020841-STORE01`、收据 `var/precloud/agent-0908020841` 可复用；常规integration fixture会清理测试库，运行前须考虑保留该验收现场。
3. 导入器`backend/tools/import_knowledge_corpus.py`支持`--prepare-mapping`离线准备、`--seed-test`显式测试库seed、`--dry-run`文件检查以及真实HTTP续传/发布。公共资料明确映射到测试店铺，不提升为跨租户权限。
   发布后运行`backend/tools/import_knowledge_relations.py`，使用同一mapping与收据；不传真实收据时只能`--dry-run`做原文绑定。旧收据缺少`index_profile_id`须先通过文档导入器刷新。
4. `backend/tools/profile_knowledge_corpus.py --manifest ... --mapping ... --output ...`可重新执行本地解析。`knowledge/tools/benchmark.py`仅接受独立dev题，服务实际不可用时不会输出虚构速度。
5. `backend/tools/verify_knowledge_precloud.py`执行健康、原件、证据、无匹配与范围探针；构建和本轮Agent已另有真实记录，主动生命周期及恢复仍需补齐，不因已有passed收据自动升级。
6. 完整恢复在新的空数据库/空目录和独立index prefix进行。检索云模型、区域和实验预算尚未决选；cloud-experiment.json已固定pilot manifest与100条dev-only请求hash，仍为not_run、billable_run_enabled=false。它与本轮使用既有Agent生成模型的联调分开。

评测日期是固定历史场景时间；Agent当前证据工具按当前时间取用。不得将历史题的as_of检索成绩声称为当前Agent运行效果。公开资料使用范围/语言覆盖及人工标注未审阅限制见[语料质量报告](../evaluation/knowledge-expanded/quality-report.md)。
