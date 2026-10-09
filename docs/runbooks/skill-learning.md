# Skill 学习功能运行说明

实现日期：2026-10-03。当前交付为 Skill 学习闭环及离线评估、在线观察基础设施；不包含流程 DSL、动态 A2UI、自动模型训练。质量校准和真实经营增益尚未完成实验。

## 开启与停用

1. 备份目标数据库，再按现有部署流程运行 `python -m alembic upgrade head`。新迁移为 `0016_learning_foundation`，增加 11 张独立学习表及 Skill 内容不可变触发器。当前开发验证只迁移了隔离测试库。
2. API、业务 worker 和 agent worker 配置 `LEARNING_ENABLED=true`。默认 false；它决定业务事务是否写入学习 outbox。三个进程必须使用一致配置。
3. 运行 `python -m app.worker --profile learning`。它负责 outbox 投影与生成任务。只采集、不调用模型时保持 `LEARNING_GENERATION_ENABLED=false`；需要生成时设置 true，并配置现有 Agent 的模型端点与密钥文件。密钥不进入经验数据。
4. 在前端“联调控制 → 学习与经验”选择“整理候选，由我选择启用”，或进入 `/?view=learning`。设置按用户和店铺隔离。仅开启服务器总开关不会默认取得用户同意，也不会回灌之前的历史。
5. 关闭个人学习设置会停止采集并暂停已启用 Skill；关闭全局开关会阻止 API 访问、采集、生成和检索。既有采购权限和确认流程保持原业务规则。

同一 Case 的多次修订计为一个 episode；普通 Mission 与恢复 Case 分开归属，恢复计划避免双重计数。前十次是首次检查点；同类至少三个独立事项且跨两个经营日期时可以生成候选。当前是可调整的工程初值。

后台每作用域每天最多三批，每批最多三个候选；模型调用最多两次生成及一次 JSON 修复，总输入/输出分别以 12000/4000 UTF-8 字节上界预算约束。崩溃后无法确认是否已付费调用的批次会失败，不自动重发模型请求。费用未取得供应商账单时显示 unknown。

## 候选与质量检验

每个候选自动接受结构/工具契约检查并保存质量卡。H1–H6、S1–S6 中缺少测量证据的项目保持 unknown。前端“检查质量”只重新执行静态检查，不会假装执行隔离经营回放。

启用必须有与当前内容、证据、策略、模型配置、工具目录、业务规则和 rubric 完全绑定的通过报告。各维最低 3 分；不能用总分抵消硬错误。独立适用样例不少于 20 且覆盖五类套件；20 是覆盖下限，通常不足以证明统计非劣。

离线评估工具只供可信维护人员使用，不是公开 HTTP 或 Agent 工具。它不自动启动真实采购，也不接受 LLM 自行注册“通过”成绩。

### 先登记实验

在 `backend` 目录运行：

```powershell
python -m app.learning.evaluate_cli prepare --input review-package/prepare.json
```

输入结构：

```json
{
  "scope": {"principal_id": "实际用户ID", "store_id": "实际店铺ID", "source_domain": "simulation"},
  "asset_id": "候选ID", "revision": 1,
  "target": "tool_calls_reduction",
  "cases": [{"id": "独立案例ID", "suite": "normal", "source_ids": [], "origin": "locked_test", "input_hash": "冻结输入的摘要"}]
}
```

示意只列一例；实际必须有不少于 20 个独立案例并包含 `normal/negative/boundary/recovery/composition`。目标只可选 `tool_calls_reduction/corrections_reduction/coverage_gain`，登记后不可看结果再改。案例与生成来源不能相交。命令返回 campaign_id 和冻结清单。

### 执行与复核

隔离回放器为每个 case 建立相同输入、模型配置、预算、工具及随机种子的独立环境，分别执行无 Skill 与候选 Skill；已有 active 版本时还需旧版本对照。`app.learning.evaluation.replay_suite` 提供回调编排接口；业务模拟器的批量回放适配和真实模型实验尚待补齐，不把历史日志当成反事实经营结果。

