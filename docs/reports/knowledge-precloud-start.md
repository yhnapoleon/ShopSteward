# 上云准备执行起点

2026-09-08。用户已授权实施全部本地准备计划。

- 当前实际git HEAD为602a6c614237bfe40f4d7c191fe20b7070ea1449，分支YH；保留已有计划/交接修改。历史6fb71fa/b7db9a0不再作为源码基线。
- 现有K1单元起点：`python -m pytest -c backend/pyproject.toml backend/tests/unit/test_knowledge_storage.py backend/tests/unit/test_knowledge_contract.py -q`，57 passed，4.37s。
- Docker普通与提权只读检查均未连接到Desktop Linux Engine；已请求用户手动启动，未尝试启动Desktop。PG/真实HTTP起点待服务可用时补测。
- 当前已有全栈部署记录显示K1开发库曾迁移0010；本次尚未连接确认，不更改或重启8000/8001。
- 执行按语料工具/公开来源/解析模块分工，服务契约与集成集中处理；依赖、共享迁移和对外契约变更统一协调。

本文件记录起点，不是完成报告。
