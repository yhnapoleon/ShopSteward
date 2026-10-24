# v6接入ShopSteward与LangGraph

用户已授权实现接入的一切必要工作，包括前端API和展示；直接执行，无新增审批。目标目录为主ShopSteward（YH），原预测研究工作树及实验产物保留。现有未提交HANDOVER/PROJECT_CONTEXT不覆盖。

## 交付与范围

可从前端选当前门店SKU、运行v6、看到七日曲线/周总量/来源/版本/质量说明；LangGraph查询同一已保存预测并引用，补货问题读取库存→预测→方案。后台实际规划仅使用时间范围匹配且显式开启的observed预测；历史演示不能自动替换真实门店方案。采购审批沿用原接口。

不重复训练。打包现有F6 .5/F3 .25/W2 .125/N3 .125模型及各自mapping、300条元数据；模型服务只根据请求历史推理。84..374日完整历史，日期递增无缺日，明确观察截至日，特征不读取之后销量。演示另打包M5每系列至1885的最后374日，仅请求historical_demo时使用，明确2016年日期。

M0：可推理、正确门店权限、完整历史、缺数据不返回0、无未来销量、过期/异店预测不作为当前依据。M1：37 tests及模型已验证证据、真实HTTP/graph工具闭环与前端交互检查。M2生产独立验收/大规模性能不阻塞本次展示。v6质量注明历史八周34.976%、相对v5仅0.57%、额外四周略差；不修改旧offline_model_validated。

## 固定接口

ML service token-auth on127.0.0.1:8053：
- GET /health/ready
- GET /v1/model -> {model_version, feature_profile, minimum_history_days:84, recommended_history_days:374, weights, evaluation, supported_series:[{series_id,item_id,dept_id,cat_id,store_id,state_id}], limitations}
- GET /v1/demo-history/{series_id} -> {series_id, observation_end_date, history:[{date,sold_quantity,complete:true}], source_kind:historical_demo}
- POST /v1/predict body {store_id,sku_id,series_id,history:[{date,sold_quantity,complete}],observation_end_date,timezone:"UTC",input_state_version:int}; strict inputs. Response {forecast_id,model_version,feature_profile,series_id,store_id,sku_id,input_state_version,observation_end_date,horizon_start,horizon_end,daily_predictions:[{date,quantity}],total_quantity_raw,predicted_quantity,unit:"piece",generated_at,valid_until,source:"model",model_name:"ShopSteward v6",assumptions,evaluation}. generated/validuntil wallUTC, horizons localmidnighttimezone input (backendUTC default). Hash id binds model/request. ML_SERVICE_TOKEN and ML_V6_BUNDLE env.

Backend：FORECAST_V6_ENABLED defaultfalse、FORECAST_V6_URL、FORECAST_V6_TOKEN、FORECAST_V6_TIMEOUT_SECONDS(default8)。原主后端不装torch。
- GET /api/v1/stores/{store_id}/forecast/model（viewer也可读）->model descriptor above。
- GET /api/v1/stores/{store_id}/forecast?sku_id=X -> {status:READY|STALE|UNAVAILABLE,reason:string|null,store_id,sku_id,mode:observed|historical_demo|null,usable_for_planning:bool,forecast:MLResponse|null,history:[{date,sold_quantity,complete}],model:descriptor|null}。
- POST /api/v1/stores/{store_id}/forecast/refresh（operator/admin）body {sku_id,series_id?:string,mode?:observed|historical_demo,history?:list,observation_end_date?:date,activate_for_planning:bool=false} -> same current wrapper。首次须series_id/mode；再次可复用已存输入。historical_demo自动取ML demo历史但禁止activate；observed输入由用户明确导入，没有自动将缺少销售记录补成0。持久化input与immutable evidence，可读取最近预测供图与前端共用。

后端schema须导出稳定类名ForecastV6Current、ForecastV6Refresh、ForecastV6Model（嵌套可dict避免过大schema，前端本地接口严格已知shape）。后台读函数 `read_current(session, store_id, sku_id, settings, now=None)->dict`供LangGraph只读调用，不在持有业务锁时发ML HTTP。API refresh在读取授权快照后结束事务再HTTP，回来复核store/state/绑定版本后保存；外部scope/model预测字段不可由LLM传入。

后台规划集成：在snapshot.prepare可读事务中读取已保存v6当前依据。仅activate_for_planning=true、mode=observed、有效期内、source history终日与业务simulation_time的预测日范围一致才采用；必须正确减去已过去预测日，当前未完日保守约定清楚说明，若不能建立可靠剩余量则返回FORECAST_UNAVAILABLE而不猜。初版允许只在预测首日午夜匹配时使用（有明确说明），避免把完整7日销量当成任意时刻剩余需求。未启用此模式的原固定场景继续用固定来源并在工具中说明plan是否用v6。

LangGraph `get_forecast`空参数、后端绑定mission store/sku，返回持久wrapper；READY才附type=forecast引用{id=forecast_id,version=model_version,store_id,sku_id,mode}。STALE/UNAVAILABLE返回ok=false且有明确data/无引用，required_read_tools阻止无依据结论。显式预测请求、补货判断在启用时强制读预测（通用定义/否定不强制）。系统提示区分历史演示与observed，依据来自工具，预测不是保证、不是采购量。最终输出复核预测引用与当前记录，缺失/变化时说明不可据旧数据断言。

前端入口放现有首页当前门店业务区：ForecastPanel组件接storeId/skuId/canManage，读取model/current；历史演示series下拉+明确按钮；observed JSON导入+refresh；可选显式用于规划开关仅observed。状态、原始日期、曲线/表、一次ceil周总量、版本、适用范围、v6质量限制可见。切店/切SKU清理状态并防迟到响应；引用链接能打开相同id，若已变更说明。无需新增图表依赖。

验证：ML真实4组件对保存v6预测一致；后端鉴权/只读/失败/未绑定/状态复核/规划适用规则；真实HTTP至已打包模型和LangGraph实际StateGraph的工具回传（可控模型测试不冒充真实LLM）；有现成LLM环境再跑一次真实模型问答。前端typecheck/build/接口生成及必要Playwright。启动隐藏服务并记录自有PID，现有8000服务若需更新只操作已核对的ShopSteward进程，不杀未知端口进程。

用户后续明确调整：前端和Agent统一称为‘模型推演，仅供参考’，不主动强调历史年份；真实日期保留在可展开详情。内部 historical_demo/observed 数据模式与规划适用规则不变。Current wrapper另含activate_for_planning以准确保留刷新开关。
