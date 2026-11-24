# 测试与验证报告

最新增量（2026-11-24）：知识库从 AI 扩展为不限领域，新增20张入门资料卡并保留原 AI 示例。**27 项后端/HTTP/MCP 回归 + 11 项评估器测试**、编译、密钥扫描和32题原 AI 开发集评测门槛通过，见 [`general-knowledge-preflight.txt`](evidence/general-knowledge-preflight.txt)。本轮 AI 开发集的非时间结果与原报告一致，新输出单独保存在 [报告](evidence/general-knowledge-ai-regression-report.md) 与 [逐题数据](evidence/general-knowledge-ai-regression-results.json)，不覆盖历史证据。

新增跨领域验收在隔离数据库进行：8个非 AI 领域的离线问题均命中预期来源，个人密码问题拒答；真实 Qwen/BGE 完成四季、机会成本、Python 列表/元组和原 RAG 问题，生成回答均带有效引用。Edge 实际点击示例后，三项指标与 HTTP 返回一致；1440px/375px布局无横向溢出或脚本错误。见 [完整结果](evidence/general-knowledge-smoke.json)、[桌面](evidence/general-knowledge-desktop.png)、[手机](evidence/general-knowledge-mobile.png)。原指标9组回归亦通过，见 [指标回归](evidence/general-knowledge-metrics-regression.json)。这些题目取自内置示例，仅验证集成与来源链路，不代表全领域准确率。

跨领域测试暴露旧长提示词漏写引用，以及通用词“多少”导致密码问题误命中。分别用简化的句末编号提示词和停用词修复，缺编号/越界编号仍必须回退为原文摘录；提示词全部试验与失败结果见 [对照记录](evidence/general-knowledge-prompt-check.json)。自动评估仍可能误判：此次 Python 问题的生成答案正确，但评估器将复利、隐喻、统计也列为相关来源，原始结果已保留。因此界面百分比只验证聚合与同步，不作为独立核验的真实质量结论。

现有网站完成增量升级：文档从1份增至21份，片段从1个增至41个；原文档、片段和3条问答所有字段均与升级前备份一致，原统计不变，见 [升级核对](evidence/general-knowledge-upgrade.json)。更新后的网页通过只读 Edge 检查，累计仍为3问且页面与聚合接口一致，见 [现有网站检查](evidence/general-knowledge-live-ui.json)。私有问答正文与数据库未提交仓库。各卡来源与核验范围见 [知识资料说明](knowledge-sources.md)。

前次增量：网站自动估算通过 **22 项后端/HTTP/MCP 回归 + 11 项评估器测试**，编译、密钥扫描和32题离线评测门槛通过；原始输出见 [`auto-metrics-preflight.txt`](evidence/auto-metrics-preflight.txt)。隔离 Edge 浏览器的9组检查覆盖连续问答立即更新、人工覆盖/纠正、迟到 GET 与核验 POST、刷新持久化、375px布局；无页面脚本错误，见 [`auto-metrics-ui.json`](evidence/auto-metrics-ui.json)。

真实本地 Qwen/BGE 的隔离 HTTP 提问返回 llm 回答、local-model 自动评估和即时非空质量指标，见 [`auto-metrics-http-model.json`](evidence/auto-metrics-http-model.json)。另一次三引用长回答的 Qwen 评估实际耗时约11.3秒，输入1882 tokens、输出93 tokens，三个编号均有判断；这只是合成案例的集成验证，不是质量基准，见 [`auto-metrics-model.json`](evidence/auto-metrics-model.json)。用户本机旧记录先备份后补评，保留问题、原回答、时间与人工判断；私人历史不进入仓库。

前一版人工核验模式的18项测试和7组浏览器验收保留在 [`live-metrics-preflight.txt`](evidence/live-metrics-preflight.txt) 与 [`live-metrics-ui.json`](evidence/live-metrics-ui.json)。下文14项的记录是首次发布时的历史快照。

日期：2026-11-24（Asia/Shanghai）
环境：Windows、Python `py -3`；确定性测试不依赖网络或模型 API。

## 自动化检查

| 检查 | 命令 | 结果 |
|---|---|---|
| 应用与协议回归 | `py -3 tests/test_app.py` | 14 项通过；运行时间 5.036 秒 |
| 提交前检查 | `powershell -ExecutionPolicy Bypass -File .claude/hooks/preflight.ps1` | 通过：编译检查、14 项测试、敏感信息扫描、离线评测门槛 |

