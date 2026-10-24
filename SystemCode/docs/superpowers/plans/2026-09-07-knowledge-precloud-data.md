# 上云准备A：语料与评测 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 得到可通过正常上传流程导入的200份试运行语料，并扩展为1000文档及独立300题评测。

**Architecture:** 原始资料、来源metadata、合成事实与评测gold分目录保存；生成与验证工具只操作自身记录的文件。原K0语料保持不变；以source/scenario family隔离dev/test问题。

**Tech Stack:** 现有Python、pydantic、pytest及文档生成运行时；原件格式沿用PDF/DOCX/XLSX/CSV/MD/TXT。源码工具不依赖云账号，模型生成可在具备端点后增加。

**Spec:** [云端与语料设计](../specs/2026-09-07-cloud-knowledge-and-corpus-design.md)、[主计划](2026-09-07-knowledge-precloud.md)。执行前读两者。

## Global Constraints

继承主计划全部Global Constraints；本子计划只新增`knowledge-expanded`语料及对应工具，不覆盖`docs/evaluation/knowledge/`。公开资料可获取性与独立来源数如实报告，不能以链接目录替代已采集原件。

## A1：来源/场景/问题契约与验证器

**Files:** 新建`backend/tools/knowledge_corpus/{__init__,schema,validate,ownership}.py`、`backend/tests/unit/test_knowledge_corpus_expanded.py`；新建`docs/evaluation/knowledge-expanded/{README.md,schema.json,sources.jsonl,scenarios.jsonl,cases.jsonl}`。

**Interfaces:**

- `validate_source(row: dict) -> dict`：验证并返回规范化来源记录；错误抛ValueError。
- `validate_case_splits(rows: list[dict]) -> None`：同family跨dev/test抛ValueError。
- `write_owned(root: Path, relative: str, data: bytes, previous_sha256: str | None) -> str`：返回新hash；目标越界或已存在且不匹配旧hash拒绝写入。
- Source必填：source_family_id、title、publisher、url或null、language、jurisdiction、publication_date或null、retrieved_at、acquisition_status、use_terms_status、source_kind。只有acquired才能有original_path/content_sha256；reference_only不计正文配额。
- Scenario必填：scenario_family_id、synthetic、store_fixture、entity_refs、effective_interval、facts、exceptions、document_kinds。合成数值需要单位和“模拟”标记，行业事实需public_source引用。
- Case必填：case_id、split、scenario_family_id、group、query、store_fixture、as_of、required_evidence、forbidden_claims、business_tools、relation_tags。gold所在文件不出现在ingest清单。

- [ ] 先加入以下RED用例及来源日期缺失、路径越界、文件被手工修改时拒写用例。

```python
import pytest
from tools.knowledge_corpus.validate import validate_case_splits

def test_paraphrase_family_cannot_cross_splits():
    rows = [
        {"case_id": "Q1", "scenario_family_id": "S1", "split": "dev"},
        {"case_id": "Q2", "scenario_family_id": "S1", "split": "test"},
    ]
    with pytest.raises(ValueError, match="family"):
        validate_case_splits(rows)
```

- [ ] 在仓库根运行并确认因未实现接口失败：

```powershell
& ./.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/unit/test_knowledge_corpus_expanded.py -q
```

- [ ] 实现确定性校验；family检测采用集合分组，不靠字符串相似度推断题集归属。所有source/scenario字段落入JSON Schema；JSONL逐行报路径/行号及错误，不打印外部密钥。

```python
families = {}
for row in rows:
    families.setdefault(row["scenario_family_id"], set()).add(row["split"])
if any(len(splits) > 1 for splits in families.values()):
    raise ValueError("scenario family crosses dev/test")
```

- [ ] 同命令复测通过；将schema与字段示例交叉检查。目录manifest必须区分logical_document_count、version_count、source_family_count、chunk_count，未解析时chunk_count为null。

## A2：首批200份及正常API导入清单

**Files:** 新建`backend/tools/{build_knowledge_expanded_corpus,verify_knowledge_expanded_corpus}.py`；补充`backend/tools/knowledge_corpus/{render,manifest}.py`；资料存`docs/evaluation/knowledge-expanded/`下`originals/`、`facts/`、`manifests/pilot.json`；大原件超过仓库合理预算时放`var/knowledge-expanded/originals/`并登记可恢复artifact路径/hash，不能只有无人可恢复的本机路径。

**Interfaces:**

- `build_manifest(records: list[dict], root: Path) -> dict`：输出documents及counts，每份包含document_fixture_id、version_fixture_id、original_path、mime、size、sha256、source_family_id、scenario_family_id、metadata、synthetic；不含facts或gold正文。
- `validate_manifest(manifest: dict, root: Path) -> dict`：返回实际字节/hash/引用错误列表、独立文档数、类别与格式统计。
- CLI `build_knowledge_expanded_corpus.py --stage pilot --verify-only`只读校验；不带verify-only时按ownership表生成已编写的场景文稿，不能循环替换实体名凑数量。
- CLI `verify_knowledge_expanded_corpus.py --manifest <path> --check-reproducible`两次隔离构建，比较hash并确认外部文件不被修改。

