# Swagger / OpenAPI 契约使用说明

完整设计契约仍包含待实现业务；B0、首批前端查询和 B2-A Agent 已实现，当前源码导出40个已注册操作（36条路径）。Agent 的11个操作见 [agent-v1.openapi.json](agent-v1.openapi.json)，启动与对话流程见 [Agent README](../../agent/README.md)。开发 backend 已迁移至 0009 并切换至当前代码，Agent 仍关闭。启动见 [Backend说明](../../backend/README.md)，实施范围见 [实现清单](implementation-status.json)。

2026-09-07 Simulator 控制台已实现：默认服务 9 个操作（含 ready），开启本地控制台后 19 个操作。可配置 SANDBOX 输入已同步到共享设计契约；运行契约见 [simulation runtime](simulation.runtime.openapi.json)、[console runtime](simulator-console.runtime.openapi.json)，验收见 [结果](simulator-console-acceptance-result.json)。

B0-07组合验收没有新增接口或迁移；当前验证见[测试报告](../reports/b0-07-test-report.md)、[进程证据](b0-07-process-result.json)及[验证汇总](b0-07-verification-result.json)。历史B0-05/06证据保留原适用范围。

2026-09-07新增**7个前端只读接口**：身份/店铺发现、销售明细/日汇总、采购列表、收货明细和经营流水。[数据字典](../data-dictionary.md)、[设计规格](../superpowers/specs/2026-09-07-frontend-data-contract-design.md)、[补充设计OpenAPI](frontend-data.openapi.json)已落实；补充设计稿的planned标签保留为设计阶段记录，实际已实现状态以[runtime](backend.runtime.openapi.json)及实现清单为准。真实HTTP响应、分页、权限和SC01账本证据见[联调记录](frontend-data-http-result.json)与[测试报告](../reports/frontend-data-test-report.md)。

| 文件 | 用途 | 设计操作数 |
|---|---|---:|
| [backend.openapi.json](backend.openapi.json) | 前端、内部事件和开发演示接口，含 B2 草案 | 26 |
| [services.openapi.json](services.openapi.json) | simulation、预测、Agent、LLM 文本兼容子集 | 10 |
| [frontend-data.openapi.json](frontend-data.openapi.json) | 7个前端只读查询的设计基线；实际已实现，运行schema见runtime | 7 |
| [validate_contracts.py](validate_contracts.py) | 验证规范、引用、示例和项目契约约束 | 不运行业务服务 |

接口语义、事务、状态和实施顺序见 [Backend 开发文档](../backend-development.md)。

B0-04为共享Reference.type追加`alert`，警报历史可以关联具体episode；消费者应同步枚举。知晓接口没有请求body，actor由Bearer身份确定；已解除警报的新知晓命令返回409 ALERT_RESOLVED。

当前设计契约版本为 `0.2.0-draft`，标记仍为planned；实际实施由runtime快照和实现清单维护。B0-01增加仅用于本地诊断的worker_probe枚举。本次修订将 Plan.input_snapshot 改为完整 DecisionSnapshot，增加 proposed_purchase；报价包含版本/有效期/交期，ScenarioRun 包含 initial_catalog，EventPage 包含 source_head_sequence，并收紧受理/拒绝回执的条件字段。消费者应同步更新 mock 和类型，不能按旧版 State 快照解析 Plan。模拟状态、事件顺序与幂等恢复行为见 [Simulator 行为契约](../simulation-contract.md)。

各接口示例用于展示合法对象，并非串在同一版本号下的完整执行轨迹；SC01时间与事件顺序以行为契约为准。日期是固定演示值，运行时必须使用注入时钟和真实资源返回的有效期/hash。

## 1. 现在如何查看 Swagger

可将 JSON 文件导入支持 OpenAPI 3.1 的 Swagger Editor，或在本机通过官方 Swagger UI 容器查看。以下 PowerShell 命令在 ShopSteward 根目录执行，需要本机已有 Docker。

