# macOS 本地开发

<!-- md-alignment-2026-09-08 -->
## 当前Mac mini接续补充（2026-09-08）

三阶段已通过[PR #11](https://github.com/yhnapoleon/ShopSteward/pull/11)、[PR #12](https://github.com/yhnapoleon/ShopSteward/pull/12)合并，业务代码 `1bbcad5` 需要 `0012_agent_progress`。Mac mini开发库已在第二阶段备份并升级0012；下文9382779基准、0009/0010迁移、空前端和初次测试数字继续保留原环境配置时点，不表示当前版本。

本指南的start/status/migrate/test仍是该Mac mini环境入口；实际进程每次用status核对，不能沿用旧PID。三阶段没有改变其他机器环境、业务调度或模拟器迁移。真实模型保持关闭，未启动Agent worker；已有窗口中的旧Windows模型记录不改变本机设置。

组合验证见[交付说明](reports/agent-workspace-delivery.md)。全部后端/Agent测试须按本脚本使用backend/pyproject.toml配置；语料的Office/PDF用例还需将KNOWLEDGE_DOCUMENT_PYTHON指向本机已存在且包含对应库的文档Python运行时。该值因机器而异，缺配置的失败不能算业务通过，也不能为测试删改原业务实现。
<!-- /md-alignment-2026-09-08 -->

2026-09-07 · 已在Apple Silicon Mac完成本机配置和验证。基准为main提交 `9382779` 加本次未提交的Mac适配改动；不是新的团队合并版本。真实模型由用户明确暂缓配置，当前只启动业务worker。

## 日常使用

在ShopSteward仓库根目录执行：

```bash
# 启动本机数据库、模拟器、后端、业务worker和前端
.venv/bin/python infra/local_dev.py start

# 查询状态
.venv/bin/python infra/local_dev.py status

# 停止本脚本登记的应用进程和专用数据库，数据保留
.venv/bin/python infra/local_dev.py stop
```

| 服务 | 地址 | 当前用途 |
|---|---|---|
| 前端 | http://127.0.0.1:3000 | v0.3样式的基础业务前端；接入情况与边界见[前端说明](../frontend/README.md) |
| 后端 | http://127.0.0.1:8000/docs | Swagger接口；受保护操作需要本机配置中的用户token |
| 模拟器 | http://127.0.0.1:8001/docs | 合成经营环境，服务token与用户token分开 |
| PostgreSQL | 127.0.0.1:55432 | 本项目独立实例，开发库与测试库分开 |

脚本遇到未登记的端口占用会拒绝启动，不终止不明进程。停止时检查所登记PID的启动时点，不清数据库，不强制杀进程。没有配置登录自启；重启电脑后按上述start命令启动即可。

## 依赖、配置与数据位置

- Python 3.12.13，uv 0.11.6；完整Python依赖由[uv.lock](../uv.lock)锁定。
- Node 22.23.1；使用仓库指定的pnpm 10.17.1，通过 `corepack pnpm` 调用，避免PATH中其他pnpm版本。本次新增[pnpm-lock.yaml](../pnpm-lock.yaml)固定前端解析结果：Nuxt 4.5.2、Vue 3.5.42。
- PostgreSQL 17.11由Homebrew安装。本机使用原生专用实例，不运行Docker Compose；团队的[Compose文件](../infra/compose.yaml)保持原样。
- Python环境、PostgreSQL数据、前端pnpm虚拟存储和日志统一在 `~/.local/share/shopsteward/`，位于iCloud项目目录之外。仓库 `.venv` 是其虚拟环境链接；本机 `.npmrc` 指定外部pnpm虚拟存储位置。
- `backend/.env`、`simulation/.env`、`infra/.env` 链接到上述目录的 `config/`，目标文件权限600，父目录700；随机本地凭证不写文档、不提交。`infra/.env`仅记录原生实例端口，不是可直接启动Compose的Docker配置。
- `.venv`、`.npmrc`、`.env`、node_modules和运行结果均从Git排除；新机器克隆不会带来本机数据库、凭证、虚拟环境或个人Git钩子。本页的启动脚本复用本次已初始化的专用实例，不是空机器一键安装器。

后续Python依赖变化时，在仓库根按已更新的锁文件同步：

```bash
UV_PROJECT_ENVIRONMENT="$HOME/.local/share/shopsteward/venv" UV_LINK_MODE=copy uv sync --frozen --all-packages --all-groups --python 3.12
corepack pnpm install --frozen-lockfile
```

这两条命令需要已有本机链接和配置；更换机器须先根据模块README准备独立数据库、随机凭证和本地路径。不要照抄其他机器的.env或运行状态。macOS本机没有配置真实模型API密钥；`AGENT_ENABLED=false`，start命令也显式关闭真实模型和Agent worker。

## 迁移与验证

```bash
# 有新的数据库迁移时执行；不清理现有数据
.venv/bin/python infra/local_dev.py migrate

# 后端+Agent及模拟器现有测试，自动使用专用测试库
.venv/bin/python infra/local_dev.py test

# 前端构建验证
NUXT_TELEMETRY_DISABLED=1 corepack pnpm --filter @shopsteward/frontend exec nuxt build
```

专用库分别为 `shopsteward` / `shopsteward_test` 和 `shopsteward_sim` / `shopsteward_sim_test`；后端与模拟器使用各自账号。test命令只注入测试库连接，不把测试指向开发库；同一测试库不要同时运行多套测试。当前迁移分别为 `0009_agent_scopes` 与 `sim_0002_purchases`，四个库均已应用。

需要验证实际API/worker/simulator闭环时，先start，再执行：

```bash
.venv/bin/python infra/local_dev.py smoke
# 停止并重启服务后，复核刚才场景的持久状态
.venv/bin/python infra/local_dev.py smoke --verify-restart
```

smoke会创建合成SC01数据并执行模拟采购，不是只读检查；不连接真实店铺、不调用模型。结果写 `~/.local/share/shopsteward/logs/macos-periodic-smoke.json`，不会覆盖仓库历史证据。`--verify-restart`要求已经成功运行本机smoke，并实际停止/启动过服务。

## 本次修复与实测

1. 后端和模拟器的SQLAlchemy依赖显式声明 `[asyncio]`。原依赖在Apple Silicon的`arm64`平台未装greenlet，首次数据库迁移因此失败；该额外依赖按[SQLAlchemy官方说明](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#asyncio-platform-installation-notes-including-apple-m1)声明。Python既有锁定版本未升级，只补充所需依赖关系和分发元数据。
2. Agent测试的事件循环钩子在非Windows平台改为返回默认工厂映射，保留Windows Selector分支。原返回None被已锁定的pytest-asyncio 1.4.0拒绝，导致Mac测试无法收集。
3. 新增[本机服务管理脚本](../infra/local_dev.py)和前端锁文件，准备一致的启动、停止、迁移、测试及SC01验证入口。

本次后端+Agent 226项、模拟器12项测试通过，失败/跳过均为0；Ruff、格式、接口契约、数据库迁移漂移检查通过；Nuxt准备和构建通过，三个HTTP入口返回200。SC01通过真实本机业务进程完成，停止应用及PostgreSQL、重启后复核通过；现金40000分、现货70，未重复采购。机器摘要见[macOS验证记录](reports/macos-development-verification.json)。原始JUnit、进程日志和场景记录留在本机日志目录，不包含在本次共享材料中。

这些结果说明本机开发与确定性业务验证可运行，不等于已完成前端业务界面、真实模型联调、完整产品三条验收链或课程效果实验。

## 前端联调版的本机接入

`start`仅向前端开发进程注入现有本机用户凭证，留在Nitro私有运行配置，不输出到客户端；开发控制保持只在合成环境使用。重启已登记的前端进程后配置才生效。生产构建不自动使用这个本机身份。应用状态以status和实际响应为准；真实模型仍关闭。

Nuxt4.5.2声明需要vue-router5.2，本轮将骨架原直接依赖4.6.4对齐5.2.0，消除路由类型插件冲突；前端依赖锁保留确切版本。业务前端测试会创建新的合成店铺，旧场景不清理。
