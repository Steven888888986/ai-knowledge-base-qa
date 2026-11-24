# AI Knowledge Base QA

公开仓库：[Steven888888986/ai-knowledge-base-qa](https://github.com/Steven888888986/ai-knowledge-base-qa)。[GitHub Actions](https://github.com/Steven888888986/ai-knowledge-base-qa/actions/workflows/verify.yml) 运行应用测试和离线评测；发布证据见 [发布记录](docs/release.md)。

一个可离线运行的 AI 领域知识库问答系统（RAG）。导入 Markdown、HTML、纯文本；安装 `pypdf` 后支持 PDF。系统结合 BM25 与本地 BGE 向量检索；有证据时可用本地 Qwen 生成带引用的回答，模型不可用或引用格式无效时会返回原文摘录并明确显示离线模式。无需 API 密钥。

小模型仍可能概括错误或漏答：独立审阅发现过 Q/K/V 角色混淆，即使引用能追溯也需要核对原文。实际失败、未采用的提示词试验和边界见 [主张审阅记录](docs/evidence-review.md)。

## 运行

本地模型安装与启动脚本面向 Windows x64，要求 Python 3.11 或更新版本。首次从 GitHub 获取项目后运行：

```powershell
git clone https://github.com/Steven888888986/ai-knowledge-base-qa.git
cd ai-knowledge-base-qa
py -3 -m pip install -r requirements.txt   # PDF 可选支持
py -3 scripts/install_models.py            # 首次下载约 1.2 GB 的模型和 CPU 运行时
powershell -ExecutionPolicy Bypass -File scripts/start-models.ps1
py -3 server.py
```

打开 <http://127.0.0.1:8765>。启动时会索引 `data/sample.md`。如需改端口，在启动服务前设置 `$env:KBQA_PORT='9000'`，再访问对应端口。也可以直接调用接口：

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/query -Method Post -ContentType 'application/json' -Body '{"question":"什么是 RAG？"}'
```

页面的“问答质量统计”随实际问答累计：拒答率自动更新；点击“核验本次回答”选择正确来源并判断每条引用后，召回率与引用准确率更新。“问答记录与核验”可以补评或修改历史判断，刷新页面后保留。未核验时显示“待核验”，不会假报准确率。具体口径见 [实时统计说明](docs/live-metrics.md)。

模型文件和运行时保存在被 Git 忽略的 `models/`、`.runtime/` 目录中；下载脚本固定模型版本并验证 SHA-256。只想使用离线功能时，可跳过模型下载与启动步骤。模型来源、许可和限制见 [`docs/models.md`](docs/models.md)。

文本导入接口 `/api/ingest` 接受 `title`、`source`、`content`；本地脚本用 `index_document()` 导入已提取的文本，用 `import_file()` 解析 PDF/HTML 等文件。网页界面也提供文件上传和 URL 导入。也可配置其它 OpenAI 兼容服务：`$env:OPENAI_BASE_URL='https://.../v1'`、`$env:OPENAI_API_KEY='本地填写'`、`$env:OPENAI_MODEL='...'`，不要提交密钥。

## 验证

```powershell
py -3 tests/test_app.py
powershell -ExecutionPolicy Bypass -File .claude/hooks/preflight.ps1
```

项目材料在 `docs/`：SPEC、功能地图、评审检查点、演示/答辩材料和[测试报告](docs/test-report.md)。AI 需求访谈与关键 prompt 已保存在 `transcripts/requirements-interview.md`；真实缺陷及回归证据在 `collab-log/bugs/`。五位成员的真实姓名、分工及个人贡献记录由组员补充，见 `collab-log/team-template.md`。`mcp_server.py` 可通过 stdio 提供 `search_knowledge_base` 工具。

答辩文件：[最终PPTX](presentation/AI领域知识库问答系统-答辩-最终.pptx)、[最终PDF](presentation/AI领域知识库问答系统-答辩-最终.pdf)、[备用API实录](presentation/AI领域知识库问答系统-API操作实录.mp4)。完整原始要求核对见 [验收审计](docs/acceptance-audit.md)。
