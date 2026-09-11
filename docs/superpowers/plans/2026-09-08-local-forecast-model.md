# B1-A 数据、训练与本地推理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付M5固定实验、三基线与本地LightGBM制品，以及可被backend调用的真实预测HTTP服务。

**Architecture:** 原始数据、标准数据和制品分别保存；训练与服务复用同一特征函数，按预测起点限制标签可见性。服务只读加载显式制品版本、处理给定历史，不连接业务库或训练目录中的未来观测。

**Tech Stack:** Python >=3.11、uv、pandas、NumPy、PyArrow、LightGBM CPU、FastAPI/Pydantic、pytest、httpx、tzdata。

**Spec:** [设计第1～6节](../specs/2026-09-08-local-forecast-design.md)。

## Global Constraints

- 模型不直接决定采购量，不计算或更改现金账本，不审批，不使用 RAG 文本直接改预测。
- 全部门槛完成前状态为b1_ready=false。
- 500序列、种子20260908、h=1..7；时间分区/特征/门槛严格按设计，不按测试结果修改。
- 原件与模型仅存Git忽略的var/forecast；Git保存manifest和合成测试夹具。
- 本计划所有新增函数、CLI和文件均为待实现接口，以下命令在对应任务完成后才可执行。

---

## 文件与接口地图

新包`ml/src/shopsteward_ml/`：`data.py`负责M5读取/验证/标准化；`splits.py`负责manifest/切分；`features.py`负责origin特征；`baselines.py`负责三基线；`training.py`负责训练；`evaluation.py`负责指标/比较；`artifacts.py`负责制品；`schemas.py`负责服务DTO；`predictor.py`负责同源推理；`service.py`负责HTTP；`cli.py`负责命令；`__init__.py/__main__.py`负责入口。

配置使用`ml/configs/m5-pilot.json`，避免新增YAML依赖；所有相对输出路径相对仓库根解析。公开原件可从官方入口下载，也可用CLI接受用户已有的三个原件；不要求backend持有Kaggle凭据。锁文件在根uv.lock，模型依赖只挂到ml包。

关键函数签名在各任务中定义；数据类型使用pandas.DataFrame，外部HTTP只使用Pydantic DTO，不向backend传DataFrame或框架对象。

### Task A1: 数据原件、标准表与500序列清单

**Files:** Create `ml/src/shopsteward_ml/{__init__,__main__,cli,data,splits}.py`、`ml/configs/m5-pilot.json`、`ml/tests/test_data.py`、`docs/evaluation/forecast/README.md`；Modify `ml/pyproject.toml`、根`uv.lock`、`.gitignore`。

**Interfaces:** `prepare_m5(raw_dir: Path, output_dir: Path, config: dict) -> dict`返回含文件hash/行数/日期/series清单的manifest；`validate_sales(frame: DataFrame) -> None`对重复键、负数、小数和非有限数值抛ValueError。输出标准表字段固定为设计§3.2。

- [ ] 先用合成最小表验证单位与重复键，测试不需要真实数据下载：

```python
import pandas as pd
import pytest
from shopsteward_ml.data import validate_sales

def test_sales_reject_fractional_piece():
    frame = pd.DataFrame([dict(series_id="s", date="2016-01-01", sold_quantity=0.5)])
    with pytest.raises(ValueError, match="INTEGER_PIECES_REQUIRED"):
        validate_sales(frame)
```

