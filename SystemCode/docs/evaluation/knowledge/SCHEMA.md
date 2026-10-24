# ShopSteward K0 数据契约与评测边界

**全部是模拟 / SYNTHETIC。** 人名、店名、供应商、SKU、事件、条款与后台形状的记录均为虚构测试夹具，不是实际经营输入。基准为 **2026-09-07**，日期有效期统一为 **`[valid_from, valid_until)`**，结束日不生效。没有调用外部API、embedding、PG、OpenSearch或Docker；本文不报告检索效果或生产能力。

## 文件与数量

| 类别 | 份数 |
|---|---:|
| supplier 供应商 | 12 |
| product 商品 | 8 |
| sop 流程 | 8 |
| campaign 活动 | 6 |
| retrospective 复盘 | 6 |

40份原件是40个唯一版本、38个逻辑文档：S01/S02/S03是同一逻辑文档的历史/当前/未来版本。格式为 **8 PDF、6 DOCX、4 XLSX、4 CSV、11 MD、7 TXT**，主题与格式交叉。每份包含独立经营情境及中英内容；同名文件保存在不同店铺/版本目录，未把格式副本计作独立资料。

- `corpus-spec.json`：逐份编写的语料源定义；不含问题答案。
- `sources/{store_id}/{version_id}/{原文件名}`：40份真正的原件，只有此目录是正常解析输入。
- `corpus-manifest.json`：版本/权限/日期/原件hash/规范文本定位与解析异常预期。
- `canonical/{version_id}.txt`：40份独立文本评价参考；不是从解析器抄回的输出，不代表扫描页已经OCR成功。规范文本保留用于评测的章节正文；重复的DOCX汇总表、跨页重复表头等不重复展开。
- `cases.jsonl`：60条逐题指定的核心标注，40 dev / 20 test。
- `relations.json`：C与D共享的28条来源明确的关系；有verified、candidate、rejected状态。
- `entities-fixture.json`：26个虚构实体、14条后台形状的关系记录及3个测试身份；无实时库存、现金、价格。
- `relation-cases.jsonl`：12条关系标注，8 dev / 4 test；带独立查询意图 `query_plan`。
- `generated-files.json`：生成器拥有的具体文件及hash，不代表拥有整个目录。
- `validation-report.json`：离线文件结构、hash、数量、拆分与引用完整性证据；不含召回/延迟评分。

## 复现与保护其他代理文件

从仓库根目录运行（也可用同依赖的仓库 `.venv`）：

```powershell
& 'C:/Users/13736/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' backend/tools/build_knowledge_corpus.py
& 'C:/Users/13736/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' backend/tools/build_knowledge_corpus.py --verify-only
& 'C:/Users/13736/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' backend/tools/build_knowledge_corpus.py --check-reproducible
```

依赖：Python 3.10+、reportlab、Pillow、python-docx、openpyxl、pypdf。以 `validation-report.json` 的版本为复现环境；不安装全局包。扫描页默认使用Windows微软雅黑 `C:/Windows/Fonts/msyh.ttc`；其他环境通过 `--font` 或 `K0_CJK_FONT` 指定本地CJK字体。不同字体/依赖版本可能改变二进制hash；同环境固定时间戳、ZIP排序与PDF invariant保证可重复生成。

构建只写原件、canonical、manifest、校验报告和拥有权清单。它不覆写手工源定义、题集、实体、关系或README，也不递归删除目录。已有未知目标文件会拒绝覆盖；上次生成后被外部修改的目标也会拒绝覆盖。独立文件采用同目录临时文件加原子替换；重复运行时相同字节不写盘。未再生成的旧目标保留，不静默删除。`--verify-only` 和 `--check-reproducible` 均为只读检查，后者在内存重新生成81个原件/canonical/manifest目标逐字节比较。

## Manifest 与解析边界

顶层 `documents[]` 每条包含：

```text
key, synthetic, store_id, document_id, version_id, version_number,
category, title, language, source_path, source_sha256, source_bytes,
valid_from, valid_until, status, allowed_roles,
canonical_text_path, canonical_sha256, canonical_role,
expected_parser_warnings, sections, conflict_set
```

路径相对本目录。`sections[]` 含 `section_id`（如 `section:1`）、`heading`、`text`、`source_locator`、`canonical_start_line/end_line`。页、行、段落号均从1开始；DOCX `paragraph_index` 定位标题后的正文段落；CSV行号含表头；XLSX sheet/单元格范围明确。权限为店铺与角色的交集；认证身份来自fixture，不依据问题中自称的角色。历史查询按题目 `as_of`，默认排除归档、过期和未来版本。

| 异常原件 | 结构验证 | 预期解析行为 |
|---|---|---|
| S04 PDF | 1页纯图，无文本层 | 无OCR时 `ocr_required`，不得静默成功 |
| P02 PDF | 第1页文本；第2页图像含关键替代条件 | `partial_text_ocr_required` 指明第2页，不得以第一页冒充完整条件 |
| O01 PDF | 3页连续检查表，每页重复表头，第3页有最终复核项 | `cross_page_table`提示；如丢续表或表头应记录截断，不能声称完整 |
| P04、R03 XLSX | `换算!D3`有公式、无缓存 | `formula_cache_missing`；缺失≠0；另算值≠提取缓存 |
| S07、A03 XLSX | `换算!D3`同时有公式与缓存 | 分别保存600和120；不能将换算/草稿当正式业务输入 |

