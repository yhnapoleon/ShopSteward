# ShopSteward

项目目录骨架：Nuxt 前端、Python 后端、独立 Worker，以及可选预测服务。

**当前仅包含文件夹和基础配置，不包含页面内容、业务逻辑、模型实现、示例数据或测试用例。** 空目录使用 `.gitkeep` 保留，后续开发时可移除。

| 目录 | 用途 |
|---|---|
| `apps/web` | Nuxt 前端 |
| `apps/backend` | FastAPI、LangGraph、Worker 及内部业务模块 |
| `services/forecast` | 可独立部署的预测服务 |
| `packages/api-client` | 前端 API 客户端与生成类型 |
| `packages/forecast-contracts` | 预测请求与响应契约 |
| `packages/forecasting` | 可复用预测实现 |
| `ml` | 数据处理、训练、评估与实验配置 |
| `skills_seed` | 项目预置技能 |
| `scenarios` | 场景及验收输入 |
| `evaluation` | Agent、学习与经营评价 |
| `contracts/generated` | 生成的接口规范 |
| `infra` | 容器、代理与部署配置 |
| `scripts` | 开发、启动和维护脚本 |
| `data` | 本地数据集 |
| `var` | 数据库、上传、产物、技能版本、模型与日志 |
| `docs` | 项目文档 |

[架构分层图](docs/architecture.md)

JavaScript 使用 pnpm workspace，Python 使用 uv workspace。运行入口和部署文件尚未编写，目前不提供完整系统启动命令。