- [ ] 运行`uv run --package shopsteward-ml pytest ml/tests/test_data.py -q`，确认缺功能失败。
- [ ] 将ml改为可安装src包，配置pytest测试依赖，CLI新增`prepare --raw-dir --output-dir --config`；实现原件hash、三表键检查、可用性记录、设计定义的500序列抽样与Parquet输出。原件网络取得失败只报告缺文件，不生成替代数据。
- [ ] 配置写入：`series_count=500,seed=20260908,min_available_days=365,min_nonzero_days=28,history_days=365,train_window_days=730,horizon_days=7,validation_days=56,test_days=56,feature_profile=sales-calendar-v1`。
- [ ] 运行测试后执行正式准备：`uv run --package shopsteward-ml python -m shopsteward_ml prepare --raw-dir var/forecast/data/raw --output-dir var/forecast/data/prepared --config ml/configs/m5-pilot.json`。输出`standard.parquet,m5-manifest.json,series-manifest.json,split-manifest.json`，复制小manifest到docs/evaluation/forecast。
- [ ] 检查500条清单由训练期统计产生，删一个原件字节后hash检查失败；报告缺失/未上架/零销量数量。聚焦diff后提交`feat(ml): add reproducible M5 preparation`。

### Task A2: 切分与训练/推理一致的特征

**Files:** Create `ml/src/shopsteward_ml/features.py`、`ml/tests/test_features.py`、`ml/tests/test_splits.py`；Modify `splits.py`；Produce `docs/evaluation/forecast/feature-schema.json`。

**Interfaces:** `cutoffs(last_day: int) -> dict[str,list[int]]`；`eligible_label(origin: int,horizon: int,cutoff: int)->bool`；`build_origin_features(history: DataFrame, origin_date: date, horizon_step: int, series_metadata: dict, calendar: DataFrame)->dict`；`make_training_rows(frame: DataFrame,cutoff:int,config:dict)->DataFrame`。所有偏移均相对origin，目标日取origin+h。

- [ ] 写入关键泄漏断言：

```python
from shopsteward_ml.splits import cutoffs, eligible_label

def test_labels_cannot_cross_training_cutoff():
    assert eligible_label(100, 7, 106) is False
    assert eligible_label(100, 7, 107) is True

def test_final_windows_are_frozen():
    split = cutoffs(1941)
    assert split["validation"] == list(range(1829, 1885, 7))
    assert split["test"] == list(range(1885, 1941, 7))
```

- [ ] 运行`uv run --package shopsteward-ml pytest ml/tests/test_splits.py ml/tests/test_features.py -q`确认失败。
- [ ] 实现target日历、5个offset、7/14/28滚动统计、类别编码与最少56日检查。训练表保存origin_date,target_date,horizon_step,cutoff,feature_profile；训练期fit类别编码，推理只transform。内层early-stop切分也通过eligible_label过滤，不随机train_test_split。
- [ ] 在合成单调序列上断言offset0为当天值、offset6为7天窗口首值；把所有未来销量改成999999，当前origin特征逐字段相同；跨店同SKU、同店不同SKU不能串历史；缺日拒绝，真实0保留。
- [ ] 对真实数据随机抽100个origin，训练构造与推理构造的特征完全一致；保存验证结果。提交`feat(ml): add causal multi-horizon features`。

### Task A3: 基线和统一指标

**Files:** Create `baselines.py`、`evaluation.py`、`ml/tests/test_baselines.py`、`ml/tests/test_metrics.py`；Modify `cli.py`。

**Interfaces:** `baseline_forecast(history: list[float],horizon:int,method:str)->list[float]`，method取mean7/mean28/seasonal7；`score_rows(rows: DataFrame)->dict`输入列series_id,origin,horizon_step,actual,predicted,group；`promotion_check(model:dict,baseline:dict)->dict`返回pass/reasons而非自动部署。

- [ ] 写测试区分累计误差与逐日误差：

```python
import pandas as pd
from shopsteward_ml.evaluation import score_rows
from shopsteward_ml.baselines import baseline_forecast

def test_weekly_total_does_not_hide_daily_error():
    rows = pd.DataFrame([
        dict(series_id="s",origin=1,horizon_step=1,actual=0,predicted=2,group="low"),
        dict(series_id="s",origin=1,horizon_step=2,actual=2,predicted=0,group="low")])
    value = score_rows(rows)
    assert value["weekly_mae"] == 0
    assert value["daily_mae"] == 2

def test_seasonal_baseline_uses_known_last_week():
    assert baseline_forecast(list(range(1,29)),7,"seasonal7") == list(range(22,29))
```