测试覆盖文本切分边界、中文检索与可追溯引用、BM25/BGE 证据选择回归、拒答、重复 source 更新、PDF 页码、三种检索消融模式、提示注入文档处理、本地模型不可用时的安全回退；还会启动临时本地 HTTP 服务测试健康检查、上传、提问、引用、文档列表与删除、拒绝 loopback URL 导入，并通过 stdio 测试 MCP 初始化、工具列表和搜索。数据集结构和敏感信息扫描也有自动化断言。

## 确定性离线评测

提交前检查运行了 32 题开发集（24 个可回答问题、8 个库外问题）。下表取自上述 hook 的本次输出；百分比由题数换算，时延为本机测量值。

| 检索模式 | Recall@1 | Recall@3 | 证据引用准确率 | 可追溯率 | 正确拒答率 | 误拒率 | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| BM25 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 36.414 |
| BGE vector | 95.8% | 95.8% | 100.0% | 100.0% | 100.0% | 4.2% | 28.587 |
| Hybrid | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 30.042 |

这是项目自编开发集，不代表真实场景泛化能力；引用准确率按标注来源和证据句核对，不等价于模型回答中所有主张的事实正确率。时延会随设备和模型服务变化。

## 本地模型

除量化指标外，另有一次按只读 reviewer 配置进行的32题主张审阅。它发现 K04 生成角色混淆、K09 漏答等问题；不将来源指标100%报告为全部答案正确。完整结论及未采用的提示词试验见 [`evidence-review.md`](evidence-review.md)。

Qwen2.5-1.5B-Instruct 与 BGE-small-zh-v1.5 的来源、许可、校验和及启动方法记录在 [`models.md`](models.md)。生成模型评测单独记录在 [`../eval/local-model/report.md`](../eval/local-model/report.md)，不得与确定性离线指标合并。服务默认使用 8765 端口，可通过 `KBQA_PORT` 覆盖；自动化 HTTP 测试使用临时端口。

## 补充验收：完全无模型与真实导入

以下记录独立于上面的指标表，不覆盖 `eval/report.md`。

- **完全无模型环境**：设置 `KBQA_EMBEDDINGS_ENABLED=0` 和 `KBQA_LLM_ENABLED=0`，执行 `py -3 scripts/evaluate.py --check --output-dir eval/no-model`，退出码为 0，输出 `PASS: evaluation gates`。此时向量模式使用有明确标记的词法哈希回退，不是 BGE 语义嵌入。Hybrid 的 Recall@3 为 100.0%、证据引用准确率为 96.0%、可追溯率与正确拒答率均为 100.0%、误拒率为 0.0%。[原始命令输出](evidence/no-model-evaluation.txt)、[独立评测报告](../eval/no-model/report.md)、[逐题结果](../eval/no-model/results.json)。
- **真实 PDF 字节导入**：用 `pypdf 7.1.1` 构造可提取文字的双页 PDF，经真实 `/api/upload` 上传，返回 HTTP 201；向 `/api/query` 提问 `What does LoRA freeze?` 后，引用指向 `upload://acceptance-two-pages.pdf` 第 2 页，片段与数据库中相同 `chunk_id` 的原文完全一致。不是 mock 页码，也不覆盖扫描件 OCR。
- **公开官方网页导入**：真实导入 [PyTorch Learn the Basics](https://docs.pytorch.org/tutorials/beginner/basics/intro.html)，`/api/import-url` 返回 HTTP 201；提问 `What is the FashionMNIST dataset?` 后，引用来源等于网页最终 URL、页码为 `null`，引用片段含 `FashionMNIST` 并与存储片段完全一致。没有使用登录、付费或私人来源。

导入验收使用临时数据库和临时 HTTP 端口，关闭两个模型以单独验证解析、入库、检索与来源链路；回答如实标记为 `offline`。命令：`py -3 docs/evidence/import-smoke.py`。验收脚本：[import-smoke.py](evidence/import-smoke.py)；原始结果：[JSON](evidence/import-smoke.json)、[控制台输出](evidence/import-smoke.txt)。全部 5 个断言组通过。

环境准备记录：首次在 `py -3` 环境执行时发现未安装可选 PDF 依赖；执行 `py -3 -m pip install -r requirements.txt` 后重试通过。[首次环境错误](evidence/import-smoke-initial-missing-pypdf.txt)、[安装输出](evidence/pdf-dependency-install.txt)。

## 公开仓库 CI

首次发布提交 `92925d4` 的 [GitHub Actions](https://github.com/Steven888888986/ai-knowledge-base-qa/actions/runs/45411516210) 已实际通过。Ubuntu / Python 3.12 下运行14项测试与32题无模型离线评测，详情与原始日志链接见 [`release.md`](release.md)。该结果与本机 BGE/Qwen 评测分开记录。
