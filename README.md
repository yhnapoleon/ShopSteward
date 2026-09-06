# ShopSteward

按团队职责划分的简化目录骨架。当前只保留空目录、基础配置和说明，不包含具体功能。

```text
ShopSteward/
├─ frontend/             # Nuxt 前端
├─ backend/              # API、业务规则、数据库
├─ agent/                # LangGraph、Worker、记忆与技能
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

前端使用 pnpm，Python 模块使用 uv workspace。各模块内部等实际开发需要时再增加子目录。目录划分用于分工，不要求每个目录都部署为独立服务。

空目录以 `.gitkeep` 保留。运行入口尚未编写，当前不提供系统启动命令。
