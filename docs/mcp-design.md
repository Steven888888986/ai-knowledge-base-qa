# MCP 设计与选型

`mcp_server.py` 提供只读 `search_knowledge_base` 工具；`.mcp.json` 配置通过 `py -3 mcp_server.py` 以 stdio 启动。工具输入为查询文本与结果上限，输出包含来源、页码、片段编号和原文，供 MCP 客户端继续核验和生成回答。

采用 MCP 的理由是将检索作为有结构化输入输出的工具暴露给兼容客户端。客户端可以发现工具并直接消费证据字段，不必为每个客户端拼接 shell 命令或解析面向人的终端文本。HTTP API 继续服务网页；MCP 与 HTTP 共用检索逻辑，避免两套索引规则。

CLI 适合启动服务、导入批次和运行评测，因此项目仍用命令行完成安装与验证。MCP 的用途是让客户端在对话中调用检索，并非声称它比 CLI 更适合所有任务。

自动验证位于 `tests/test_app.py` 的 `MCPSmokeTest.test_stdio_initialize_list_and_search`：发送 `initialize`、`tools/list` 和 `tools/call`，检查服务返回工具名称及预先索引的来源。一次依照项目 skill 流程使用 HTTP 检索和生成的记录见 [`skill-demo.md`](skill-demo.md)；该记录不是 MCP 客户端调用的替代证据。
