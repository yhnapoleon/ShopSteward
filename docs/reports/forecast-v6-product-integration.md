# v6 接入说明与验收记录

2026-09-11，目标为主目录 `ShopSteward` 的 YH 分支。研究工作树与实验结果未改动，未重新训练。

## 已接通的产品链路

`ForecastPanel → 前端代理 → 后端 forecast_v6 → 独立 ML 服务 → 持久化预测 → LangGraph get_forecast → 结构化引用`。

前端首页“七日需求预测”展示七日曲线、逐日数量、整周一次向上取整的合计、模型版本、质量说明与输入入口。用户可选择模型参考系列运行推演，或导入当前商品的完整销售历史。按最新用户要求，面向用户统一使用“模型推演，仅供参考”，原始日期保留在可展开详情，不将日期改写为当前日期。

LangGraph 对明确的预测/模型推演或补货问题按 `get_dashboard → get_forecast → get_plan`（需要方案时）取证。`get_forecast` 无参数，门店和商品来自当前 Mission；前端和 Agent 使用同一份已保存预测。回答前再次校验预测标识、版本、门店、商品、模式和有效状态。Agent 只接收七日结果、输入覆盖范围和模型摘要，不携带全部历史及 300 个系列目录。

## 给前端及调用方的接口

公共路径以前缀 `/api/v1/stores/{store_id}/forecast` 开始；Nuxt 浏览器端通过 `/api/backend` 代理。沿用已有身份认证及门店权限，服务 token 不进入浏览器。

| 方法和后缀 | 用途 | 权限 |
|---|---|---|
| GET `/model` | 模型版本、权重、支持系列、历史长度与评估说明 | viewer/operator/admin |
| GET `?sku_id=...` | 当前已保存预测及输入、状态、适用范围 | viewer/operator/admin |
| POST `/refresh` | 推理并保存预测；输入更新后复核经营状态 | operator/admin |

首次模型推演请求：

```json
{
  "sku_id": "sku_001",
  "series_id": "FOODS_1_014_CA_1",
  "mode": "historical_demo",
  "activate_for_planning": false
}
```

`historical_demo` 是保留的内部协议值，界面称为模型推演。`observed` 模式另传 `history` 与 `observation_end_date`。历史是 84–374 个连续完整日，建议 374 日；每行 `{date:"YYYY-MM-DD",sold_quantity:非负整数,complete:true}`，最后一天须等于截至日。不能以缺失销售记录补零。`series_id` 是已训练类别映射的参考系列，需要明确选择，并不意味着新商品已获独立效果验证。

复用输入只需传 `sku_id` 与保留的 `activate_for_planning`；前端已保存该开关，不会因普通刷新而悄悄关闭。请求失败不会覆盖上一次成功结果。

返回 `ForecastV6Current`：`status=READY|STALE|UNAVAILABLE`、`reason`、门店商品、`mode`、`activate_for_planning`、`usable_for_planning`、`forecast`、`history`、`model`。预测包含 `forecast_id/model_version/feature_profile`、观察截至日、七日范围（结束时点不包含）、每日浮点数量、`total_quantity_raw`、`predicted_quantity`、生成/到期时间和评估说明。未绑定返回 UNAVAILABLE；经营状态变化、到期、observed 业务日期不匹配返回 STALE，并保留可追溯结果。

实际 OpenAPI：`docs/api/backend.runtime.openapi.json`；生成的 TypeScript：`frontend/app/types/backend.d.ts`；生成代理 allowlist：`frontend/server/utils/backend-routes.ts`。同步修复了已有文档上传 metadata 中嵌套 `$defs` 引用，保证整份契约可生成。

## 规划和模型边界

现有规划引擎能读取 v6。只有 `observed`、明确开启规划、当前预测有效且业务时点正好等于预测首日 UTC 午夜时，才把七日合计写入规划快照。初版不猜测日内剩余销量。未开启的场景继续使用已有固定预测；模型推演用于参考。采购仍走现有逐笔确认流程。