记录每个变体的 `success` 布尔值、`tool_calls`、`corrections` 非负整数。UNKNOWN 不能填成 true。适用/非适用案例须在冻结清单中确定；结果应携带同样的 `id/suite/source_ids/input_hash`、`completed_at` 与 `artifact_ref`。保留运行轨迹和业务 oracle 的真实证据文件。

两名评审独立按 [Skill rubric](../superpowers/specs/2026-10-03-skill-quality-rubric.md) 给出 S1–S6 的 score、reason、evidence_refs。分歧返回 unknown。H1–H6 必须各自有测试/审查证据。尚未完成首批 30 个候选的双人校准，不能声称评估器已经校准。

### 登记报告

```powershell
python -m app.learning.evaluate_cli complete --input review-package/complete.json
```

输入含 `scope/campaign_id/results/reviews/checks/artifacts`：

- results：冻结案例对应的配对结果；baseline 为旧 active（存在时），否则无 Skill。存在旧 active 时，额外提供 without_skill 结果。必须在 campaign 登记之后完成。
- reviews：恰好两名不同评审，结构为 `{reviewer, dimensions: {S1: {score, reason, evidence_refs}, ...}}`。
- checks：`{H1: {status: "pass|fail|unknown", evidence_refs: [...]}, ...}`。
- artifacts：`[{id, path, sha256}]`。路径必须在输入 JSON 所在评审包目录内，工具读取实际文件计算 SHA-256。引用必须能解析；校验和只验证文件一致性，真实性仍由可信回放器和评审负责。

工具计算配对改善与保守区间，保存不可跨版本复用的报告。报告通过仍不会自动激活；用户在前端启用。报告有效期初值七天，每次调用重新校验绑定。静态复查记录最新检查，不覆盖已启用版本的发布依据；已过期或依赖失效的报告仍不能继续使用。

## 调用与事后观察

只检索当前用户/店铺/来源域的 ACTIVE Skill。前置条件与排除条件由服务端事实判定，未知条件不匹配；最多三个，总内容 UTF-8 字节上界 1800。当前会话已绑定的 Mission/Case 用作场景，不凭模型生成的范围声明扩大权限。

显式用户知识优先。显式记忆变化会暂停同作用域的推断经验并更新证据策略版本。遗忘会撤销所有版本，禁止原来源再次提炼，包括改标题重建。来源的 outcome revision 变化使旧质量绑定失效；下一次准入需要重新检验。每个 Run 固定首次选择的版本（包括空集）；普通版本更新供下一 Run 使用。工具执行和答复发布事务会重新核对已注入经验的依赖，撤销后的在途模型结果不能继续产生副作用或发布。当前 Run 自己成功保存显式记忆后清空学习选择并重建上下文，保留该次保存回执。

`GET /api/v1/stores/{store_id}/learning/applications` 返回最近 100 次选择与观察记录；selected 不等于 executed，也不计为成功。Agent 结束只记录调用轨迹与运行状态。到货结果另行更新 pending/unknown/matured，不宣称 Skill 导致经营收益。

`POST .../applications/{id}/feedback` 可登记用户复核：expected_feedback_version、executed、status、attribution、evidence_ids。确认 executed 必须引用该次真实调用的 invocation_id；近十次确认执行中失败至少三次时自动暂停该版本。反馈不替代离线准入报告。现阶段没有自动因果归因或自动 judge 复核，也没有定时全量再评估。

## 回滚与诊断

可以暂停版本，或通过 transitions API 指定旧 revision、expected_version、evaluation_id 执行 rollback；旧版本同样要通过当前质量准入。内容永不原地覆盖。遗忘是功能性禁止复用，保留审计记录，不是物理删除个人数据的接口。

生成失败查看学习 worker 的 learning_batch 作业及 learning_batches.usage.error_code；只存错误码，不记录密钥。普通经营失败仍以原 Mission/Action 审计为准。

数据库降级到 0015 会删除全部学习表，仅可在备份后、停止所有新版本进程且明确放弃这些数据时执行；回滚功能开关通常比降级数据库更合适。
