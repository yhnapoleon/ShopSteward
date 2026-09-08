# Knowledge 服务器交接与云端试部署

2026-09-08。可以提交“本地检索闭环与云端试部署基础”PR并交给服务器负责人。当前代码支持开始服务器环境准备和隔离试部署；完整搬迁验收仍未通过，`pilot_ready=false`。本文件是交接入口和工作划分，不声称已经提供经过验证的云端一键部署。

## 先读这些文件

1. [当前验收与未完成项](../reports/knowledge-precloud-readiness.md)。
2. [Agent接入图与真实调用轨迹](../reports/agent-document-langgraph-integration.md)。
3. [本地启动、镜像固定与恢复手册](knowledge-local-and-cloud.md)。其中命令主要针对Windows本地测试环境，服务器上应使用对应系统的命令和独立配置。
4. [Compose](../../infra/compose.knowledge.yaml)、[配置模板](../../knowledge/.env.example)、[Dockerfile](../../knowledge/Dockerfile)、根 `pyproject.toml` / `uv.lock`。
5. [本地准备总计划](../superpowers/plans/2026-09-07-knowledge-precloud.md)及三个子计划。

## 部署边界

第一阶段搬到服务器的是 Knowledge API、ingestion worker、独立PostgreSQL、OpenSearch和知识服务持久卷。业务backend、业务DB、原件权威、发布控制及LangGraph Agent继续在现有环境。原件经现有后台上传与投递流程送入知识服务；不能把服务器上的知识库直接当作业务权威库。

实际调用是：本地Agent → 本地backend工具网关 → 服务器Knowledge API → 带metadata的candidate → backend重新核对权限与发布 → Agent。Agent不直连PostgreSQL或OpenSearch，知识服务的service key也不下发给模型。

现有Compose已经包含这四个服务，但只把端口绑定到127.0.0.1，且OpenSearch关闭了安全插件。该配置适合隔离主机内演练。跨机器联调需另外准备私有连接或受保护的API入口，数据库与索引端口保持内部可达。最先可以通过SSH隧道/VPN验证跨机链路，随后再确定长期入口；不能直接把当前三个端口改为公网开放。

## PR应交付什么

| 内容 | 交付方式 |
|---|---|
| `knowledge/`、backend投递/工具/迁移、Agent图修改、测试 | 同一PR完整包含，不能只提交Compose |
| `infra/compose.knowledge.yaml`、helper、Dockerfile、`.dockerignore` | 同一PR，包含相关workspace manifest和 `uv.lock` |
| 本文、运行手册、验收报告、API契约 | 同一PR，方便负责人从GitHub进入 |
| pilot manifest、实体fixture、原件与评测输入 | 包含 `docs/evaluation/knowledge-expanded/` 所需文件，保留来源/合成标记；首次仅用200份pilot |
| 密钥、数据库密码、私有env | 在部署环境另行配置，不提交Git |
| 本地DB、Docker卷、`var/`中的发布收据/映射/镜像记录 | 不会随Git自动传输；在目标重建，或另行制作经过验证的迁移包 |

当前不少新增文件尚未提交，提PR前应查看未跟踪文件，避免只提交已有文件的diff。现有 `var/` 被Git忽略；报告中引用本机 `var/...` 的路径是本地证据位置，不是GitHub可下载的部署资产。也不要把本机生成的实体ID/发布收据用于另一套新数据库。

接收方应记录PR对应commit SHA。在一份干净checkout里从根目录构建，验证所需原件、workspace依赖和配置模板齐全。当前本地镜像ID只是内容ID，不是已经推送的仓库digest；接收方可从该commit构建并记录结果，或通过另行授权的镜像发布流程取得确切镜像。

## 双方实施顺序

| 阶段 | 服务器负责人 | 项目/Agent负责人 | 完成证据 |
|---|---|---|---|
| 1. 接收与环境准备 | 获取固定commit，确认OS/CPU架构、Docker Compose、可用资源、持久卷与网络 | 提供完整PR、配置字段和语料入口 | 干净checkout构建记录，目标环境信息 |
| 2. 空服务启动 | 按Compose启动独立PG/索引，显式运行knowledge迁移，再启动API/worker；记录image/digest | 确认API契约与版本 | live/ready200、schema、索引健康、worker状态 |
| 3. 跨机器接通 | 配置仅backend可达的API入口及服务鉴权 | 设置backend的URL/key并重启相关API、投递和Agent进程使配置生效 | 本地backend通过真实HTTP得到候选 |
| 4. 数据准备 | 保持派生存储、索引和worker可用 | 在独立业务测试环境走正常上传→索引→发布流程，导入pilot200；再导入有原文证据的关系 | 文件/hash、发布、块数、关系路径核对 |
| 5. 验收 | 配合worker重启、持久化及空目标恢复演练 | 重跑业务/文档/展开/混合4场景，版本失效和引用校验 | 两端可复现的结果、失败记录、恢复查询对比 |
| 6. 云端选型实验 | 提供候选服务端点、资源及费用记录 | 固定语料和dev题，对比检索质量/延迟/成本 | 同输入实验报告，确认正式profile后再扩大语料 |

