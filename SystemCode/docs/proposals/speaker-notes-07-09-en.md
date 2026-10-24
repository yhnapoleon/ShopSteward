# ShopSteward：第 7–9 页技术讲稿（模块简述版）

展示英文架构图顶部 **03 Learning system**、下方 **01 System map**。图作为评委阅读的背景，不逐个指图、不报具体数字、不念技术栈清单。以下英文正文用于朗读。

## 07 — How the main modules work together

Behind that demo, the system has a few main roles. The workspace lets the owner give instructions and review proposals. The agent understands the request and gathers evidence through tools.

Business services handle stock, cash and purchasing, while a background worker tracks changes and follows up on orders. The owner still approves spending. Together, these modules turn a conversation into a business process.

## 08 — The supporting and learning modules

The agent is supported by a few specialised modules. The forecasting service estimates demand. The knowledge service retrieves supplier terms and other documents, so recommendations can point back to their sources. A simulator lets us test changes in sales, deliveries and cash before connecting to a real store.

On the learning side, our next step is to turn business scenarios into verified training examples. We would use these to fine-tune a task model, helping it choose tools, supply the right parameters, and ask useful questions when information is missing. We would then compare it with the original model.

## 09 — Where the architecture could go next

Looking further ahead, we want to explore multi-agent coordination. A supervisor could assign analysis, evidence gathering and planning to specialised agents, then bring their results together. They would share task context and use the same business tools.

We also want to explore reinforcement learning. The simulator could provide feedback on whether a task was completed and whether the agent used tools efficiently. We could use that feedback to improve the policy.

These are future directions. We would only keep the extra complexity if it improves task completion without adding too much delay or cost.

That leads to the next part: how will we test whether the system actually helps?

## 演讲与衔接提示（不朗读）

- 第 7 页接原第 6 页的 “Now, how is it built?”，按用户工作区、Agent、业务服务和后台任务说明分工。

- 第 8 页说明预测、知识与模拟器分别提供什么，再自然过渡到计划中的数据准备和微调。

- 第 9 页用 could / would 介绍 Multi-Agent 与 RL，明确它们是未来方向；最后接第 10 页的评测设计。

- 不需要切换视图、打开节点详情或介绍图中每个框。将图留给评委阅读，自己讲清主要关系。

- 本段不把原稿其他页面的 Beam search、quotation reuse 或课程内评测承诺改成 RL；如果团队调整交付范围，应另行同步其他页面。

- 可在每段之间自然停顿；强调业务分工、模块如何互补，以及哪些属于未来探索。
