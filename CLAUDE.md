# Claude 工作上下文

这是一个无框架、Python 标准库优先的 AI 领域 RAG 演示。`app.py` 负责导入、切分、SQLite 持久化与离线答案；`retrieval.py` 在 Python 中计算 BM25 并融合向量检索；`server.py` 提供 HTTP API 与静态页面。项目不使用 SQLite FTS5。

回答证据链：问题 → 检索片段 → 引用 → 回答。默认尝试本机 `http://127.0.0.1:8081/v1` 的 Qwen 服务，本机调用不需要 API 密钥；`KBQA_LLM_ENABLED=0` 可关闭生成。外部 OpenAI 兼容服务可通过 `OPENAI_BASE_URL`、`OPENAI_MODEL` 和按需填写的 `OPENAI_API_KEY` 配置。模型不可用或引用无效时应明确回退，不得把离线摘录标记为 `llm`。
