# Claude 工作上下文

这是一个无框架、Python 标准库优先的 AI 领域 RAG 演示。`app.py` 负责导入、切分、SQLite FTS5/关键词检索与离线答案；`server.py` 提供 HTTP API 与静态页面。

回答证据链：问题 → 检索片段 → 引用 → 回答。模型服务是可选的，只有同时配置 `OPENAI_BASE_URL` 和 `OPENAI_API_KEY` 才会调用。
