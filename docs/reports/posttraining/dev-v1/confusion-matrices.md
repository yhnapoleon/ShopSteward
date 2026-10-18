# 动作混淆矩阵

每格是决策步数，missing包含不允许补发脚本回复的后续步；不等同独立episode数。

## decision/B0

| 预期 / 实际 | evaluate_plan | revise_plan | clarify | handoff | no_action | invalid/missing |
|---|---:|---:|---:|---:|---:|---:|
| evaluate_plan | 70 | 7 | 6 | 0 | 0 | 2 |
| revise_plan | 1 | 51 | 12 | 0 | 1 | 1 |
| clarify | 2 | 3 | 54 | 0 | 0 | 0 |
| handoff | 0 | 0 | 7 | 3 | 0 | 0 |
| no_action | 0 | 2 | 5 | 0 | 3 | 0 |

## decision/B1

| 预期 / 实际 | evaluate_plan | revise_plan | clarify | handoff | no_action | invalid/missing |
|---|---:|---:|---:|---:|---:|---:|
| evaluate_plan | 85 | 0 | 0 | 0 | 0 | 0 |
| revise_plan | 0 | 66 | 0 | 0 | 0 | 0 |
| clarify | 1 | 0 | 57 | 1 | 0 | 0 |
| handoff | 0 | 0 | 0 | 10 | 0 | 0 |
| no_action | 0 | 0 | 0 | 0 | 10 | 0 |

## execution/B0

| 预期 / 实际 | evaluate_plan | revise_plan | clarify | handoff | no_action | invalid/missing |
|---|---:|---:|---:|---:|---:|---:|
| evaluate_plan | 70 | 7 | 5 | 0 | 0 | 2 |
| revise_plan | 1 | 48 | 5 | 0 | 1 | 1 |
| clarify | 2 | 0 | 28 | 0 | 0 | 0 |
| handoff | 0 | 0 | 0 | 0 | 0 | 0 |
| no_action | 0 | 0 | 0 | 0 | 0 | 0 |

## execution/B1

| 预期 / 实际 | evaluate_plan | revise_plan | clarify | handoff | no_action | invalid/missing |
|---|---:|---:|---:|---:|---:|---:|
| evaluate_plan | 84 | 0 | 0 | 0 | 0 | 0 |
| revise_plan | 0 | 55 | 1 | 0 | 0 | 0 |
| clarify | 0 | 0 | 30 | 0 | 0 | 0 |
| handoff | 0 | 0 | 0 | 0 | 0 | 0 |
| no_action | 0 | 0 | 0 | 0 | 0 | 0 |
