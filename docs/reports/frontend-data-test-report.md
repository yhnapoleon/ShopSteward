# 首批前端只读接口实施与测试报告

日期：2026-09-07。基准：`YH / da79cbded5a6493f63788a62c666201ab1d5a7c6`；本批实现保留在工作区，未提交或推送。

## 结果

数据字典定义的7个GET已实现，实际backend为**29个操作、28条路径**。复用现有表和确定性账本，没有新增表、迁移、依赖或worker handler，没有改变采购执行链路。

| 新增接口 | 返回内容 |
|---|---|
| GET /api/v1/me | 当前身份、角色、店铺作用范围 |
| GET /api/v1/stores | 当前身份可见的店铺 |
| GET /api/v1/sales | 已记录销售事实，按来源序号分页 |
| GET /api/v1/sales/summary | 模拟经营时间、UTC日桶、已记录销量与成交额 |
| GET /api/v1/actions | 可筛选采购列表，与已有单项Action响应一致 |
| GET /api/v1/inbounds | 当前收货量、剩余量、到货状态和逾期判断 |
| GET /api/v1/ledger-entries | 期初状态及采购、到货、销售、需求调整的经营效果 |

## 验证结果

| 检查 | 结果 / 范围 |
|---|---|
| backend全量pytest | **186通过，0失败，0跳过**；19 API、48单元、119真实PostgreSQL/跨服务集成；63.12秒 |
| simulator全量pytest | **12通过，0失败，0跳过**；3.29秒，两套DB测试串行执行 |
| Ruff / 格式 | backend app/tests/migrations/tools全部通过，108个Python文件格式通过；补充契约校验器Ruff通过 |
| Alembic check | backend及simulator均无新增upgrade操作；迁移头保持0006_periodic / sim_0002_purchases |
| 既有契约 | backend设计26操作/37示例、services设计10操作/16示例、共享schema与负例、2个Plan hash通过 |
| 前端补充契约 | 7操作/22设计schema/14响应示例，8个既有共享schema完全一致，成功例子通过runtime schema；10个schema反例及4个跨字段反例通过 |
| 真实HTTP | 7接口响应均通过设计schema校验；401/403/404/422边界通过；实际OpenAPI与导出一致；详见[HTTP证据](../api/frontend-data-http-result.json) |
| 代码复审 | 日期解析、极限日期、记录定位日志及关联查询问题修复后复审，无剩余实质问题 |

原始pytest输出及JUnit XML保存在Git忽略的`var/frontend-*-pytest.log`、`var/frontend-*-tests.xml`；可携带的运行结果为[验证汇总](../api/frontend-data-verification-result.json)及HTTP证据。B0-05/06/07历史报告和进程证据未被覆盖。

## 关键行为与故障回归

- **权限与隔离**：viewer仅见授权店铺；admin可分页发现店铺；空角色看不到店铺数据；service不能冒充用户；跨店查询、未知SKU/Mission按既有隐藏资源语义处理。非法参数和未知/重复query key返回422。
- **销售口径**：重复事件不增加销量；列表分页不影响汇总；按来源序号而非实际时间排序；from包含/to排除，偏移日期规范化为UTC；空桶只表示无已记录销售，coverage固定RECORDED_EVENTS_ONLY。
- **快照与只读**：在读取context后，另一连接提交销售；当前响应仍读到旧版本与旧列表，下一请求读到新版本与新列表。重复调用7接口前后State及events/ledger/jobs/commands/alerts/timeline计数不变。
- **采购与到货**：采购SUCCEEDED不代表已到货；0/部分/全收分别展示。Mission取消后UNKNOWN采购继续可见，回执确认后到货明细也仍可见。未知ETA返回未知逾期，模拟时间等于ETA不算逾期，全收始终不逾期。
- **流水**：INIT返回期初State；采购回执没有模拟时间，返回null。真实HTTP按limit=1翻页仍能完整还原2笔采购、2条到货和7条账本；单独筛选到货效果也可读取。
- **损坏事实**：非法已存事件、缺失/不匹配Action、无效数量等不能被当成0或空列表；返回503 INVALID_STORED_DATA且retryable=false。日志只记录安全的记录ID/类型，不泄漏存储payload或身份凭证。

开发中实际复现并修复：到货流水在采购不在同页时漏加载关联Action；纯数字日期被解释为Unix时间戳；UTC转换及9999年最后一天桶边界溢出；到货订单数量与采购快照不一致；JSON日志格式器丢弃记录定位字段。新增测试验证这些分支，旧接口路径清单同步增加7个已实现路由。

## 真实HTTP验收边界

工具启动并停止独立API进程，绑定`127.0.0.1:8014`，使用临时且仅授权SC01店铺的viewer身份。读取的是B0-07验收后保存的SC01，**本轮没有重新推进该模拟场景**，也没有再次进行B0-07进程故障注入。读取到的两笔采购为40/20件，销售10件/200元；账本重建现金400元、应收200元、现货70件、在途0，与持久State一致。业务State和表记录数在读取前后不变。

日期区间与日桶固定UTC；既有Action/Receipt/State DTO保持既有序列化语义，事实时间携带RFC3339时区。销售来源过滤后使用类型化解析，避免SQL日期转换把损坏事实误报为普通数据库故障；当前按门店销售历史扫描，汇总在内存完成，未承诺大规模历史分析性能。跨页没有持久快照，采购/到货状态可能变化，前端刷新应重置cursor。

这批接口不提供真实订单接入、多仓/批次、当前售价、回款/退款/毛利、Agent/记忆/技能，也不把经营流水称为完整财务总账。前端页面尚待实现。

## 复现

在backend目录按HANDOVER设置专用`shopsteward_test`及`shopsteward_sim_test`后运行`../.venv/Scripts/python.exe -m pytest -q`；随后在simulation目录串行运行同一命令。两侧运行`../.venv/Scripts/python.exe -m alembic check`。

仓库根运行：

```powershell
.venv/Scripts/python.exe docs/api/validate_contracts.py
.venv/Scripts/python.exe docs/api/validate_frontend_data_contract.py
.venv/Scripts/python.exe backend/tools/verify_frontend_reads.py
```

HTTP工具要求8014空闲、开发DB可用以及原B0-07场景仍在；只停止自身API，不修改凭证文件。正常开发在backend目录运行`../.venv/Scripts/python.exe -m app`，Swagger为`http://127.0.0.1:8000/docs`。只读接口不需要worker在线，但数据是否持续更新由源同步与worker决定。