```powershell
$contractDir = (Resolve-Path -LiteralPath '.\docs\api').Path
docker run --rm --name shopsteward-api-docs -p 127.0.0.1:8088:8080 --mount "type=bind,source=$contractDir,target=/contracts,readonly" -e SWAGGER_JSON=/contracts/backend.openapi.json docker.swagger.io/swaggerapi/swagger-ui
```

浏览器打开 `http://localhost:8088`。查看外部服务契约时，在另一个终端运行：

```powershell
$contractDir = (Resolve-Path -LiteralPath '.\docs\api').Path
docker run --rm --name shopsteward-service-docs -p 127.0.0.1:8089:8080 --mount "type=bind,source=$contractDir,target=/contracts,readonly" -e SWAGGER_JSON=/contracts/services.openapi.json docker.swagger.io/swaggerapi/swagger-ui
```

浏览器打开 `http://localhost:8089`。这是本地文档预览，不启动 backend/simulation/ml/agent。命令使用官方默认镜像便于首次查看；团队正式部署和 CI 应记录并锁定验证后的镜像 digest。本文未替用户启动或下载容器。[Swagger 官方安装说明](https://swagger.io/docs/open-source-tools/swagger-ui/usage/installation/)

后续需要单页面选择多个契约时，可用 Swagger UI 的 `urls` 配置；两个契约应从同源静态目录提供。服务地址位于 OpenAPI servers，每个外部 operation 覆盖为所属服务地址。[Swagger UI 配置](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)

## 2. 当前运行时 Swagger

FastAPI进程已有 `/docs`、`/openapi.json`、health/monitoring/job/catalog查询、内部事件、开发初始化、Mission管理、Plan、警报、看板及timeline入口。其余业务仍按以下目标结构接入：

- `/docs`：真实运行时 Swagger UI。
- `/openapi.json`：仅从已注册路由生成的契约。
- `/api/v1/...`：前端接口。
- `/internal/v1/...`：服务身份接口。
- `/dev/v1/...`：仅开发环境与 admin 可用。

运行时不应把本目录的完整设计稿直接作为 app.openapi() 返回。B2 尚未实现时，真实 Swagger 不能显示这些路由为可用。生成行为参考 [FastAPI OpenAPI](https://fastapi.tiangolo.com/how-to/extending-openapi/)。

通过文档页面跨端口调用 backend 时，后端 CORS 必须精确允许文档 origin（如本地8088），并允许 Authorization、Content-Type、Idempotency-Key，暴露 X-Request-ID。浏览器中的 localhost 指浏览器所在机器，不是服务容器。认证失败和 CORS 失败应分别排查。

以下片段为历史设计示意；实际app/main.py已实现，当前路由以runtime快照为准：

```python
from fastapi import FastAPI

app = FastAPI(
    title="ShopSteward Backend API",
    version="0.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
    redoc_url=None,
    openapi_tags=[
        {"name": "Dashboard", "description": "经营状态与基础目录"},
        {"name": "Missions", "description": "任务与可追溯历史"},
        {"name": "Planning", "description": "版本化方案与候选比较"},
        {"name": "Execution", "description": "审批和采购回执"},
        {"name": "Alerts", "description": "风险生命周期"},
        {"name": "Scheduling", "description": "检查计划和异步任务"},
    ],
    swagger_ui_parameters={"displayRequestDuration": True},
)
```

开发路由时为每个操作显式设置 `operation_id`、`response_model`、`status_code` 和错误 `responses`。UserBearer/ServiceBearer 必须同时接入 FastAPI 安全依赖与实际授权检查；只向 OpenAPI 手工添加 securitySchemes 不会自动保护接口。

当前在backend目录执行 `uv run --frozen python -m app.export_openapi` 可导出 [运行时契约](backend.runtime.openapi.json)。以下为等价手工导出示例：

```powershell
uv run python -c 'import json; from pathlib import Path; from app.main import app; Path("../docs/api/backend.runtime.openapi.json").write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding="utf-8")'
```

导出只导入应用和注册路由，不连接模型、启动worker或执行数据库迁移；有副作用的初始化放受控生命周期/独立命令。`backend.runtime.openapi.json`当前由实际应用导出，包含29个操作（28条路径）；本批新增7个GET，不新增迁移或worker handler。

## 3. 字段与版本维护

- `openapi: 3.1.0` 是规范版本；`info.version: 0.2.0-draft` 是契约版本；`/api/v1` 是兼容系列。当前仍未发布业务服务，本次草案结构变化明确标记版本，不暗示已上线v1兼容。
- `x-phase` 区分 B0/B1/B2；`x-implementation-status: planned` 表示当前仅设计。
- 所有对象输入默认拒绝未知字段；外部 LLM 响应允许供应商扩展字段。
- null 使用 JSON Schema 联合类型；金额使用整数分；时区明确。
- 每个 operationId 稳定唯一，生成客户端后不要随意更名。
- 已批准方案的请求中不传金额、数量或审批人，避免客户端篡改权威字段。
- 不将秘密、真实服务 token 或真实个人资料写入 Swagger 示例。

## 4. 校验命令

从 ShopSteward 根目录运行：

```powershell
uv run --no-project --with openapi-spec-validator==0.7.2 --with jsonschema==4.23.0 python docs/api/validate_contracts.py
```

这是固定直接工具版本的临时验证环境，不把这些包加入 backend 的业务依赖。首次运行可能需要获取工具依赖；团队 CI 后续锁定完整传递依赖。若Windows默认uv缓存不可用，可在uv参数中增加 `--cache-dir "$env:TEMP\shopsteward-contract-cache"`。

已有项目虚拟环境时，可分别校验原契约和前端补充契约：

```powershell
.venv/Scripts/python.exe docs/api/validate_contracts.py
.venv/Scripts/python.exe docs/api/validate_frontend_data_contract.py
```

后者核验设计基线的7个GET与实际路由/实现清单匹配、22个设计schema、14个响应示例、8个runtime共享schema一致，以及销售/到货/SC01账本算术、10个schema负例和4个跨字段负例。成功示例还按runtime schema校验。真实HTTP验收可在根目录运行`.venv/Scripts/python.exe backend/tools/verify_frontend_reads.py`：要求8014空闲及B0-07持久化SC01场景仍在；仅启动自有API并读取该场景，使用临时viewer/service身份，最后停止API。它不创建场景或推进模拟器，结果写入[联调记录](frontend-data-http-result.json)。

校验器检查：OpenAPI 3.1 结构、JSON Schema、全部本地引用、operationId 唯一、路径参数、阶段标记、写命令幂等头、外部服务地址、媒体类型示例、共享 schema 一致性，并核算示例 Plan 的规范化hash及采购/快照数值一致性。负例覆盖旧版快照、缺失采购/报价/分页字段、受理缺订单号、拒绝缺原因。它不代替实际 HTTP、权限、数据库并发或业务测试，也不提供业务运行实现。

## 5. 实现时的契约验收

1. 选定工作包 B0-01～B0-07，并确认本次实现的 operationId。
2. 添加 Pydantic 模型、实际路由和错误处理，字段与设计稿保持一致。
3. 从应用导出 OpenAPI；仅比较承诺已实现的操作和可达 schema。
4. 对比 required、type、enum、nullable/null、权限、请求头和状态码；忽略无语义的对象键顺序。
5. 用真实请求校验成功响应和错误响应。特别验证409版本冲突、422字段错误和202异步受理。
6. 更新实现状态及生成快照，再交付前端联调。

两个契约中共享的 State、事件、回执等结构暂各自内联，以便单文件导入。校验器比较相同名称 schema，防止漂移；实现后从模块公共 DTO 生成，避免手工维护副本。

B0-05后质量收口：所有21个运行时操作均有x-phase=B0及x-implementation-status=implemented，由B0Router统一登记。补齐原先遗漏的list_alerts、acknowledge_alert、get_dashboard、list_mission_timeline；统一错误模板包含409。请求/响应schema和operationId保持一致，元数据完整性有API回归测试。
