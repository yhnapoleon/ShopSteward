# v6 Product Integration Plan

> For agentic workers: use superpowers:subagent-driven-development; user authorized direct execution.

**Goal:** v6从前端到后台、规划依据及LangGraph可用。
**Architecture:** 独立ML服务，backend持久预测，LangGraph只读同一证据，前端使用公开API。
**Tech Stack:** 当前FastAPI/SQLAlchemy/PostgreSQL、LangGraph、Nuxt/Vue、现有Python ML环境。
**Spec:** docs/superpowers/specs/2026-09-11-v6-product-integration.md

## Global Constraints
不重训、不覆盖旧研究结果；不把历史演示自动作为真实店铺需求；不改现有采购审批。主ShopSteward目录按用户接入要求编辑，仅任务范围文件。Python沿用D盘缓存脚本及forecast工作树venv，测试时PYTHONPATH优先主目录backend/agent，不能误测旧工作树。

- [x] ML适配器/服务/打包：ml新运行代码、模型bundle、API严格验证、真实模型对齐测试、可启动8053。
- [x] Backend：forecast_v6模块/迁移/配置/路由/持久快照/refresh事务界限/规划读取、权限及时效测试。
- [x] LangGraph：tools/evidence_policy/composition接get_forecast、当前引用验证、必读与不可用测试。
- [x] 前端：ForecastPanel/首页/Agent引用入口、导入与演示、状态与竞态测试、类型及构建。
- [x] 集成：契约生成、专用数据库迁移、真实HTTP/模型/graph链路验收，启动配置与runbook，清晰记录未覆盖条件。

验收及运行说明：`docs/reports/forecast-v6-product-integration.md`。按用户最新要求，界面与Agent统一称为“模型推演，仅供参考”；日期保留在详情，内部模式与规划适用规则不变。

执行分工：ML、Backend、Frontend各独立实现，根代理负责LangGraph与集成审查。源码与启动配置可迁移；本机bundle路径不能只指向一次性实验临时目录。用户后续要求组内复现，冻结模型包现随 Git 发布，其他运行日志、缓存和密钥仍排除。