- [ ] 运行聚焦测试确认失败；实现同一窗口评估、分组、bias空分母处理、固定种子配对时间块bootstrap、5%/10%阈值。总量先累加浮点再计算预测指标；业务取整误差另报，不把取整后的改善冒充原模型提升。
- [ ] CLI新增`baseline --prepared-dir --output-dir`，默认只跑validation。最终test只能由A5的冻结评价入口打开，避免平时调参查看。
- [ ] 运行`uv run --package shopsteward-ml python -m shopsteward_ml baseline --prepared-dir var/forecast/data/prepared --output-dir var/forecast/experiments/baselines`。保存三个基线逐点结果和验证汇总，按规则冻结baseline_champion。
- [ ] 补零目标、稀疏销量、单组不足30条、全0基线误差的边界；聚焦diff后提交`feat(ml): add baseline evaluation and promotion gates`。

### Task A4: LightGBM有界搜索与制品

**Files:** Create `training.py`、`artifacts.py`、`ml/tests/test_training.py`、`ml/tests/test_artifacts.py`；Modify `cli.py`、`ml/pyproject.toml`、根`uv.lock`。

**Interfaces:** `candidate_configs()->list[dict]`；`train_candidates(prepared_dir:Path,output_dir:Path,config:dict)->dict`；`fit_artifact(prepared_dir:Path,selection:dict,output_dir:Path)->dict`；`load_artifact(path:Path)->ModelArtifact`。ModelArtifact包含version,feature_schema,category_mapping,supported_series,predictor,manifest，不含训练未来销量。

- [ ] 先测试配置总数与文件完整性：

```python
from shopsteward_ml.training import candidate_configs

def test_search_is_bounded():
    configs = candidate_configs()
    assert len(configs) == 4
    assert {(x["objective"],x["num_leaves"]) for x in configs} == {
        ("poisson",31),("poisson",63),("regression",31),("regression",63)}
    assert all(x["num_threads"] == 4 for x in configs)
```

- [ ] 运行测试确认失败；实现设计§4.2的4配置×8外层窗口、内层28日early-stop、排序选择和中位数轮数；使用chunk/Parquet减少内存，不把完整原始M5笛卡尔展开到全部商品。诊断100序列配置输出到不同目录，不覆盖正式manifest。
- [ ] 同时实现artifact原生保存、checksums、可信路径根校验和schema检查。对测试artifact改一个model字节，load_artifact必须报ARTIFACT_HASH_MISMATCH；只有该程序生成的可信制品可载入。
- [ ] CLI新增`train --prepared-dir --config --output-dir`及`export --experiment-dir --prepared-dir --output-dir`；先在合成多序列上完成真正LightGBM fit/save/load/predict一致验证，再跑正式500序列。
- [ ] 正式训练超过2小时记录未完成组并退出非0；不自动缩减预算或并发启动多组超占CPU。保存profile与失败证据。完成后提交`feat(ml): train and package direct-horizon forecast models`。

### Task A5: 冻结测试、模型卡与可演示制品

**Files:** Modify `evaluation.py`、`artifacts.py`、`cli.py`；Create `ml/tests/test_freeze.py`、`docs/reports/forecast-offline.md`；Produce `docs/evaluation/forecast/experiment-result.json`。

**Interfaces:** `freeze_selection(experiment_dir:Path)->dict`生成不可覆盖的selection.json；`evaluate_frozen(artifact_dir:Path,prepared_dir:Path,output_dir:Path)->dict`只加载固定artifact不调用train；CLI `freeze --experiment-dir`、`evaluate --artifact-dir --prepared-dir --output-dir`。