成功刷新使门店 `state_version` 增加，旧方案因此失效。规划快照的 `forecast_version` 仍追踪原经营投影；`forecast_id/model_version` 明确标识 v6 依据。没有伪造旧 `offline_model_validated` 标志。

模型版本 `shopsteward-v6-1885`，配方 F6 0.5、F3 0.25、W2 0.125、N3 0.125。已有评估八周 WAPE 34.976%，相对 v5 改善约 0.57%，额外四周略差；这些结果不等价于新门店保证。便携模型包在 `var/forecast-v6/bundle`，约 21.8 MiB，318 个文件；已按用户要求随 Git 发布，组员拉取后无需额外下载权重。推理不依赖原研究代码或原始数据集。

## 本机启动与维护

组员新环境请优先使用 [ML README](../../ml/README.md) 中的克隆、锁定安装与 `reproduce_v6.py` 命令。以下记录是最初接入工作站的运行方式，不是其他成员的前置条件。

已配置本机私有 `backend/.env`：启用 v6，模型服务为 `127.0.0.1:8053`，独立 token；沿用既有 Luna 配置。开发数据库迁移到 `0012_forecast_v6`。现有模型虚拟环境被复用，`ML_PYTHON` 在私有配置内指向它；代码通过明确 PYTHONPATH 使用主目录。

从主目录 PowerShell 启动（Docker Desktop 先运行；端口已运行时不要重复启动）：

```powershell
. ./infra/use_local_storage.ps1
& ../ShopSteward-forecast/.venv/Scripts/python.exe infra/start_windows.py
```

启动器同时启动 ML、API、业务 worker、Agent worker、前端及需要时的模拟器；后台隐藏窗口，自有 PID 和日志保存在 `var/windows-*`。端口：前端 3000、API 8000、模拟器 8001、ML 8053、PostgreSQL 55432。只重启已核对身份的自有进程，不结束未知占用进程。

其他环境可安装 `ml` 的 `runtime` extra 到独立 ML Python（CPU Torch 即可），配置 `ML_PYTHON`、`ML_V6_BUNDLE` 与 `FORECAST_V6_*`。完整 ML HTTP 与打包方法见 `ml/README.md`。`uv.lock` 已更新并通过离线一致性检查。

重新生成契约：

```powershell
$env:PYTHONPATH = "$PWD/backend;$PWD/agent/src;$PWD/ml/src;$PWD/simulation"
& ../ShopSteward-forecast/.venv/Scripts/python.exe -m app.export_openapi --output docs/api/backend.runtime.openapi.json
node frontend/scripts/generate-api.mjs
```

## 验证证据

- ML 22 项测试通过，包含 300 个系列全部四组件与保存预测的 `1e-6` 一致性、真实模型 HTTP、严格输入和因果特征检查。
- 后端与 Agent 现有单元回归 277 项通过、3 项可选测试跳过；修正后针对 API、取证、引用及契约的 74 项测试通过（与前项部分重叠）。
- v6 PostgreSQL 集成 3 项通过，规划/执行既有集成 30 项通过：不可变记录、禁止推演激活、午夜规划、失效方案拒绝均已验证。
- 前端类型检查、生产构建、API 生成检查通过；7 项预测交互用例覆盖导入、权限、失效、切店竞态、引用、刷新保留开关及模型推演表述。
- 本地真实 HTTP 和 Nuxt 代理返回相同 `forecast_id`。实际 Luna 的 LangGraph 已完成库存→预测→方案并保存回答及预测引用；调度结果中的引用转成通用 artifact，完整引用仍留在回答中。
- 真实运行记录保存在 `var/forecast-v6/live-smoke.json`；浏览器实际看到 READY、13 件、曲线与逐日数据。当前默认门店示例商品已准备一份模型推演，可直接打开首页体验。

这次完成的是产品接入，不增加训练质量承诺，也未执行采购。
