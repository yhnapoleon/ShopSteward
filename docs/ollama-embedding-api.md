# Ollama embedding 接口

更新：2026-10-20。本文约定 ShopSteward 使用的文本向量化协议，字段依据当前 [embedding 适配器](../knowledge/src/shopsteward_knowledge/providers/embedding.py)。服务部署、Modelfile 和版本记录见[运行说明](runbooks/ollama-embedding.md)。本次整理未重新执行模型或跨机器验收。

## 服务范围

接收已切分的文档文本或用户问题，返回对应向量。调用方负责文档解析、切分、向量入库和检索。

| 项目 | 约定 |
|---|---|
| 地址 | `POST http://<服务机IP>:11434/v1/embeddings` |
| 请求格式 | `Content-Type: application/json` |
| 默认模型 | `qwen3-embedding:0.6b` |
| 输出维度 | `1024` |
| 调用方式 | 后端服务通过 HTTP 调用 |
| 鉴权 | 直接访问本机 Ollama 无需 key；项目适配器要求非空占位值 `ollama`，不代表已开启鉴权 |

在服务机本地使用 `127.0.0.1`；另一台机器使用服务机的实际局域网 IP。如果运营方发布了自定义模型名，调用方的 `model` 必须使用实际公布的名称。

## 请求

```json
{
  "model": "qwen3-embedding:0.6b",
  "dimensions": 1024,
  "input": [
    "新旧条码并存期间，需要保留映射并按批次追踪。",
    "条码变更后应该如何管理？"
  ]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `model` | string | 服务端已有的模型名称，必填 |
| `dimensions` | integer | 本项目显式传 `1024` |
| `input` | string[] | 本项目使用非空文本数组，每条文本对应一个输出向量 |

当前适配器每批最多 64 条，每条默认最多 12000 字符，可通过 profile 调整字符预算。这些是项目侧限制，不代表模型的 token 上限或已验证并发容量。查询前缀与文档前缀由调用方 profile 管理，服务端不再额外拼接。

## 成功响应

HTTP `200`。以下为结构示意，向量仅展示前三项，实际每条必须包含 1024 个数值；usage 数字为示意。

```json
{
  "object": "list",
  "model": "qwen3-embedding:0.6b",
  "data": [
    {"object": "embedding", "index": 0, "embedding": [0.012, -0.034, 0.056]},
    {"object": "embedding", "index": 1, "embedding": [-0.021, 0.043, 0.008]}
  ],
  "usage": {"prompt_tokens": 35, "total_tokens": 35}
}
```

调用方按 `index` 对应输入位置，检查结果数量、唯一索引、向量维度及有限数值。项目适配器还会按 profile 配置进行 L2 归一化。

## Postman 与 PowerShell

Postman 选择 `POST`，地址填写服务地址，Body 选择 `raw / JSON`，粘贴上面的请求。Authorization 使用 `No Auth`（直接调用 Ollama 的情形）。

PowerShell 从服务机本地测试：

```powershell
$embeddingBody = @{
    model = 'qwen3-embedding:0.6b'
    dimensions = 1024
    input = @('条码变更后应该如何管理？')
} | ConvertTo-Json
$embeddingReply = Invoke-RestMethod -Method Post `
    -Uri 'http://127.0.0.1:11434/v1/embeddings' `
    -ContentType 'application/json; charset=utf-8' `
    -Body ([System.Text.Encoding]::UTF8.GetBytes($embeddingBody))
$embeddingReply.data | ForEach-Object {
    [pscustomobject]@{ Index = $_.index; Dimensions = $_.embedding.Count }
}
```

预期一条结果，`Index=0`、`Dimensions=1024`。其他机器修改请求地址后执行同一检查。

## 错误与版本约定

| 现象 | 处理 |
|---|---|
| 连接拒绝或超时 | 检查进程、IP、监听范围、防火墙及模型冷启动 |
| 非 200 | 按实际错误响应检查模型名、请求格式及输入长度，不当作成功向量使用 |
| 数量或维度不符 | 拒绝结果，核对模型/profile，避免写入不兼容索引 |

模型名称、实际 digest、维度、归一化方式和输入前缀需要由双方固定。更新模型或输入规范前通知调用方，验证是否需要重新向量化和发布索引。

本协议使用 `/v1/embeddings`；原生 `/api/embed` 的响应结构不同，不能直接替换现有适配器地址。支持字段与占位 key 语义见 [Ollama 官方兼容接口文档](https://docs.ollama.com/api/openai-compatibility)。
