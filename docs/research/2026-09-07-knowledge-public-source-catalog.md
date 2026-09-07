# ShopSteward扩展语料：首批公开来源目录

检索日期2026-09-07。用途是指导有意义的资料采集，而非把搜索结果计作已经入库的原件。当前0份新公开原件进入K1/检索索引。下列10个来源家族为候选；简繁英译本、PDF/HTML镜像只计同一家族。未保存全文，不对再分发权作推断。

| ID | 发布方与资料 | 拟覆盖的业务任务 | 获取证据与处理 |
|---|---|---|---|
| PUB-001 | CFS：[采购、接收及贮存](https://www.cfs.gov.hk/sc_chi/trade_zone/safe_kitchen/Purchasing_receiving_and_storage.html) | 到货检查、供应商文件、储存与周转流程 | 浏览工具已打开正文；HK、简体；英文版同家族；获取原件时记录使用条件/hash |
| PUB-002 | CFS：[食品回收指引](https://www.cfs.gov.hk/tc_chi/import/import_icfsg_08.html) | 撤回通知、下架隔离、记录和跟进所需证据 | 已打开正文；HK、繁体；“食品回收”在此指撤回问题食品，不与捐赠混淆 |
| PUB-003 | CFS：[食物回收计划的食物安全指南](https://www.cfs.gov.hk/tc_chi/multimedia/multimedia_pub/files/Food_Safety_Guidelines_for_Food_Recovery_c.pdf) | 剩余食品接收/捐赠工作流及适用条件 | 已打开28页PDF并取得文本；HK、繁体；与PUB-002保留同词不同业务含义的自然难例 |
| PUB-004 | FEHD：[Food Hygiene Code](https://www.fehd.gov.hk/english/publications/code/code_index.html)；[完整PDF](https://www.fehd.gov.hk/english/publications/code/code_all.pdf) | 经营卫生、设备/场所、流程和人员培训的长文证据 | 官方搜索结果确认目录及PDF候选；正文尚未逐章获取/审阅；整手册计一份，章节为chunks |
| PUB-005 | GS1：[Traceability](https://www.gs1.org/standards/traceability) | 追溯概念、事件与记录字段的区分 | 官方搜索内容已读取；完整获取待验证；作为概念说明，不能替代门店实际事件数据 |
| PUB-006 | GS1：[Global Traceability Standard](https://www.gs1.org/standards/gs1-global-traceability-standard/current-standard)；[PDF候选](https://www.gs1.org/sites/default/files/docs/traceability/GS1_Global_Traceability_Standard_i2.pdf) | 供应商/收货/物流标识的关系建模与证据来源 | 已读取官方索引内容，完整原件获取和版本对应待核验；不将PDF与网页计两份 |
| PUB-007 | GS1：[Fresh Fruit and Vegetable Traceability Guideline](https://www.gs1.org/standards/fresh-fruit-and-vegetable-traceability-guideline/current-standard) | 生鲜批次、包装重组与追溯关系 | 搜索可读，直接打开403；标记reference_only，未绕过限制，不能声称全文采集成功 |
| PUB-008 | GS1：[GTIN Management Standard](https://ref.gs1.org/standards/gtin-management/)；[净含量变化规则](https://www.gs1.org/1/gtinrules/en/rule/266/declared-net-content) | 相似包装/不同规格的标识判断 | 官方搜索已发现；规则页直接打开失败；同一规则集计一家族，完整获取待核验 |
| PUB-009 | CFS：[预先包装食品中未有标示的致敏物](https://www.cfs.gov.hk/tc_chi/multimedia/multimedia_pub/multimedia_pub_fsf_165_04.html) | 标签遗漏、顾客问询需要哪些原始材料 | 官方搜索已发现；正文待完整读取；历史案例只能标历史，不声称当前停售 |
| PUB-010 | CFS：[食物安全重点控制系统与业界指引](https://www.cfs.gov.hk/tc_chi/programme/programme_haccp/programme_haccp.html) | 饮品/简餐场景后续主题筛选入口 | 仅来源发现入口，不作为整页目录灌入语料；需选择相关具体指南并单独验证 |

来源说明均为助手编写的采集用途摘要，不是原文完整替代品。来源题材以现有饮品/简餐/零售模拟场景为依据，不能仅靠这一组卫生资料完成供应商合同、活动条款与复盘配额。下一批优先找厂商包装/兼容/设备手册和正式商品说明；缺乏公开合同、真实门店事件的部分使用明确标记的合成经营资料。

采集记录必填字段：source_family_id、publisher、title、url、language、jurisdiction、publication_date或null、retrieved_at、acquisition_status、use_terms_status、content_sha256（只有实际取得原件后填写）、local_original_path、source_kind、supersession信息。不得给未下载资料生成虚假hash/页码。

参见[云端知识与扩展语料设计](../superpowers/specs/2026-09-07-cloud-knowledge-and-corpus-design.md)中的规模、去重、题集隔离及分批验收要求。