- [ ] 写测试：冻结后更换params/hash被拒绝；evaluate运行前后模型文件hash一致；第一次测试原点历史截止T-56，后续原点只追加已经发生的销售，不更新参数。
- [ ] 运行`uv run --package shopsteward-ml pytest ml/tests/test_freeze.py -q`确认失败；实现freeze/evaluate，写入8窗口逐序列预测、paired bootstrap和promotion状态。
- [ ] 执行正式freeze与evaluate一次；保留模型未通过时所有结果，不能重新选择测试冠军。报告训练/测试范围、抽样方法、主/分组指标、5%门槛、偏差、耗时与限制。
- [ ] 输出模型卡明确target=observed_sales、最大7天、至少56日历史、销售受库存约束、M5域外不保证有效。baseline artifact标algorithm=baseline、source=model、model_name=baseline-mean7等，并在UI显示“统计基线”，不能宣称为训练后的机器学习模型。
- [ ] `offline_model_validated=false`时，manifest只能promotion_status=candidate；shadow联调可继续，active产品切换被B计划禁止。提交`docs(ml): record frozen forecast evaluation`，只提交摘要和重建说明。

### Task A6: HTTP推理、契约与本机运行

**Files:** Create `schemas.py`、`predictor.py`、`service.py`、`ml/.env.example`、`ml/README.md`、`ml/tests/test_service.py`、`ml/tests/test_predictor.py`、`ml/tools/export_contract.py`；Modify `cli.py`；Produce `docs/api/forecast-service.openapi.json`。

**Interfaces:** `ForecastRequest/ForecastResponse/PredictionDay`按设计§6；`predict(request:ForecastRequest,artifact:ModelArtifact)->ForecastResponse`；`create_app(settings)->FastAPI`；`to_business_quantity(values:list[float])->int`。CLI `serve --host --port --artifact-dir`，token从ML_SERVICE_TOKEN读取，参数不接受token明文。

- [ ] 先写核心契约测试：

```python
import pytest
from shopsteward_ml.predictor import to_business_quantity

def test_round_only_the_total():
    assert to_business_quantity([0.2,0.2]) == 1
    assert to_business_quantity([0.0,0.0]) == 0
    with pytest.raises(ValueError,match="INVALID_PREDICTION"):
        to_business_quantity([float("nan")])
```

- [ ] 在TestClient中覆盖401、少于56日、重复/缺日、闭日false、目标日不连续、DST、未知series、错误模型版本、1MiB/365日上限、429和同请求重复响应的原始曲线一致；运行`uv run --package shopsteward-ml pytest ml/tests/test_service.py ml/tests/test_predictor.py -q`确认先失败。
- [ ] 实现有界线程推理、只读制品加载、启动ready校验、错误码、浮点总量与int64检查；提供Bearer保护的`GET /ml/v1/model`单制品描述，字段按设计§6，用于backend配置校验。Liveness不暴露训练信息；service不导入backend或读取环境未来需求。
- [ ] 导出真实路由契约；更新旧`docs/api/services.openapi.json`中的预测设计为实现对照，保留版本说明并验证共享旧Forecast DTO兼容，新增字段通过专用响应DTO显式映射。
- [ ] 以正式制品在可配置空端口启动自有进程，真实HTTP完成100次预热后延迟采样及并发1/4；重启后同模型/历史的原始预测一致。最后只停止自有进程。
- [ ] `uv run --package shopsteward-ml pytest ml/tests -q`、相关Ruff、构建wheel及HTTP报告通过后提交`feat(ml): serve versioned local forecasts`。将接口交给B，artifact路径通过本机配置而非Git传输。

## A交接结果

A输出可核对的data_ready、artifact_ready、offline_model_validated和HTTP结果，不能因服务ready就勾选模型质量。B消费ForecastRequest/Response、固定artifact、series_manifest、split_manifest和history_seed格式；seed/hidden replay导出由B5实现，A只交冻结数据边界。
