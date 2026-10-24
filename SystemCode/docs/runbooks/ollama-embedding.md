# Ollama embedding 部署与联调

更新：2026-10-20。适用于提供 embedding HTTP 服务的同事，操作示例以 Windows PowerShell、仓库根目录为起点。完整 Knowledge 部署沿用[既有手册](knowledge-server-handoff.md)。本次只补充文档，未启动服务、下载模型或修改网络配置。

## 1. 模型准备与 Modelfile

安装 Ollama 并启动应用后，检查客户端和模型：

```powershell
ollama --version
ollama list
```

模型不存在时再拉取（需要下载权重）：

```powershell
ollama pull qwen3-embedding:0.6b
```

仓库的 [infra/Modelfile](../../infra/Modelfile) 当前内容为：

```text
FROM qwen3-embedding:0.6b
```

直接使用基础模型即可调用 embedding。如果需要根据该文件创建项目自定义名称，可执行：

```powershell
ollama create shopsteward-embedding:0.6b -f infra/Modelfile
ollama show shopsteward-embedding:0.6b --modelfile
```

创建后，自定义名称为 `shopsteward-embedding:0.6b`，请求及 Knowledge 配置必须使用该名称。它是本部署选择的名称，不是自动生成的通用模型名。创建后仍需通过真实 embedding 请求验证。

