# 知源 · 通用知识库问答

公开仓库：[Steven888888986/ai-knowledge-base-qa](https://github.com/Steven888888986/ai-knowledge-base-qa)。[GitHub Actions](https://github.com/Steven888888986/ai-knowledge-base-qa/actions/workflows/verify.yml) 运行应用测试和离线评测；发布证据见 [发布记录](docs/release.md)。

一个可离线运行、支持各领域资料的知识库问答系统（RAG）。内置科学、人文、经济、技术与生活等入门资料及原有 AI 示例；可继续导入任意主题的 Markdown、HTML、纯文本、公开网页，安装 `pypdf` 后支持 PDF。系统结合 BM25 与本地 BGE 向量检索；有证据时可用本地 Qwen 生成带引用的回答，模型不可用或引用格式无效时会返回原文摘录并明确显示离线模式。无需 API 密钥。

“通用”表示不限制资料领域，不表示已收录所有知识或自动联网搜索。内置卡片是自编的入门概述，含参考来源；目录与示例问题见 [知识资料说明](docs/knowledge-sources.md)。资料不足时先拒答、更新统计，再弹窗询问是否需要大模型生成。选择“是”后调用已配置的本地 Qwen，单独显示无知识库依据的补充回答，不附引用；选择“否”或关闭窗口则回到正常界面。需要可追溯或更新的内容时请导入对应原文。

只输入数字（如 `2`、`2024`）时，页面自动进行内容查找：在结果摘要下方直接列出所有匹配文档及全部命中原文片段，相邻的重叠上下文合并，数字高亮并支持打开原文。按连续字符包含匹配，因此 `2` 也会命中 `12`、`2024`。该查找不受问答候选数或引用数限制，也不计入问答质量统计；输入完整问题（如“2 的三次方是多少？”）仍走普通问答。

只输入算式（如 `1+1`）时，资料中须明确写出对应算式及数值结果才提供原文引用。仅出现数字 `1` 或无答案的练习题不算证据；未找到时拒答且不列引用。用户可在随后的弹窗确认调用大模型，生成内容与知识库拒答分开显示。

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

打开 <http://127.0.0.1:8765>。启动时会索引 `data/sample.md` 和 `data/knowledge/` 的多领域资料。旧版本数据库会增量装入新资料，不覆盖同来源的现有文档，不清空问答历史；已导入批次中的文档删除后不会因重启重新出现。如需改端口，在启动服务前设置 `$env:KBQA_PORT='9000'`，再访问对应端口。也可以直接调用接口：

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/query -Method Post -ContentType 'application/json' -Body '{"question":"地球为什么会出现四季？"}'
```

页面的“问答质量统计”在每次问答结束后自动更新：召回率和引用准确率由本地模型评估，明确标为“自动估算”；模型不可用时显示词项规则回退。拒答率按实际拒答次数统计。“人工核验 / 修正”可覆盖自动判断，历史与统计刷新后保留。百分比可能相同，请同时查看分子与分母；无样本不显示假 0%。具体口径与旧记录补评命令见 [实时统计说明](docs/live-metrics.md)。

拒答后的大模型补充生成不修改原问答记录或三项指标，也不重复计数。生成内容仅显示在当前页面，不保存到问答历史或知识库；生成失败时显示错误，可重试，原拒答仍保留。接口 `POST /api/generate` 接受 `{"query_id": 已保存的拒答编号, "confirmed": true}`，问题从该记录读取；未确认、记录不存在或不是拒答时不能生成。

“今天星期几”“今天几号”等日历问题会在每次生成时从系统时钟读取北京时间（Asia/Shanghai，UTC+08:00），并将日期和星期提供给模型。该时间上下文仅用于日历问题；没有联网天气、新闻或行情服务。默认模型是本地 Qwen2.5-1.5B-Instruct，日历修正不代表其他知识回答均已验证。

模型文件和运行时保存在被 Git 忽略的 `models/`、`.runtime/` 目录中；下载脚本固定模型版本并验证 SHA-256。只想使用离线功能时，可跳过模型下载与启动步骤。模型来源、许可和限制见 [`docs/models.md`](docs/models.md)。

文本导入接口 `/api/ingest` 接受 `title`、`source`、`content`；本地脚本用 `index_document()` 导入已提取的文本，用 `import_file()` 解析 PDF/HTML 等文件。网页界面也提供文件上传和 URL 导入。也可配置其它 OpenAI 兼容服务：`$env:OPENAI_BASE_URL='https://.../v1'`、`$env:OPENAI_API_KEY='本地填写'`、`$env:OPENAI_MODEL='...'`，不要提交密钥。

## 验证

```powershell
py -3 tests/test_app.py
powershell -ExecutionPolicy Bypass -File .claude/hooks/preflight.ps1
```

项目材料在 `docs/`：SPEC、功能地图、评审检查点、演示/答辩材料和[测试报告](docs/test-report.md)。AI 需求访谈与关键 prompt 已保存在 `transcripts/requirements-interview.md`；真实缺陷及回归证据在 `collab-log/bugs/`。五位成员的真实姓名、分工及个人贡献记录由组员补充，见 `collab-log/team-template.md`。`mcp_server.py` 可通过 stdio 提供 `search_knowledge_base` 工具。

原 AI 主题答辩材料：[PPTX](presentation/AI领域知识库问答系统-答辩-最终.pptx)、[PDF](presentation/AI领域知识库问答系统-答辩-最终.pdf)、[备用API实录](presentation/AI领域知识库问答系统-API操作实录.mp4)，保留为此前交付快照。当前通用版功能以 SPEC、知识资料说明与[演示脚本](docs/demo-script.md)为准。完整原始要求核对见 [验收审计](docs/acceptance-audit.md)。
