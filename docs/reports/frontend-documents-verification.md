# 文档中心接入与验收

2026-09-08。承接既有K1文档接口，实现前端与必要文件代理。初始实现基准jeffrey `62bf285`；PR前快进到相同文件树的main合并提交 `4944104`。发布范围仅包含文档中心、必要共享组件适配与验收说明。

## PR前复核（2026-09-08）

新增首次上传/原提交重试的异步校验期间场景切换保护：离开旧页面后，不再开始该页面的写请求；已发送的原请求仍保留幂等恢复依据。补充两条受控浏览器用例。

重新执行类型、生产构建、契约、Prettier、测试支撑脚本Ruff与diff检查，均通过。临时生产前端3013＋隔离API8018＋shopsteward_test的一次联合运行 **24 passed（51.7秒）**：文档受控10项、真实文档HTTP/浏览器2项、既有经营概览12项。原件/权限/CAS/副作用边界保持。原始产物在 `var/documents-pr-verification/artifacts`；本节更新下方初版批次的当前验收口径。

## 实现与范围

- 入口：今日/跟进/经营记录页的“资料与简报 → 文档中心”，或 `/?view=documents`，按需加载。
- 既有K1九项操作已有前端承接：上传、筛选分页、资料详情/编辑、追加版本、版本列表与原件信息、下载、归档/恢复。版本内容由列表返回完整元数据，无需重复请求单版本详情接口。
- 商品/供应商关联来自当前店铺catalog；分类以可读标签展示，现有其他分类保留。查看“最近上传”不表示该版本已生效或已建立检索索引。
- 文件代理仅对已注册K1上传/下载开放。上传按实际字节累计限制20 MiB＋128 KiB总请求；原件仍由后端严格校验。下载保留Content-Type、Content-Disposition、request ID，强制nosniff与private/no-store。
- 原提交恢复按身份与店铺隔离，存幂等键/操作/元数据/文件hash，不存凭证与原件正文。丢响应后不自动创建新命令；刷新后重选原文件并核对hash。版本冲突明确提示重新载入，成功后回读最新详情。
- 复用AppDialog，只将固定标题ID改为每实例独立ID，避免新旧弹层的可访问名称冲突。原关闭、焦点、忙碌语义不改。

已用Git差异确认backend、agent、ml、simulation、infra、工作流、依赖、useShop与报价处理代码均未改；既有四份未提交文档修改继续保留。没有实现报价持久化、修复策略/监控或扩展任何其他研究建议。

## 实际验证

| 验证 | 结果与边界 |
|---|---|
| Nuxt类型检查、生产构建、生成契约检查 | 通过；新文档组件独立加载，未加依赖。既有ECharts大chunk提示仍保留 |
| 受控浏览器 | 最终8项通过：入口与完整操作、刷新后的幂等恢复、文件不匹配、元数据冲突、角色/私有权限、资料及版本分页、迟到响应隔离、无效/超大文件、手机/键盘/下载拒绝 |
| 真实文件代理＋PG | 2项通过：临时生产前端3013→隔离API8018→专用shopsteward_test。大于256KB的真实multipart上传、同键重放唯一版本、下载逐字节/hash/文件名/安全响应头、viewer拒写、跨域拒绝、普通业务multipart仍415、非公开路径404、私有/归档下载拒绝、CAS、追加版本、恢复与超限413 |
| 实际浏览器＋真实API | 上述2项之一：上传合成原件、刷新后标题筛选取回、下载字节一致；不是浏览器mock |
| 经营副作用 | 真实HTTP用例前后dashboard.state完整相等。测试只创建独立合成测试店铺/资料；开发数据库、模型、采购与模拟器未写入 |
| 原经营概览回归 | 12项生产受控用例通过，含原确认弹层、场景切换、图表懒加载、移动布局和数据边界；没有重新执行实际采购 |
| 视觉 | 查看桌面列表/详情/上传、手机列表/详情/表单及真实HTTP画面；检查长标题、窄屏不溢出、原生弹层与焦点恢复 |

最终文档10项联合用例18.6秒，原概览12项15.3秒；这是两次运行，不合并冒充一次全量产品验收。初轮分类测试使用包裹label的精确文字定位而失败，改为combobox语义角色；中途重建临时前端造成旧静态资源失效，该批2项加载失败。停止重建、重启临时生产前端后，最终10项全部通过。失败证据保留，没有当作产品通过证据。

运行证据位于仓库忽略目录：`var/documents-final/artifacts`、`var/documents-overview-regression/artifacts`、`var/documents-e2e/*.png`、`var/documents-http`。可重复测试源码随仓库保留。临时3013/8018仅用于验收，任务结束停止；原3000/8000/8001与业务worker保持。

## 复现

普通文档UI用例完全拦截API，不产生真实业务写入：

```bash
corepack pnpm --filter @shopsteward/frontend exec playwright test tests/documents.spec.ts --reporter=line --output=../var/documents-e2e/artifacts
```

真实传输验证需要隔离环境。先从仓库根将TEST_DATABASE_URL配置为已迁移的本机`shopsteward_test`连接，保密提供，不填开发库。然后启动：

```bash
.venv/bin/python frontend/tests/support/documents_backend.py
```

该脚本复用现有后端测试输入与身份，强制库名和loopback检查；每次初始化自己的合成店铺，不调用会清表的pytest fixture，不启动worker/模型，也不迁移。测试原件在`var/documents-http/`，上下文只记录store_id。

另开终端启动独立前端（构建完成后再启动，验证期间不要再次覆盖.output）：

```bash
corepack pnpm --filter @shopsteward/frontend build
NITRO_HOST=127.0.0.1 NITRO_PORT=3013 NUXT_BACKEND_URL=http://127.0.0.1:8018 node frontend/.output/server/index.mjs
```

运行文档中心十二项联合验收（含PR前新增2项）：

```bash
FRONTEND_URL=http://127.0.0.1:3013 DOCUMENTS_REAL=true corepack pnpm --filter @shopsteward/frontend exec playwright test tests/documents.spec.ts tests/documents-transport.spec.ts --reporter=line --output=../var/documents-final/artifacts
```

真实测试文件未显式开启DOCUMENTS_REAL时跳过，不能把跳过解释成真实传输通过。结束时只停止自己启动的临时进程，保留测试证据。生产前端登录使用隔离测试脚本所配置的测试身份，绝不使用开发用户凭证。

## 验证边界

浏览器为Chromium，覆盖桌面1440×1000及手机390×844；未宣称Safari/Firefox、屏幕阅读器全量或可访问性认证。没有压力、并发大文件或公网部署验收；文件传输为有大小上限的内存缓冲，未实现断点续传。后端原有原件孤儿文件/备份等边界保持，不在本轮修改。资料不解析、不自动索引、不交给Agent，也不改变经营账本。