当前 Modelfile 只引用基础模型，没有新增参数或训练行为。`FROM` 的 tag 不固定模型 digest，也不包含服务网络配置。命令与文件语义见 [Ollama Modelfile 文档](https://docs.ollama.com/modelfile)。

## 2. 监听与局域网访问

只在本机使用时保留默认 `127.0.0.1:11434`。需要为其他机器提供服务时，先确认允许访问的机器，再配置监听与防火墙。

Windows 桌面应用方式：在托盘退出 Ollama，在用户环境变量中设置 `OLLAMA_HOST=0.0.0.0:11434`，再从开始菜单启动 Ollama。已运行的进程不会自动读取新环境变量。

也可以在退出原 Ollama 应用后，在 PowerShell 前台启动：

```powershell
$env:OLLAMA_HOST = '0.0.0.0:11434'
ollama serve
```

此窗口保持运行；`Ctrl+C` 停止该前台服务。不要和已占用同一端口的桌面进程重复启动。设置及重启规则见 [Ollama 网络与环境变量说明](https://docs.ollama.com/faq#how-can-i-expose-ollama-on-my-network)。

在 Windows 防火墙设置 TCP 11434 入站规则，限定到约定的调用方 IP 和实际使用的网络配置文件。`0.0.0.0` 是监听地址，不能作为给同事的调用地址；对外公布服务机的实际局域网 IP。

直接 Ollama 接口的占位 key 不提供认证。需要独立 API key 或只允许 embedding 路由时，应增加具备相应限制的代理；仅做端口白名单不会把 Ollama 变成只提供一个路由的服务。Postman/后端联调通常无需修改浏览器 CORS 设置。

## 3. 验证顺序

1. 在服务机 `GET http://127.0.0.1:11434/api/tags`，确认实际模型名和 digest。
2. 按[接口文档](../ollama-embedding-api.md)发送一条 embedding 请求，检查 HTTP 200、输入输出数量及 1024 维。
3. 从调用机器使用服务机 IP 重复请求；本机通过不代表局域网已通过。
4. 在实际运行 Knowledge 的进程或容器里重复验证，确认该运行环境可访问服务地址。
5. 完整项目联调时，真实上传一个测试文档，以 `hybrid-v1` 建索引并发布；检查检索结果包含 `dense`，没有相关降级告警。

首次请求可能包含模型加载时间。先做短文本预热，再检查项目的超时预算。`ollama ps` 可查看当前已加载模型及运行资源；不能把一次成功响应当作并发或性能保证。

## 4. Knowledge 调用方配置

在 Knowledge 进程使用的配置中设置；使用现有 Compose 管理器时，写入由 [knowledge/.env.example](../../knowledge/.env.example)复制的私有配置文件（例如 `var/knowledge-precloud/private.env`），不要写进业务数据库的 `infra/.env`。

```dotenv
KNOWLEDGE_EMBEDDING_URL=http://<服务机IP>:11434/v1/embeddings
KNOWLEDGE_EMBEDDING_API_KEY=ollama
KNOWLEDGE_EMBEDDING_MODEL=qwen3-embedding:0.6b
KNOWLEDGE_EMBEDDING_DIMENSIONS=1024
KNOWLEDGE_EMBEDDING_NORMALIZE=true
# REVISION 填实际获取并记录的模型 digest；前缀沿用当前建库 profile。
```

若发布的是自定义模型名称，替换上面的 MODEL。完整 URL/API_KEY/MODEL/DIMENSIONS 必须一起配置；修改后重启相应 API 和 worker。项目配置与校验以 [Settings](../../knowledge/src/shopsteward_knowledge/config.py) 为准。

| Knowledge 所在环境 | embedding 地址选择 |
|---|---|
| 与 Ollama 同一宿主机进程 | `http://127.0.0.1:11434/v1/embeddings` |
| Windows Docker Desktop 容器访问宿主机 | `http://host.docker.internal:11434/v1/embeddings`，仍需验证宿主机监听与防火墙 |
| 另一台机器 | `http://<服务机局域网IP>:11434/v1/embeddings` |

容器内的 `127.0.0.1` 指容器自身。宿主机直接运行 Ollama 不要求 Docker；本项目目前的 OpenSearch 和 Knowledge 使用 Compose 管理。

入库请求显式提交 `{"profile_id":"hybrid-v1"}`，现有索引接口省略该字段仍默认 `lexical-v1`。业务后端同时设置 `KNOWLEDGE_RETRIEVAL_PROFILE=hybrid-v1`。既有纯关键词文档需要重新索引并发布，不能只切换查询配置。

## 5. 模型版本和变更记录

`model` 名称相同不代表字节版本永远相同。每次部署记录下表，并从 `/api/tags` 获取实际 digest。不要根据 Modelfile 推测量化版本、硬件性能或当前运行状态。

| 字段 | 本次部署填写 |
|---|---|
| 日期、负责人 | 待填 |
| 仓库 commit、Ollama 版本 | 待填 |
| 对外 IP/端口与允许调用方 | 待填 |
| 实际请求 model、基础模型 tag、完整 digest | 待填 |
| 输出维度 | 1024；以请求验证为准 |
| 查询/文档前缀、归一化配置 | 记录与现有索引对应的 embedding profile |
| 本机/跨机器/Knowledge 环境验证 | 分别填结果与时间 |
| 耗时、批量与并发条件、运行资源 | 实测后填写；未测则标明未测 |

升级前保留旧模型/profile 和运行记录。在新空间重新向量化、验证并发布后，再切换调用方；回退时恢复匹配的模型配置和发布版本。即使维度相同，也不能默认两套模型向量兼容。改模型名或输入前缀也应检查项目 profile 身份变化。

## 6. 常见故障与交付清单

| 现象 | 检查 |
|---|---|
| `address already in use` | 已有桌面 Ollama 或另一 serve 进程占用端口；确认归属后沿用或正常退出 |
| 本机成功、远程失败 | 使用的 IP、OLLAMA_HOST 是否生效、防火墙来源范围、网络连通性 |
| Postman 成功、Knowledge 失败 | 容器地址、模型名称、完整 endpoint、占位 key、模型输入与 deadline |
| 有检索结果但没有 dense | 是否实际向量化并发布 hybrid-v1；查询 profile、warnings、embedding 请求是否成功 |
| 重启后不可用 | Ollama 是否启动、网络环境变量是否持久配置、主机是否休眠、模型是否仍存在 |

给调用方提供：可达地址、精确模型名、维度、digest、输入规范、允许来源、服务运行时间、已测容量及[接口文档](../ollama-embedding-api.md)。后续若承诺固定延迟或并发，另提交有硬件、样本和测量条件的验证报告。
