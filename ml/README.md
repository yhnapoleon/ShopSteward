# Portable v6 ML service

## 组员快速复现（Windows / Linux / macOS）

这里复现的是**已训练 v6 的推理结果**，不需要 GPU、数据库、LLM API key、原始数据集或旁边的研究工作树。模型推演，仅供参考。

安装 Python 3.12 和 uv 后，从新目录执行：

```shell
git clone --branch YH https://github.com/yhnapoleon/ShopSteward.git
cd ShopSteward
uv sync --frozen --package shopsteward-ml --extra runtime --extra dev --python 3.12
uv run --frozen --package shopsteward-ml --extra runtime --extra dev python ml/tools/reproduce_v6.py
uv run --frozen --package shopsteward-ml --extra runtime --extra dev python -m pytest ml/tests -q
```

验证脚本应输出 `verification: PASS`、模型 `shopsteward-v6-1885`、七日原始合计约 **12.039875**、整周需求 **13 件**。测试还核对全部 300 个系列、四组件推理与参考结果的一致性（容差 `1e-6`）。这里的 13 件是固定示例结果，不是所有商品的通用需求。

模型已随 Git 提交至 `var/forecast-v6/bundle`（约 22 MB），无需 Git LFS 或额外下载权重。`.gitattributes` 保留模型包原始字节，运行时检查 manifest 的 SHA-256；不要手工格式化包内 JSON 或树模型文件。Linux 若提示缺少 `libgomp.so.1`，安装系统 OpenMP 库；macOS 的 LightGBM 可能需要 `brew install libomp`。首次安装的 Torch 依赖体积可能较大。

## 启动独立模型 HTTP 服务

先在当前终端设置随机的 `ML_SERVICE_TOKEN`（后端的 `FORECAST_V6_TOKEN` 要使用相同值），然后运行：

```shell
uv run --frozen --package shopsteward-ml --extra runtime --extra dev python -m uvicorn shopsteward_ml.service:create_app --factory --host 127.0.0.1 --port 8053
```

PowerShell 设置方法为 `$env:ML_SERVICE_TOKEN='你的随机本地token'`；bash/zsh 为 `export ML_SERVICE_TOKEN='你的随机本地token'`。token 不需要任何外部账号，不要提交真实 token。服务默认读取仓库内模型包。

## 接到组员自己的 ShopSteward

按 `backend/README.md` 和前端说明先配置自己的数据库、登录身份及模拟器。后端 `.env` 增加：

```dotenv
FORECAST_V6_ENABLED=true
FORECAST_V6_URL=http://127.0.0.1:8053
FORECAST_V6_TOKEN=与模型服务相同的随机token
```

后端目录执行 `alembic upgrade head`，迁移到 `0014_forecast_work_merge`（同时包含预测、Agent 进度和事项承接迁移；已有任一分支的数据库均可升级）。启动后首页可选模型系列并“运行模型推演”；LangGraph 启用且配置了组员自己的 LLM key 时可调用 `get_forecast`。Windows 总启动器 `infra/start_windows.py` 会启动模型服务；此时不要提前单独占用 8053，且 `ML_PYTHON` 应指向组员本机安装了 ML 依赖的 Python。完整公开 API 及输入格式见 [接入报告](../docs/reports/forecast-v6-product-integration.md)。

以下是原实现说明；其中研究目录命令只用于重新打包，不是组员运行模型的前置条件。

## Implementation

This service runs the frozen F6 (0.5), F3 (0.25), W2 (0.125) and N3 (0.125)
components from the completed experiment. It does not train or import research
runners. `_features_*`, `_state`, `_constants`, `_trees_v6` and `_neural` contain
selected unchanged inference kernels, extracted by `tools/vendor_v6_runtime.py`.

Install this package with its `runtime` extra into a dedicated ML Python environment;
for a CPU-only installation install Torch from the official CPU wheel index first.
The main backend does not need Torch. Building bundles/tests additionally need the
`dev` extra (PyArrow is only used by the offline packager).

On this workstation, from the main ShopSteward directory:

```powershell
. ./infra/use_local_storage.ps1
$env:PYTHONPATH = (Join-Path (Get-Location) 'ml/src')
$env:ML_V6_BUNDLE = (Join-Path (Get-Location) 'var/forecast-v6/bundle')
$env:ML_SERVICE_TOKEN = '<same token as backend FORECAST_V6_TOKEN>'
& ../ShopSteward-forecast/.venv/Scripts/python.exe -B -m uvicorn shopsteward_ml.service:create_app --factory --host 127.0.0.1 --port 8053
```

Use `Authorization: Bearer <token>` for every endpoint:

- `GET /health/ready`: verifies the bundle was integrity checked and all four models loaded.
- `GET /v1/model`: 300 supported identities, weights and historical evaluation limits.
- `GET /v1/demo-history/{series_id}`: explicitly requested historical demo only, 374
  days ending 2016-03-27 (d1885). No post-cutoff actual sales are packaged.
- `POST /v1/predict`: strict request input described in the product integration spec.
  Inputs must be ordered, contiguous, complete, nonnegative integer piece sales for
  84–374 days. The final date must equal `observation_end_date`. No zero filling,
  future sales, fallback model, or automatic demo-history lookup occurs.

`horizon_start` is local midnight after the observation date; `horizon_end` is
exclusive midnight seven days later. Daily dates are local calendar dates.
`generated_at` and `valid_until` are UTC wall time, with a 24-hour evidence lifetime;
the backend must independently match the forecast horizon to business time.
`predicted_quantity` applies one ceiling to the raw weekly sum, never one per day.
The stable forecast ID binds the full request and bundle manifest (including hashes).

The default bundle location is `var/forecast-v6/bundle` relative to process cwd.
This directory is included in Git. To transfer deployments, copy it and the ML package; the research
checkout and raw dataset are not required for serving. Each component retains its
own mapping. On startup every manifest-listed file is SHA-256 checked. Reference
files hold historical model outputs for tests only and contain no future actuals.

To rebuild from the original experiment into a new empty directory (no retraining):

```powershell
& ../ShopSteward-forecast/.venv/Scripts/python.exe -B ml/tools/build_v6_bundle.py ../ShopSteward-forecast var/forecast-v6/new-bundle
& ../ShopSteward-forecast/.venv/Scripts/python.exe -B -m pytest ml/tests -q
```

Tests cover all 300 series and all four components against saved first-review-origin
predictions, authenticated HTTP via TestClient, invalid inputs, explicit future-row
feature invariance, timezone boundaries, and minimum-history inference. Historical
review is reused from v5: WAPE 34.976%, relative v5 improvement about 0.57%; the
additional four weeks are slightly worse than v5. This is not an independent
production validation, and selected M5 identity is an explicit external-SKU proxy.
