# ShopSteward

[v6 模型推演：组员安装与复现](ml/README.md) · [前端、后端与 LangGraph 接入说明](docs/reports/forecast-v6-product-integration.md)

`YH` 分支已包含 v6 四组件模型、参考输入与推理代码。拉取后可直接验证推理结果，无需重新训练；界面统一标注“模型推演，仅供参考”。

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
