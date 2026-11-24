# AI Knowledge Base QA

一个可离线运行的 AI 领域知识库问答系统（RAG）。导入 Markdown、HTML、纯文本；安装 `pypdf` 后支持 PDF。系统默认用 SQLite FTS5 和关键词重叠检索，回答显示来源、片段和当前模式；没有 API 密钥也能完整演示。配置兼容 OpenAI 的服务后，回答会切换到 `llm` 模式。

## 运行

```powershell
cd kbqa
py -3 -m pip install -r requirements.txt   # PDF 可选支持
py -3 server.py
```

打开 <http://127.0.0.1:8000>。启动时会索引 `data/sample.md`。也可以直接调用接口：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/query -Method Post -ContentType 'application/json' -Body '{"question":"什么是 RAG？"}'
```

导入接口接受 `title`、`source`、`content`；本地脚本可用 `index_document()` 导入 PDF/HTML。模型配置示例：`$env:OPENAI_BASE_URL='https://.../v1'`、`$env:OPENAI_API_KEY='本地填写'`、`$env:OPENAI_MODEL='...'`，不要提交 `.env` 或密钥。

## 验证

```powershell
py -3 tests/test_app.py
powershell -ExecutionPolicy Bypass -File .claude/hooks/preflight.ps1
```

项目材料在 `docs/`：SPEC、功能地图、评审检查点、测试报告和五人分工模板。`mcp_server.py` 可通过 stdio 提供 `search_knowledge_base` 工具。
