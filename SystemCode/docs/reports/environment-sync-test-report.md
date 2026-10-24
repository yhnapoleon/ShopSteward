# 模拟器驱动当前经营环境：修复与验收

2026-09-07。用户报告 console 新 SANDBOX 现金1000，产品前端仍显示旧 SC01 采购后的800。数据已导入 backend，但前端只在初始化时发现店铺，并优先采用浏览器保存的旧店铺；此前联调遗漏了外部创建后已打开前端自动跟随的行为。

## 当前行为

- console 默认联动后端。初始化任务成功提交经营状态后，backend 将最新创建请求中的成功场景作为当前环境，通过 StoreList.active_store 返回。依据为 PostgreSQL 持久任务及结果，重启不丢；未完成/失败创建不切换，较早请求晚完成不会覆盖较新请求。该字段独立于列表分页，遵守店铺权限和非空角色要求。
- 前端启动优先采用后端当前环境；运行中每2.5秒发现环境变化并重新加载实际数据。手动查看历史场景有明确标识和返回当前环境入口；下一次新建仍会自动跟随。历史账本、订单、任务和场景不被覆盖。
- 切换清空旧审批弹窗、任务数据及分页游标；在途历史分页响应不写入新场景。未决采购确认保留原幂等回执，跨场景也显示恢复入口。Agent 创建/发送/取消/主动跟进的异步返回校验原店铺与任务，避免覆盖新会话或草稿。
- 新场景不会代用户建立委托；产品前端“开始备货跟进”创建的新任务及 Agent 使用当前场景数据。独立模拟保留为显式单独调试；浏览 console 历史 run 不重新激活它。

## 验证

- backend 场景发现/权限/读视图及 Operations：23 passed（9.31s）。
- 查询参数与契约单元测试：11 passed（3.09s）。
- console 原异步回归：3 passed。
- 最终浏览器：5 passed（1.4m），包含4项受控 Agent 延迟响应与1项真实业务/官方 gpt-5.6-luna 链路。
- 前端类型、生产构建、生成契约、相关 Python Ruff 与 git diff --check 通过。

浏览器使用隔离的 shopsteward_environment_test / shopsteward_sim_environment_test 数据库和3018/8018/8019端口，不替换用户场景。原产品页不刷新、不手动选店：console 创建现金1234、库存37的 SANDBOX 后自动显示相同数据，旧审批框关闭且旧店无采购；销售3件后产品显示库存34、应收60、现金1234，刷新仍一致。新任务的官方 Luna 调用 get_dashboard 并报告1234/34/60，Run属于新任务会话。见[模型与环境证据](environment-sync-e2e.json)。

首轮失败包含测试消息定位器无法匹配带子标签的气泡，以及误用工具名get_state的断言；修正为日志包含断言和实际get_dashboard。复测又发现首次店铺加载关闭刚打开的控制框，已修复。最终完整5项回归通过，不将中间失败批次列为通过。

## 实际运行现场

用户原 SANDBOX store_306305666ce640468b083731e7788e8d / run_5ad2f12638a14148b7c2ffa41c2e96f8 保留：现金1000、库存20、在途0、应收0、需求60、源序号0。API重启后同一环境仍被返回，实际 Edge 产品页也显示1000。见[两端现场状态](environment-user-sandbox.json)。预测版本标识分别代表源预测与后端计算投影，不要求字符串相同。

用户服务继续使用3000/8000/8001和原业务/Agent worker。最终API根PID39108（操作前核对），清单 var/windows-stack-20260907-133412/processes.json 已更新；隔离验收进程已回收。无迁移、无提交或推送；测试数据库保留供复现。

复现：在frontend运行 `node node_modules/nuxt/bin/nuxt.mjs build`，再在仓库根运行 `.venv/Scripts/python.exe backend/tools/verify_environment_sync.py agent-scope.spec.ts`。使用已有私密模型配置，凭据不进入报告。
