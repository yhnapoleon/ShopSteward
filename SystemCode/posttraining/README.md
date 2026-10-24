## 2026-09-15 修复复评已完成

后续受限策略实验选择提示v2：诊断60/60，dev决策199/200，core真实执行140/140。原三个失败通过，新增一个Plan ID抄写错误保留；每成功任务token约增加30%。完整结果与Data下一步见[修复交接](../docs/reports/posttraining/repair-v2/data-handoff.md)。

选用配置为`posttraining/configs/eval_dev_repair_v2.json`/`runtime_dev_repair_v2.json`，显式`prompt_version: v2`；旧配置和默认构造器继续使用v1。工具schema和原gold不变。`report_repair_eval.py`生成离线对照，`repair-v2/selection.json`保存选择及剩余问题。以下历史章节保留原实验记录。

# ShopSteward Eval

最终结果与完整交接见[Eval交接](../docs/reports/posttraining/eval-handoff-v1.md)、[dev对照](../docs/reports/posttraining/dev-v1/comparison.md)。B1动作228/230、参数151/151、核心执行139/140；B0分别181/227、91/151、89/140。全部待复核和环境错误为0，人工复核0、Codex复核已记录。下文保留E1到dev的构建过程；当前安装与依赖说明以文末交接补充为准。

当前交付：E1 契约与 smoke-50、E2 scorer、真实 fixture 与模型 runner；E3/E4 smoke 基线已完成；E5 dev-200 与 E6 交接已完成。

- 50 个 episode：36 个核心、14 个挑战，8 个澄清任务各有第二步，共 58 个决策目标。
- 50 个案例由 Codex 逐例检查语义，标记 `agent_reviewed`；尚无团队人工复核。
- 初始spec_only/not_run是冻结规格当时的状态，不代表当前未评测。完整结果见datasets/eval-release-v1.json及最终报告，规格内容保持原hash。
- 每个案例保存预期动作、必要参数、成功谓词、历史 recipe、语义理由和已知限制。`expected_steps` 不进入模型可见输入。

## 运行 E1

以下 PowerShell 命令从 ShopSteward 根目录执行。E1 只需要 Pydantic 与测试依赖，不需要数据库、模型 API、LangGraph 或 CUDA。

本次已用本地缓存建立 `.venv-pt`，没有修改业务 `.venv` 的依赖。运行：

```powershell
$env:PYTHONPATH = "$PWD\agent\src;$PWD\posttraining\src"
$env:PYTHONIOENCODING = 'utf-8'
.venv-pt\Scripts\python.exe -m shopsteward_pt.cli validate --config posttraining/configs/eval_smoke_v1.json
.venv-pt\Scripts\python.exe -m pytest -c posttraining/pyproject.toml posttraining/tests agent/tests/test_task_policy.py -q
```

新机器可使用 Python >=3.11 与已有 uv 重建最小环境：

```powershell
uv venv --python 3.12 .venv-pt
uv pip install --python .venv-pt/Scripts/python.exe -r posttraining/requirements-eval.lock
$env:PYTHONPATH = "$PWD\agent\src;$PWD\posttraining\src"
$env:PYTHONIOENCODING = 'utf-8'
.venv-pt\Scripts\python.exe -m shopsteward_pt.cli validate --config posttraining/configs/eval_smoke_v1.json
```

离线机器可增加 `--offline --cache-dir .uv-cache`，前提是依赖已在该缓存中。锁文件是此次 Windows / Python 3.12 的实际验证环境，不包含训练或模型服务栈；其他平台安装后应重跑相同契约测试。

`posttraining/` 是独立轻量包，没有加入根 uv workspace。E1 以源码方式导入同仓库的 `agent/src` 共享契约；单独安装 posttraining wheel 不包含 Agent 契约，需同时提供该源码目录或安装同版本 `shopsteward-agent`。后续模型运行和业务执行再增加相应依赖。

本次静态检查使用业务环境中已有的 Ruff 0.16.6；离线缓存不含该版本，因此未为 E1 单独下载：

```powershell
.venv\Scripts\python.exe -m ruff check agent/src/shopsteward_agent/task_policy agent/tests/test_task_policy.py posttraining
.venv\Scripts\python.exe -m ruff format --check agent/src/shopsteward_agent/task_policy agent/tests/test_task_policy.py posttraining
```

## validate 做什么

1. 校验逐条 JSONL 的 EpisodeSpec、目标动作和参数类型、一次澄清限制、成功谓词名称。
2. 检查案例数量、重复 ID、fixture recipe 名称、manifest 的分区/家族对应关系和文件 hash。
3. 输出一份可读的逐例清单与机器可读的规格统计。

