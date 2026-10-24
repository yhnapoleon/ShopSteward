# 基础设施与模型服务

| 交付内容 | 配置入口 | 操作说明 |
|---|---|---|
| 独立 embedding 服务 | [Modelfile](Modelfile) | [Ollama 部署与联调](../docs/runbooks/ollama-embedding.md)、[调用接口](../docs/ollama-embedding-api.md) |
| 完整 Knowledge 服务 | [compose.knowledge.yaml](compose.knowledge.yaml)、[配置模板](../knowledge/.env.example) | [Knowledge 部署交接](../docs/runbooks/knowledge-server-handoff.md) |
| 业务 PostgreSQL | [compose.yaml](compose.yaml)、[配置模板](.env.example) | [项目安装与启动](../README.md#首次安装) |
| Windows 应用启动 | [start_windows.py](start_windows.py) | [项目启动说明](../README.md#启动服务) |

当前 Modelfile 仅声明基础模型 `qwen3-embedding:0.6b`。它不包含模型权重，也不配置监听地址、防火墙或服务自启动；模型 tag 还需配合实际 digest 记录才能追溯版本。

单独提供 embedding 时，调用方发送文本、接收向量，并自行负责文档处理和搜索。部署完整 Knowledge 服务时，文档解析、切分、向量化、索引和检索由 Knowledge API/worker 协同完成。Ollama 可直接运行在宿主机；当前 OpenSearch 与 Knowledge 使用 Docker Compose 管理。

实际局域网地址、访问白名单和机器上的运行状态由部署记录提供。配置模板中的地址不代表服务已对外开放。
