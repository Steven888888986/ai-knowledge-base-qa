# 协作日志

以下记录为 2026-11-24 本次用户与 AI 助手会话中实际发生的工作，按工作顺序整理。记录者为 AI 助手，不代表五名组员已完成相应贡献；组员个人记录请在 [`team-template.md`](team-template.md) 中据实补充。

| 序号 | 任务与输入 | 决策/实际产出 | 可核验证据 |
|---|---|---|---|
| 01 | 用户选择第二题“知识库问答系统”，要求面向 AI，排除交叉红队 | 将导入、检索、引用、拒答、API 与工程交付拆成可测验收标准 | `transcripts/requirements-interview.md`、`docs/SPEC.md` |
| 02 | 用户说明没有模型 API，要求寻找已训练模型 | 采用本地 Qwen2.5-1.5B-Instruct 与 BGE-small-zh-v1.5；固定版本、许可与 SHA-256 | `docs/models.md`、`scripts/install_models.py` |
| 03 | 实现可导入的 AI 文档知识库 | Markdown/HTML/TXT/PDF 解析与页码保留；同一 source 更新 | `ingestion.py`、`app.py`、页码与更新回归测试 |
| 04 | 实现检索与证据回答 | BM25、BGE vector、RRF hybrid 三种模式；引用携带来源和原文 | `retrieval.py`、`app.py`、`docs/feature-map.md` |
| 05 | 修复离线哈希碰撞导致旧问题命中新内容 | 要求词项支持，补充来源更新回归用例 | `bugs/bug-01-hash-vector-false-positive.md` |
| 06 | 修复未知问题没有拒答 | 区分检索候选与支持证据，证据不足返回拒答和空引用 | `bugs/bug-02-irrelevant-evidence-not-refused.md` |
| 07 | 实现网页与服务接口 | 导入/删除/预览文档、提问、检索模式、引用和状态展示；HTTP 流程有自动化验证 | `static/`、`server.py`、`tests/test_app.py` |
| 08 | 配置 AI 开发工具与检查 | 自定义 skill、MCP search、preflight hook、reviewer agent、CI 与关键 prompt 留档 | `.claude/`、`.agents/`、`.mcp.json`、`.github/`、`transcripts/` |
| 09 | 发现 K23 提示注入题引用了通用 RAG 资料 | 修正 BM25 和 cosine 不同量纲的证据强度比较，新增回归用例；本地 Qwen 定点验证返回正确资料 | `test_citations_exclude_weaker_bge_match_when_bm25_is_close`、`app.py` |
| 10 | 组织答辩材料与演示步骤 | 生成 12 页答辩 PPTX/PDF、演示脚本与讲稿；更正与当前实现不符的 FTS5 描述 | `presentation/`、`docs/defense.md`、`docs/demo-script.md` |
| 11 | 对修复后的代码做提交前验证 | `tests/test_app.py` 14 项通过；preflight 的编译、测试、敏感信息扫描与离线评测门槛通过 | `docs/test-report.md`、`eval/report.md` |
| 12 | 审计交付材料真实性 | 测试报告补入实际执行结果；成员姓名、实际分工和个人反思保留待填；交叉红队按用户要求跳过 | `docs/test-report.md`、`collab-log/team-template.md` |
| 13 | 原始五张要求图逐项复核 | 补齐 MCP 选型、上下文演化、真实会话导出与 goal 工具记录 | `docs/acceptance-audit.md`、`docs/mcp-design.md`、`transcripts/conversation-export.md` |
| 14 | 补正向导入与无模型验收 | 安装缺失的 pypdf；真实双页 PDF 引用到第2页；PyTorch 网页成功导入；完全关闭模型后评测通过 | `docs/evidence/import-smoke.json`、`eval/no-model/` |
| 15 | 录制备用演示 | 隔离服务执行健康、导入、Qwen 引用回答、拒答；真实日志渲染60秒MP4 | `presentation/视频说明.md`、`docs/evidence/demo-api.json` |
| 16 | 保存真实 Git 演化 | 从初版 `74ed939` 创建实现提交 `b35cde6`，提交代码、测试和上下文修订 | `git log`、`docs/configuration-evolution.md` |
| 17 | 按只读 reviewer 职责核对32题 | 发现 K04 生成角色混淆及漏答/限定词丢失；多种 prompt 试验没有稳定改善，未部署候选 | `docs/evidence-review.md`、`docs/evidence/prompt-trial*.json` |
| 18 | 用户恢复浏览器并手动完成 GitHub 设备授权 | 创建公开仓库；发布前14项测试与32题评测再次通过；真实 Qwen/BGE 接口正常 | `docs/release.md`、`eval/release-check/` |
| 19 | 推送并核对公开仓库 | Git 直连失败后使用既有本地代理成功推送；远端 tree 与本地一致；首次 Actions 的14项测试、32题评测通过 | `docs/release.md`、`docs/evidence/github-actions.json`、公开仓库 Actions |
| 20 | 用户要求网站随多次问答显示指标，并选择核验后真实统计 | 新增持久化问答记录、三张指标卡、正确来源与逐条引用核验；拒答率自动累计，质量指标核验后更新；修改核验不重复计数；补后端与浏览器验收 | `metrics.py`、`static/metrics.js`、`docs/live-metrics.md`、`docs/evidence/live-metrics-ui.json` |
| 21 | 用户发现质量指标仍待核验，明确改选“自动估算，问答后立即更新” | 接入本地模型自动评估，失败时标注词项规则回退；自动与人工判断分开存储，人工优先；补评已有快照并新增自动流程回归 | `auto_eval.py`、`metrics.py`、`tests/test_auto_eval.py`、`docs/live-metrics.md` |

GitHub 公开发布与实际 CI 结果见 [`docs/release.md`](../docs/release.md)，成员个人记录仍由本人据实补充。