第1—3阶段可以开始，不必等全部模型选型结束。第4—5阶段仍有未完成工作，不能因为服务启动或4项路由通过就宣布搬迁验收完成。整体门槛仍按已有 `corpus_200 / real_http / restore / versioning / agent_tools / build` 记录。

优先区分“在空服务器部署代码后重新入库”和“搬迁现有双库及发布状态”。前者需要在新环境建立自己的映射和发布收据；后者需要一致性导出和空目标恢复，当前仍待真实验收。不要把Git clone当作数据迁移。

## 本地backend连接字段

以下是已有backend配置字段；示意值需由部署双方确定，不能直接复制为生产凭据：

```dotenv
KNOWLEDGE_SERVICE_ENABLED=true
KNOWLEDGE_SERVICE_URL=<backend可达的Knowledge API地址或本地隧道入口>
KNOWLEDGE_SERVICE_KEY=<与Knowledge服务一致的私有key>
KNOWLEDGE_RETRIEVAL_PROFILE=lexical-v1
```

`AGENT_BACKEND_URL` 仍指向承载工具网关的业务backend，不改成Knowledge API。backend当前知识HTTP超时上限8秒、工具上限10秒；跨机延迟需要实测，不能只验容器内部localhost。云服务API/worker的数据库和索引地址使用云端内部地址，不使用开发电脑路径。

本地helper、语料/关系导入器及bundle工具有loopback/test目标限制。遇到拒绝远端地址时，不应直接删保护逻辑：先使用独立测试环境/受控隧道，或把远端部署支持作为单独改动并测试。现有自动恢复只支持lexical profile，混合索引不能假定可直接恢复。

## 数据库和embedding何时重新评估

先冻结一个可复现基线，再在服务器上比较。当前基线是“PostgreSQL派生数据及关系 + OpenSearch词法 + embedding/rerank关闭”。这只是已验证实现，不代表最终选型胜出。

| 项目 | 当前实现 | 后续变更成本与约束 |
|---|---|---|
| 知识服务PostgreSQL | 任务、投影、chunk/parent、关系、迁移与租约 | 改自建/托管通常先处理连接与兼容性；换成另一种数据库产品需要实现和迁移，不能只改URL |
| 检索引擎 | 已实现OpenSearch适配，真实验证词法 | pgvector/Qdrant等尚无等价实现；若改用，需要补适配、索引生命周期、范围过滤及回归 |
| 知识图谱 | 已实现PG有来源的有向关系和有界取回 | 先验收真实关系路径；Neo4j等是可评估方案，目前没有开箱即用的驱动切换 |
| Embedding | OpenAI兼容HTTP接口、query/document指令、维度等profile字段 | 可在服务器上比较提供方/模型；协议不兼容需新适配，同维度也不代表同向量空间 |
| Rerank | 可选HTTP适配 | 单独比较增益、额外延迟和费用，当前没有真实质量结论 |

模型或维度、归一化、query/document指令等profile变化必须建立新generation/索引、重新生成文档向量、验证再发布；查询向量必须与文档向量使用兼容profile。不能把旧索引留着只切换查询模型。

服务端完整embedding配置会开放 `hybrid-v1`，但还要正常生成并发布对应profile的数据，再将backend的 `KNOWLEDGE_RETRIEVAL_PROFILE` 切换为匹配的profile。填写key不等于完成混合检索迁移。生成回答用的Luna与embedding是两个独立配置和评测对象。

云端实验沿用200份pilot与固定100条dev请求；test题用于后续保留集验证。至少同时记录关键条款召回、引用正确性/无依据回答、关系条件满足情况、端到端p50/p95、索引耗时、失败率和调用成本。区域按实测决定；本轮没有选定云厂商、购买资源或给出正式机器规格。

## 接收方回填

- commit SHA、部署OS/架构、构建镜像及依赖digest。
- 服务拓扑和backend接入地址（不含key）、端口范围、数据卷位置。
- schema版本、实际导入数量、PG/索引块数和不一致数。
- 四场景Agent结果、版本变更/重启/恢复结果及未通过项。
- 模型/profile/区域实验结果和下一步决定。

第一份PR的交付状态应标为“可开展云端试部署，完整搬迁验收待补”。后续再提交目标服务器部署配置及实测回执，不把本地Docker结果写成云端成绩。