成功时退出码 0，stdout 为 JSON；输入缺失、格式错误、数量不符或 hash 不符时退出码 1。它不调用模型或数据库，也不计算模型准确率。

配置内路径相对配置文件所在目录解释，因此使用绝对 `--config` 可从其他工作目录运行。`--output-dir` 可把清单和统计写到指定目录，输入文件不变。

默认产物：

- `docs/reports/posttraining/task-contract-v0.md`：任务语义和接口说明，人工可阅读的维护文档。
- `docs/reports/posttraining/smoke-50-cases.md`：命令生成的完整案例表及逐例语义依据。
- `docs/reports/posttraining/eval-e1-validation.json`：命令生成的规格数量、分组、hash 和复核状态。

修改数据后，需要逐例重新确认改动的金标，再同步 `split-manifest.json` 的 episode/family/split 条目和 dataset_sha256；校验器不会自动重写 manifest，以免把误修改默认为新金标。JSONL 使用 UTF-8、LF。

## 本轮语义约定

`evaluate_plan` 和 `revise_plan` 必须显式携带 `max_purchase_qty`，值为 `[0, 1000000]` 内的严格整数或明确的 null。缺省不等于 null；`true`、`20.0`、`"20"` 等模型参数不能通过校验。中文数字属于用户表达，在金标中转为整数。

`revise_plan` 额外携带当前 Mission 版本。来源消息由业务后端绑定，不在模型动作 schema 中。`clarify` 的模型输出包含问题；金标只标必要缺项，不要求问题文字完全一致。

当前初稿只为每例保留一个明确允许动作，避免尚未决定的多答案金标。动作正确与真实执行成功在后续 scorer 中分开计分。

## E1 时的后续安排（历史记录，现已执行）

E2 实现 scorer；E3 创建真实 fixture、冻结上下文并运行 B0/B1；E4 测真实执行。尤其要验证 PT-05 的历史来源支持与 PT-10 的网关 null 行为。E1 不宣称这些案例已跑通。

完整安排见 [Eval 实施计划](../docs/superpowers/plans/2026-09-14-phase2-eval-implementation-plan.md)。

## E2–E4 实际运行

业务执行与模型调用使用仓库已有 `.venv`（backend/agent/knowledge 依赖，未修改 uv.lock）。`.venv-pt` 继续用于纯契约、评分和报告测试。以下从仓库根目录执行：

```powershell
$env:PYTHONPATH = "$PWD\backend;$PWD\agent\src;$PWD\posttraining\src;$PWD\knowledge\src;$PWD\simulation"
$env:PYTHONIOENCODING = 'utf-8'
.venv\Scripts\python.exe -m shopsteward_pt.cli freeze --config posttraining/configs/eval_smoke_v1.json
.venv\Scripts\python.exe -m shopsteward_pt.cli evaluate --config posttraining/configs/eval_smoke_v1.json --run-dir var/posttraining/runs/my-smoke --policies B0 B1 --mode decision
.venv\Scripts\python.exe -m shopsteward_pt.cli evaluate --config posttraining/configs/eval_smoke_v1.json --run-dir var/posttraining/runs/my-smoke --policies B0 B1 --mode execution
.venv\Scripts\python.exe -m shopsteward_pt.cli rescore --run-dir var/posttraining/runs/my-smoke/decision/B1
```

`freeze` 创建并执行真实测试 fixture，需 Docker 中 PostgreSQL 和迁移到 head 的 `shopsteward_test`。不要对现有 run 重新 freeze；它会改变随机对象 ID 和上下文 hash。执行模式每例创建新的独立业务对象。模型配置从 `runtime_v1.json` 与已有 `backend/.env` 读取；B2 未配置，价格缺失时金额为 null。

每个 mode/policy 目录包含 specs、manifest、raw、scores、pending-reviews、reviews、summary、failures.csv、report.md。先逐项阅读 pending-reviews.jsonl，再在 reviews.jsonl 填写 key、原样 question、slot、relevant、no_guess、no_known_id_request、reviewer、review_type、rationale。只有准确匹配且三项判定均通过才能继续 scripted reply；用原 evaluate 命令增加 `--resume`，只补待继续的第二步，保留原第一步。复核错误问题也必须记录 false，不能为提高分数改问题或注入正确答案。

`rescore`/`report` 不调用模型，只重算已保存轨迹。暂未复核或第二步未执行的中间报告不能称完整最终结果。这里的 delivery 是 harness 从真实回执提取字段，不评价自然语言报告质量；clarify/no_action/handoff 由最薄 harness 完成，不评价生产持久对话流程。

