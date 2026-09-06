# 简化架构与分工

按交付模块划分，backend的B0-01、B0-02核心、B0-03及B0-04已实现；Mission、规划、警报、看板和历史可用，审批采购和周期调度待开发。实际启动见 [Backend说明](../backend/README.md)。后端内部聚类与开发契约见 [Backend 开发与接口规范](backend-development.md)，接口预览见 [Swagger / OpenAPI](api/README.md)。以下按“先做 backend，Agent/RAG 后接”的最新安排更新职责。

## 模块职责

| 目录 | 负责什么 | 对外提供什么 |
|---|---|---|
| frontend | Nuxt 页面、交互、执行进度展示 | 用户提交与结果展示 |
| backend | HTTP API、业务任务调度与恢复、库存和现金账本、采购规则与批准校验 | 前端接口与 Agent 业务工具接口 |
| agent | 推理编排、图检查点与恢复、LLM 调用、记忆和技能学习 | 后续接收任务触发，推进推理并回传进度与结果 |
| ml | 预测数据处理、训练、评估与推理；需要时提供独立预测服务 | 有版本和数据截止时间的预测结果 |
| simulation | 合成经营场景、模拟时间、需求、到货、销售和结算事件；模拟外部动作结果 | 场景重置、时间推进、事件与执行回执 |
| infra | Docker、环境配置、启动脚本、部署与联调配置 | 一致的开发与运行环境 |
| docs | 架构、接口契约、数据字段、分工、实验说明 | 团队共同遵循的约定 |
| tests | 跨模块集成与 A-01 / SC-01 / L-01 验收 | 检查整条业务链是否连通、正确 |

## 模块交互

```mermaid
flowchart LR
    F[frontend / Nuxt] -->|用户请求| B[backend / API 与业务服务]
    B -->|持久业务调度| W[backend / Worker]
    W -.->|后续任务触发与结果核对| A[agent / 推理编排]
    A -->|调用业务工具、记录进度| B
    B -->|需求预测| M[ml / 预测能力]
    B -->|模拟外部动作| S[simulation / 经营环境]
    S -->|事件与回执| B
    A -->|文本推理| L[外部或自部署 LLM]
```

## 分工时需要共同确定的边界

1. **backend 与 agent：**backend 保存经营事实和任务记录，负责业务检查调度、动作权限和采购核对；agent 后续负责推理任务并保存自己的图检查点与记忆。两者通过 agent_run_id 关联恢复状态。现金或库存不能由模型直接改写，Agent 未启用时后端仍能独立运行。
2. **backend 与 simulation：**simulation 模拟店铺外部世界及动作结果；backend 根据带唯一 ID 的事件/回执更新经营账本。状态归属、初始状态导入、事件顺序和去重规则在接口文档中写明，避免同一次销售或到货重复记账。
3. **backend 与 ml：**ml 返回预测，backend 负责现金约束、方案推演和采购比较。LLM 客户端归 agent，销量预测模型归 ml。
4. **infra 与业务对接：**infra 负责让模块启动、联网和部署；业务 API、模型调用和模拟器适配代码归各调用方，接口约定放 docs。

这些是代码所有权边界，不等于八个独立部署服务。B0 联调采用 API、worker、单一持久 HTTP simulation 与 PostgreSQL；ml 首先使用 backend 的 fixed provider。simulation 可与 backend 共用 PostgreSQL 实例，但表、迁移和状态所有权独立，不共享业务事务。进程内 simulation fake 仅用于开发/单元测试，不能在 API 和 worker 内各建一份可变世界。

后端可以先开发，不必等完整模拟平台。先固定 [Simulator 行为契约](simulation-contract.md)，再交错实现 backend 最小业务链与 simulation 的五个接口；首次采购联调前接入持久模拟器。payload 字段之外，必须共同约定事件序号、一次性效果、采购核对、时间推进和双方重启语义。

## 四人认领建议

| 工作包 | 主负责 | 协作 |
|---|---|---|
| 产品与整合 | frontend、infra | 汇总 docs、组织 tests |
| 业务与环境 | backend、simulation | 与 Agent/模型负责人对齐输入输出 |
| Agent 与学习 | agent | 与 backend 对齐任务、工具、批准与恢复 |
| 预测与实验 | ml | 共同完善 simulation 场景及效果评价 |

各模块负责人共同补充 docs 和 tests。若业务与环境工作量过重，可由预测负责人认领模拟需求与场景部分；不为分工方便而复制业务状态或计算规则。