`sections.text`、canonical、题集、关系题答案、报告都是评分侧材料。**不得把manifest中的正文或canonical索引进正常检索，也不得用答案构造查询、选候选、造索引或补齐扫描文本。** 若另做“理想解析文本”诊断，必须单独标明oracle诊断，不能与原件解析基线混报。无OCR扫描题的证据仍是独立gold，解析缺失应单独归因，不能删题美化召回率。

## 核心题集与冻结拆分

每行必要字段：`id, split, group, query, store_fixture, as_of, expected_document_versions, required_assertions, forbidden_assertions`。有证据时 `required_evidence=[{version_id, sections:["section:1"]}]`；额外字段包括 `expected_outcome`、`excluded_document_versions`、工具类别预期。工具类别 `business_read/business_write/document_search/memory_edit` 是路由验收语义，不冒称现有函数名。业务混合题不得只凭检索命中宣布回答或业务行为正确。

| group | dev | test | 合计 |
|---|---:|---:|---:|
| exact | 8 | 4 | 12 |
| keyword | 8 | 4 | 12 |
| synonym | 8 | 4 | 12 |
| synthesis | 6 | 2 | 8 |
| no_answer | 5 | 3 | 8 |
| business_mixed | 5 | 3 | 8 |

空 `expected_document_versions` 不是普通召回失败样本：可能是无资料、权限隔离、当前无生效资料或纯业务工具路由。冲突题N05要求同时找出S10/S11，仍不能给唯一期限；缺少司机姓名题N08可以引用相关文档并明确无答案。分组和分母须保留，不能把ACL拒绝计入普通Recall提升。

标注由本次作者助手逐题独立指定，**没有从任何检索器、SQL路径返回或模型回答反推期望，也没有声称真人已经复核**。`human_review_status` 为pending；真人复核可另存审阅记录。test标签冻结作为验收集，不用来调词典、谓词、阈值或预算；整个共享经营语料可用于索引，题目拆分不是文档隔离实验。

## 关系输入：C和D严格同事实

`relations.json.edges[]` 使用规格字段：

```text
edge_id, store_id, subject_type, subject_id, predicate, object_type, object_id,
origin_kind, source_record_id OR source_version_id + source_locator,
valid_from, valid_until, assertion_status, qualifiers, revision
```

后台来源的 `source_record_id` 精确引用 `entities-fixture.json.backend_records[]`。文档与人工来源引用manifest的版本及section；人工标签明确说明这是人为适用标签，不谎称原文包含实体ID。替代边额外保留条件、方向和有效期；MENTIONS不等同APPLIES_TO。关系集是开放世界小样本，未建边不等于不存在。

每条关系题另外提供 **独立题意输入**：

```json
{"query_plan":{"seed_entity_ids":["E-SUP-QH"],"allowed_predicates":["HAS_OFFER","FOR_SKU"],"target_types":["Mission"],"target_entity_ids":[],"max_depth":3,"direction":"both","qualifier_context":{"sku_id":"E-SKU-OAT","mission_status":"preparing","purpose":"potential_mission_association"}}}
```

查询执行器只接收 `query_plan`、`store_fixture` 与 `as_of`，读取共享实体/关系事实。C可以固定1–3跳JOIN，D可以有界递归；SQL也能多跳，不预设D更优。两路必须记录同一 `relations.json` 与 `entities-fixture.json` 的SHA256，并共享店铺、角色、源文档可见性、时间及条件处理，拒绝把人工答案边只给D。

`target_entity_ids=[]` 表示只限终点类型，非空仅取题目显式点名的终点。`direction=both`允许沿存储边反向发现关联，但不颠倒断言：`A POTENTIAL_SUBSTITUTE_FOR B` 不会变成B可替A，也不会使两条替代边产生传递批准。`query_plan`无expected字段，也不复制期望路径。

条件上下文的解释：

- 所有路径先满足同店、verified、源资料可见、边与来源有效期交集、实体状态；candidate/rejected仅可在评分或拒绝原因诊断中查看，不能成为接受路径。
- `sku_id`限制涉及的SKU；`mission_status`和`action_status`限制对应终点/中间实体。`only_skus/excluded_skus`在通知路径中向后传播，RQ05须排除同供应商的茶报价路径。
- 替代需匹配 `mission_id/use`；`customer_consent_required`要求context的 `customer_consent=true`；`nut_allergy_claim_allowed=false`要求 `nut_allergy_claim=false`；`nut_label_required`要求 `nut_label_present=true`。未知条件不能当满足。包装等量另按边的 `conversion` 检查，禁止默认对称/传递。
- RQ10先检查半开区间：试用边结束9月15日，下旬任务开始9月16日，交集为空；还存在任务条件不匹配。
- RQ03 `allow_historical_target_metadata=true`只允许SUPERSEDES定位历史版本ID，不允许默认读过期正文；有效来源仍为S02。没有该意图时采用常规有效资料约束。
- `purpose`说明题意，不是通过/拒绝开关；`completeness_required`表达用户要求，不能把开放世界数据变成完整名单。不得基于case ID写特判。

评分字段：`expected_edge_ids`是**接受路径**中边的集合；`expected_paths`是路径列表，每跳为 `{edge_id, direction: forward|reverse}`；`excluded_edge_ids`是本题必须排除的路径边；`diagnostic_edge_ids`只帮助审阅拒绝依据。负例中即便没有接受路径，也可要求检索可见来源解释条件/日期/未确认状态。这些诊断来源不能充当成功路径。

关系拆分为 single_step 3 dev/1 test、multi_step 3/1、conditional 1/1、unknown 1/1，共8/4。核心与关系分别报告。文件校验通过不证明查询算法、OCR、中文分词或回答断言已通过；相应协议与检索运行证据由K0 baseline runner另行产出。