200份配额：公开资料20、合成供应商条款36、商品/包装说明64、SOP32、活动20、复盘28。先完成20份跨类别审阅，再逐批扩到200；公开20份获取失败时如实记录缺口，不私自改为200份全合成并宣称原配额完成。

- [ ] 为manifest加入RED：同一文档两个版本只能算一个logical document；reference_only不计已采集正文；gold不出现在ingest manifest。

```python
from tools.knowledge_corpus.manifest import logical_count

def test_versions_are_not_independent_documents():
    rows = [
        {"document_fixture_id": "D1", "version_fixture_id": "V1"},
        {"document_fixture_id": "D1", "version_fixture_id": "V2"},
    ]
    assert logical_count(rows) == 1
```

`logical_count(rows: list[dict]) -> int`定义为唯一document_fixture_id计数，放manifest.py；不会按文件数计数。

- [ ] 同A1 pytest命令确认RED后实现计数/文件校验及CLI，已有K0工具只作为格式/生成参考。
- [ ] 逐项采集[来源目录](../../research/2026-09-07-knowledge-public-source-catalog.md)中的可用正文；正文内容与用法查官方来源，保存时间/hash/版本，阻断403时记录reference_only。网页需保存为K1支持的规范化MD，保留URL/标题/标题层级；此为归档转换，不能伪称网站原始PDF。
- [ ] 写场景事实与完整原件，覆盖订单截止/分批配送/破损举证/包装兼容/活动替代/异常复盘等至少20个不同scenario family。MD/TXT和Office/PDF均覆盖；扫描与表格沿用K0异常组做回归，不以制造大量难解析文件拉低分数。
- [ ] 去重分两层：完全hash重复剔除；去模板文本的字符5-gram Jaccard≥0.85列为人工/助手复核候选，只作警报，不自动删除具有不同业务条件的有效资料。
- [ ] 执行以下已规划CLI，输出JSON及可读报告；命令只有工具完成后才能声称可运行。

```powershell
& ./.venv/Scripts/python.exe backend/tools/build_knowledge_expanded_corpus.py --stage pilot --verify-only
& ./.venv/Scripts/python.exe backend/tools/verify_knowledge_expanded_corpus.py --manifest docs/evaluation/knowledge-expanded/manifests/pilot.json --check-reproducible
```

- [ ] 通过条件：200个独立document ID、文件全部有字节证据、主体商业条件可区分、模拟标签齐全、所有引用存在、未改变K0hash。真人审阅未发生就写pending，不能把助手审阅称真人复核。

**给B/C的产物：** `manifests/pilot.json`只包含原件和metadata；`entities-fixture.json`记录模拟门店/SKU/供应商及关联。真正导入时由C1通过独立测试租户映射到backend实际ID，禁止在索引中用fixture ID冒充生产ID。

## A3：1000份质量集、300题与关系对照

**Files:** 补充`knowledge-expanded/manifests/full.json`、`cases.jsonl`、`relations.jsonl`、`freeze-evidence.json`、`quality-report.md`；新建`backend/tools/knowledge_corpus/evaluation.py`与`backend/tools/verify_knowledge_expanded_eval.py`。

**Interfaces:** `required_evidence_recall(required: list[set[str]], retrieved: set[str]) -> float | None`；每个set是一项要求的可替代证据ID集合，有交集即满足；required为空返回None，不用1掩盖无答案行为。`evaluate(result_file, case_file)`只在检索完成后离线评分，不向search发送gold。

- [ ] 加入RED验证多项必要证据和无答案分母：

```python
from tools.knowledge_corpus.evaluation import required_evidence_recall

def test_one_of_two_conditions_is_not_complete_support():
    assert required_evidence_recall([{"A", "A2"}, {"B"}], {"A2"}) == 0.5
    assert required_evidence_recall([], {"unrelated"}) is None
```

- [ ] 用A1 pytest入口执行，按上述集合定义实现评分后复测。
- [ ] 按设计配额扩量1000逻辑文档，约200修订版本另计。每新增批次先过A2检查，再加入full manifest；内容/来源不能用未执行的LLM输出占位。
- [ ] 编写300题，按40/40/60/60/40/60组配额分层，同时整family分配100 dev/200 test。关系标签60题包含单步/多步/条件不满足/图不完整；入口实体与查询约束独立写，不能由expected_path反推。
- [ ] 关系使用相同有来源事实供SQL限定和有界遍历比较；模拟verified与真实verified状态区分。禁止把可达等同替代许可或完整影响范围。
- [ ] 在正式调参前冻结全部题/关系/文档hash；后续test修订另升评测版本并解释原因。试运行使用dev；不能一边改test问法一边报提分。
- [ ] 建立独立压力manifest，只用于1万/5万/10万块存储和并发测试；规模克隆不进入full质量集计数或300题分母。
- [ ] 输出语料类别/来源/格式/条件覆盖、近重复复核记录、人工状态和公开来源缺口。效果脚本只有实际获得search结果才生成分数；无模型时只报词法成绩。

此子计划完成不代表云模型选型或K2完成；交付是实际可导入内容、明确gold和可重复评价入口。