后台运行入口：`posttraining/scripts/run_smoke_background.py --run-dir var/posttraining/runs/smoke-v1`。启动应使用隐藏窗口并重定向输出；进度见 status.json，进程/退出情况见 background.json。完成首批后仍需澄清复核、resume、失败分析以及 E5 dev-200 和 E6 交接，不能将进程退出等同于整个 Eval 完成。

## dev-v1（200例）

规格、案例清单和manifest已发布：140核心/60挑战，230个决策目标，70个语义家族。原smoke50原样包含；这些是合成语义分组，不代表70个独立真实来源。新增150例由Codex逐项设定动作、数值和语义依据，人工复核仍为0。

构建命令：`.venv-pt/Scripts/python.exe posttraining/scripts/build_dev_v1.py`。校验：`python -m shopsteward_pt.cli validate --config posttraining/configs/eval_dev_v1.json`。模型调用沿用smoke提示和配置。开发集后台命令：

```powershell
.venv/Scripts/python.exe posttraining/scripts/run_smoke_background.py --run-dir var/posttraining/runs/dev-v1 --config posttraining/configs/eval_dev_v1.json --execution-suite core --freeze-first
```

首次运行后勿再次传`--freeze-first`，避免改动已冻结ID。恢复澄清第二步使用`evaluate --config posttraining/configs/eval_dev_v1.json --run-dir var/posttraining/runs/dev-v1 --policies B1 --mode execution --suite core --resume`；decision恢复不带suite。批次完成仍需复核、错误分析和最终交接。

## 最终交接补充（2026-09-15）

已完成全部smoke与dev评测/续跑，40个不同失败案例有42条解释，四组dev离线重评分结果完全一致。B2未配置，SFT未训练，独立test300未构造或运行。监视自动化随交接暂停，未自动commit/merge。所有源码、数据、报告在当前工作区；var里的完整raw/源码快照为Git忽略文件，交接实验应一并保存。

新机器业务依赖按根uv.lock安装（backend的agent extra同时提供模型依赖）：

```powershell
uv sync --project backend --extra agent --frozen --cache-dir .uv-cache
$env:PYTHONPATH = "$PWD\backend;$PWD\agent\src;$PWD\posttraining\src;$PWD\knowledge\src;$PWD\simulation"
$env:PYTHONIOENCODING = 'utf-8'
```

本次复用了已有.venv，未另做新机器安装演练。[关键包版本](../docs/reports/posttraining/dev-v1/runtime-versions.json)已保存。轻量.venv-pt安装沿用前述requirements-eval.lock，posttraining未加入根workspace。

参考backend/.env.example准备本地配置，不覆盖现有backend/.env。需要已启动的Docker中PostgreSQL、本地shopsteward_test数据库（本次55432端口）及迁移head0014_forecast_work_merge。下面从仓库根目录明确迁移测试库，不打印连接密码：

```powershell
.venv/Scripts/python.exe -c "import os,sys,subprocess; from app.core.config import Settings; from sqlalchemy.engine import make_url; u=make_url(Settings(_env_file='backend/.env').database_url.get_secret_value()).set(database='shopsteward_test'); assert u.host in {'127.0.0.1','localhost'}; os.environ['DATABASE_URL']=u.render_as_string(hide_password=False); subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd='backend',check=True)"
```

本轮8项集成测试重跑（不运行其他会清空整个job队列的测试）：

```powershell
.venv/Scripts/python.exe -c "import os,pytest; from app.core.config import Settings; from sqlalchemy.engine import make_url; u=make_url(Settings(_env_file='backend/.env').database_url.get_secret_value()).set(database='shopsteward_test'); os.environ['TEST_DATABASE_URL']=u.render_as_string(hide_password=False); raise SystemExit(pytest.main(['backend/tests/integration/test_task_policy_eval.py','-q']))"
```

已有frozen文件可直接用于新run；只在全新环境第一次freeze。重建上下文时复制config/runtime并改用新frozen路径和run目录，不要覆盖原实验上下文。evaluate需显式--run-dir；report与rescore都使用指向单个mode/policy目录的--run-dir，而非--run-root。

所有“参数正确率”分母包含选错动作的期望工具步骤；期望clarify的案例不在参数分母。因此B1参数100%并不抵消其将-8读成8的动作错误。B0有3个按协议禁止补发回复的后续步，保留为失败，不是待运行。

当前价格未配置，金额不可用；516次正式模型调用加6warmup/1probe的总已观察用量为input374033、output36758。失败连接探针未返回usage。下一阶段先固定units/件及最低量路由约定，再采集新来源数据；不得将dev金标及同模板近义改写转成训练集。
