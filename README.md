# ShopSteward

<!-- md-alignment-2026-09-08 -->
## 当前实现入口（2026-09-08增补）

任务工作区第一阶段已通过[PR #11](https://github.com/yhnapoleon/ShopSteward/pull/11)合并；真实工具进度、历史证据、试算/修订成果及原件下载/代码块复制通过[PR #12](https://github.com/yhnapoleon/ShopSteward/pull/12)合并为 `1bbcad5`。从[当前交接](HANDOVER.md)与[三阶段组合交付](docs/reports/agent-workspace-delivery.md)读取实际能力、迁移和验证边界。

第二、三阶段包含必要的后端桥接、接口与持久记录改动，业务库要求 `0012_agent_progress`；没有改动既有规划、账本、审批执行、Mission、业务调度和Agent主体源码。模型启用情况按运行环境核对，合并不代表完整A-01/L-01或部署验收。

下方“B0-01至B0-05”“下一步B0-06”“Agent后续接入”“21个操作”“空目录”等文字与目录示意保留初始搭建时点；不再作为当前进度或完整目录清单。模块职责和原有启动入口继续保留。
<!-- /md-alignment-2026-09-08 -->

[项目总说明与对话交接](PROJECT_CONTEXT.md)：新对话先读，包含架构、资料与参考项目索引，以及主干设计/实施状态。

按团队职责划分的项目。backend已完成B0-01至B0-05：业务事实、Mission/规划、警报/看板/历史、审批采购与回执核对；显式推进的完整SC01已验证。下一步为B0-06周期调度。

```text
ShopSteward/
├─ frontend/             # Nuxt 前端
├─ backend/              # API、业务规则、数据库
├─ agent/                # 推理编排、LLM、记忆与技能（后续接入）
├─ ml/                   # 预测模型的训练、评估与服务
├─ simulation/           # 模拟经营环境与场景
├─ infra/                # 部署、环境配置、启动与联调脚本
├─ docs/                 # 架构、接口约定、分工与项目文档
├─ tests/                # 跨模块集成与验收测试
├─ package.json
├─ pnpm-workspace.yaml
├─ pyproject.toml
└─ .gitignore
```

[职责与架构图](docs/architecture.md)

[Backend 开发与接口规范](docs/backend-development.md) · [Swagger / OpenAPI 契约](docs/api/README.md)

[Simulator 行为契约与协作顺序](docs/simulation-contract.md)：先固定 payload 与行为，backend 和最小持久 HTTP simulator 交错开发，尽早贯通第一次采购。

后端采用独立API与worker，已实现health、monitoring、任务查询、PostgreSQL迁移和持久技术探针，并支持catalog、初始化、事件入账、Mission管理、方案、警报、看板和历史查询。新增精确审批、Action查询和场景推进，真实Swagger显示21个已注册操作，完整设计稿仍包含计划接口。

[Backend启动、测试与当前边界](backend/README.md) · [实际接口清单](docs/api/implementation-status.json)

前端使用 pnpm，Python 模块使用 uv workspace。各模块内部等实际开发需要时再增加子目录。目录划分用于分工，不要求每个目录都部署为独立服务。

其余空目录以 `.gitkeep` 保留。backend运行入口为 `python -m app` 和 `python -m app.worker`（backend目录执行），完整配置与启动见Backend说明。
