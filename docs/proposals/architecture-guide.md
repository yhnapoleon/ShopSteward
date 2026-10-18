# ShopSteward proposal 架构图

交互入口：[shopsteward-architecture.html](shopsteward-architecture.html)。浏览器直接打开即可；不需要启动 ShopSteward、数据库或模型服务，也不依赖网络资源。

英文展示版：[shopsteward-architecture-en.html](shopsteward-architecture-en.html)。采用暗色画布、青色/琥珀色/淡紫色状态编码、动态连线与 Focus 展示模式；保留全部三种视图、阶段动画、节点详情和导出。青色为已实现，琥珀色为实验，淡紫色虚线为规划。页面、节点说明与指标均为英文，项目依据链接保留原始文档语言。

英文静态图：[Current](architecture-current-en.svg) · [Future](architecture-future-en.svg) · [Multi-agent](architecture-multiagent-en.svg) · [Learning loop](architecture-learning-en.svg)。

## 文件

| 文件 | 用途 |
|---|---|
| [交互 HTML](shopsteward-architecture.html) | 三个视图、阶段切换、演进动画、节点详情、缩放、SVG 导出、打印 |
| [当前架构 SVG](architecture-current.svg) | 当前业务系统与独立任务策略实验 |
| [理想架构 SVG](architecture-future.svg) | 当前能力与未来扩展的整体关系 |
| [Multi-Agent SVG](architecture-multiagent.svg) | 单 Agent 主循环与专长协作的演进 |
| [学习闭环 SVG](architecture-learning.svg) | Eval → Data → SFT → Serving，以及 RL 反馈循环 |

SVG 是静态矢量图，可放大、插入支持 SVG 的文档或幻灯片。静态文件是本次 HTML 的快照；后续修改 HTML 时，可使用页面“导出 SVG”重新生成。打印按钮调用浏览器打印，可选择保存 PDF；不同打印机设置可能影响分页。

## 演示方式

1. 选择“系统全景 → 当前实现”，讲清用户如何从备货委托走到方案、人工确认、采购与回执。预测与知识为决策提供依据，后端承担经营状态与业务计算。
2. 点击“播放演进”，展示 Data/SFT 和远期研究逐步进入系统。每阶段约 3.8 秒，可暂停或手动切换。
3. 切换“Agent 协作 → 理想架构”，说明 supervisor 如何调用经营分析、知识证据、方案执行跟进等专长子图，并共享任务状态、汇总结果。
4. 切换“学习闭环 → 理想架构”，说明数据如何经工具验证进入 SFT，以及模拟环境如何产生轨迹、计算奖励、更新策略并回到独立评测。
5. 点击节点展示职责、产出与依据；Esc 取消节点高亮并停止播放。窄窗口可使用放大与横向滚动查看细节。

## 可配合架构图使用的讲述

ShopSteward 面向零售补货与采购跟进，把经营数据、七日需求预测、知识检索、Agent 对话和采购执行连接成一个业务闭环。已有系统能够提供工具与可核对的执行结果，独立评测链路进一步把模型的工具选择、参数绑定和澄清能力变成可衡量任务。

下一阶段将从新业务规格生成并验证训练数据，以目标模型训练前基线为对照，开展任务 SFT 和服务接入。远期探索两条路径：通过专长 Agent 协作处理复杂任务；通过模拟器轨迹与可验证奖励优化策略。研究将比较任务成功率、调用与 token 开销、端到端时延，以及模拟场景中的库存、缺货和现金影响。

## 状态与依据

- **蓝色：已有实现。** 指工作区代码与项目记录存在；不代表本次启动或完成生产验收。
- **橙色：实验验证。** 受限任务策略与 Eval 在独立链路运行，尚未替换通用 Agent 主循环。
- **紫色虚线：未来规划。** 包括 Data、B2、SFT、任务模型自部署、Multi-Agent、RL 与真实业务连接。切换理想视图不会把它们标成已完成。

当前记录为合成 dev 决策 199/200、核心执行 140/140、已知问题诊断 60/60。这三组口径不同，不能相加或替代独立测试；也不是 SFT 后成绩或真实门店成功率。既有简历草稿中的示例数字未作为架构事实引用。

Qwen3-8B、LoRA、vLLM 是计划中的候选；LangGraph supervisor + 专长子图是本 proposal 建议的多 Agent 路径。GRPO/PPO 等 RL 算法需要根据环境、动作空间和训练支持选型。偏好优化 DPO 可另做对照，不能与在线 RL 等同。联合多智能体 RL 属于更远期探索。

主要依据（核对日期 2026-09-26）：

- [现有架构](../architecture.md)与[项目 README](../../README.md)。
- [Agent 运行时](../../agent/src/shopsteward_agent/)、[事项承接协议](../../backend/app/work_items/README.md)。
- [预测 v6 接入记录](../reports/forecast-v6-product-integration.md)。
- [受限策略复评](../reports/posttraining/repair-v2/comparison.md)与[Data 交接](../reports/posttraining/repair-v2/data-handoff.md)。
- [Data 与 B2 计划](../superpowers/plans/2026-09-17-data-preparation-and-b2-plan.md)、[SFT/Data/Eval 总计划](../superpowers/plans/2026-09-14-phase2-sft-data-eval-plan.md)。

## 本次验证

已检查内嵌 JavaScript 语法、三个视图 × 三个阶段的节点展示、规划节点状态、节点详情、图形边界及依据路径；并在浏览器中检查布局。HTML 和 SVG 均不加载外部脚本、字体或样式。
