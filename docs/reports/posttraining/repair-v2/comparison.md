# 受限决策修复复评

Historical dev comparison differs in call time and execution fixtures; diagnostics compare prompt versions on shared frozen inputs. Agent-reviewed synthetic dev only.

## 针对性诊断

| 分类 | v1 | v2 |
|---|---:|---:|
| negative_ascii | 6/6 | 6/6 |
| negative_chinese | 6/6 | 6/6 |
| positive | 6/6 | 6/6 |
| negated_negative | 6/6 | 6/6 |
| upper | 6/6 | 6/6 |
| lower | 5/6 | 6/6 |
| exact | 6/6 | 6/6 |
| followup_cn | 6/6 | 6/6 |
| followup_en | 6/6 | 6/6 |
| packaging | 6/6 | 6/6 |

## 原dev复评

| 模式 | v1任务成功 | v2任务成功 | 修复 | 新失败 |
|---|---:|---:|---:|---:|
| decision | 198/200 | 199/200 | 2 | 1 |

decision变化：`{"fixed": ["dev-pt07-011", "dev-pt07-014"], "regressed": ["dev-pt01-019"], "persistent_failures": [], "pending": []}`

| execution | 139/140 | 140/140 | 1 | 0 |

execution变化：`{"fixed": ["dev-pt04-019"], "regressed": [], "persistent_failures": [], "pending": []}`


每成功任务调用/token、第二步完成与重复澄清、原始指标及所有分母见comparison.json。金额未配置时为null；参数正确率仍只覆盖期望工具步骤。

诊断变体来自已知失败，不用于训练或独立test。
