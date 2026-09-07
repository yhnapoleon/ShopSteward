# ShopSteward K0 模拟资料

全部为 **模拟 / SYNTHETIC** 中英经营资料，不含真实业务数据。基准日 **2026-09-07**，有效期左闭右开。详细接口见 [SCHEMA.md](SCHEMA.md)，包括关系 `query_plan`、条件过滤、ACL与解析异常规则。

- **40份原件**：供应商12、商品8、SOP8、活动6、复盘6；8 PDF、6 DOCX、4 XLSX、4 CSV、11 MD、7 TXT。40版本对应38逻辑文档，包含同文档历史/当前/未来版本。
- **60核心题**：12精确/12关键词/12同义/8综合/8无答案/8业务混合；40 dev、20 test。
- **12关系题**：4单步/4多步/2条件/2未知；8 dev、4 test；C/D共享28条关系、相同来源/权限/时间/条件。
- **异常**：S04纯扫描PDF、P02混合扫描PDF、O01三页连续表格；S07/A03 XLSX有公式缓存，P04/R03无缓存；两店同名、权限受限、过期/未来/归档、冲突与提示注入。

文件：`corpus-spec.json`为源定义，`sources/`为原件，`canonical/`为评价参考文本；`corpus-manifest.json`给出store/ACL/document/version/hash/定位；`cases.jsonl`、`relation-cases.jsonl`为独立逐题标注；`relations.json`与`entities-fixture.json`是共享事实；`validation-report.json`与`freeze-evidence.json`保存校验和冻结证据。

从仓库根目录运行，也可使用有相同依赖的仓库`.venv`：

```powershell
& 'C:/Users/13736/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' backend/tools/build_knowledge_corpus.py
& 'C:/Users/13736/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' backend/tools/build_knowledge_corpus.py --verify-only
& 'C:/Users/13736/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' backend/tools/build_knowledge_corpus.py --check-reproducible
```

依赖为reportlab/Pillow/python-docx/openpyxl/pypdf，版本见报告；不安装全局包。扫描页字体默认微软雅黑，可用`--font`指定本地CJK字体。固定依赖与字体时输出字节可重现。

脚本只覆盖`generated-files.json`中自身生成且未被外部修改的具体目标；不递归删除，不改手工源定义和题集，也不影响目录里的其他代理文件。只读校验不写盘。

**只将sources原件交给正常解析/检索。** canonical、manifest中的section正文和所有gold字段仅用于评分；SQL/遍历查询只能用独立`query_plan + store_fixture + as_of`，不能从期望路径构造查询。扫描缺文本与召回失败分开报告。标注由作者助手逐题指定，未从检索结果生成；真人复核状态为pending。此次仅验证夹具，不声称OCR、OpenSearch、PG或模型评测已通过。
