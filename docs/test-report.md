# 测试与验证报告

最新增量（2026-11-25）：用户截图中“今天星期几”被生成模型答为星期五。确认服务使用既定的 Qwen2.5-1.5B，原请求没有系统时间；重新调用时曾碰巧答对星期三，见 [修正前再次调用](evidence/clock-grounding-before.json)。为当前/相对日期问题或简短日历提问提供每次从系统时钟计算的北京时间及昨今明三日的日期、星期；普通计算与星期制度等问题不附当前日历。全量附加时间曾干扰1+1，被否决，真实输入输出对照见 [提示词试验](evidence/clock-grounding-prompt-trials.json)。

48项应用测试、11项评估器测试及32题原评测门槛通过，见 [提交前检查](evidence/clock-grounding-preflight.txt)。新增跨午夜、跨年、闰日的时间注入与无关问题隔离回归；原 AI 评测非时间结果一致且恢复历史文件，见 [比对](evidence/clock-grounding-ai-regression.json)。6项隔离 HTTP/Edge 验收使用真实模型，无输出 mock：当前日期返回2026-11-25星期三、跨年固定时钟返回2027-01-01星期五、1+1仍为2，生成前后历史及指标一致，见 [验收](evidence/clock-grounding-ui.json)与[截图](evidence/clock-grounding-result.png)。这是功能修复，不能证明1.5B模型所有知识回答都正确。

网站已更新并对截图中的既有问题重新调用生成接口，返回“今天是2026年11月25日，星期三。”；保留21份文档、41片段与9条历史全部字段，统计未变，见 [本机验证](evidence/clock-grounding-live.json)。未向真实历史新增测试问答。

前次增量（2026-11-25）：新增拒答后选择大模型生成。知识库先返回拒答并更新指标，再弹窗询问；确认后按保存的原问题调用 Qwen，单独显示无知识库依据的内容和空引用。取消不生成，生成成功、失败、取消及重试不更改原问答、核验或指标。纯数字查找与有依据问答保留原流程。

真实 Qwen/BGE 隔离 HTTP 验证中，RAG 问题得到带引用的 `llm` 回答；`1+1` 在无数学依据时拒答，确认后返回 `llm-general` 的“1+1等于2。”。拒答率从0/1变为1/2，补充生成后仍为1/2，历史与全部指标一致。见 [实际模型结果](evidence/generation-fallback-model.json)与[复现脚本](evidence/generation-fallback-model.py)。这是一组功能集成样例，不代表一般知识准确率。

独立 HTTP/无界面 Edge 的19项检查通过，覆盖先更新指标再询问、是/否/Escape/关闭、重复点击、失败重试、取消与迟到结果、原拒答核验、数字匹配及零结果不弹窗、纯文本安全、桌面/手机布局。浏览器测试使用受控模型 HTTP 服务，明确不冒充实际模型，见 [验收](evidence/generation-fallback-ui.json)、[弹窗](evidence/generation-fallback-dialog-desktop.png)、[手机生成结果](evidence/generation-fallback-result-mobile.png)。修复了用户停止等待时 JSON 响应写入断开连接产生异常日志的问题，并补回归。46项应用测试、11项评估器测试、提交前 hook 与原32题 AI 开发集门槛通过，见 [提交前检查](evidence/generation-fallback-preflight.txt)；原评测除时间外结果一致，历史文件恢复原字节，见 [比对](evidence/generation-fallback-ai-regression.json)。

现有网站已加载新增界面，原21份文档、41个片段及8条历史的所有字段和三项统计均与本轮备份一致；只读检查没有添加测试问答，见 [现有网站验收](evidence/generation-fallback-live.json)。

前次增量（2026-11-25）：修复 `1+1` 因分词丢失运算符、仅凭数字 `1` 重合而引用无关文档的问题。[修复前](evidence/expression-lookup-before.json)在没有该表达式的内置资料中返回3个错误来源，[修复后](evidence/expression-lookup-after.json)拒答且引用为空。纯算式现在扫描全部片段，要求完整表达式与明确数值结果，直接摘录对应等式；只有练习题、不同算式或更长算式的局部命中均不能引用，不调用生成模型补算。分数、科学计数等未支持的结果形式保守拒答，避免截取成错误答案。

数字查找改为在主结果摘要下直接列出全部匹配原文，同文档远距命中保留，重叠上下文合并；页码无法可靠定位时留空并支持查看全文。**41项应用/HTTP/MCP测试、11项评估器测试**及32题原 AI 开发集门槛通过，见 [提交前检查](evidence/expression-lookup-preflight.txt)；原 AI 评测非时间结果一致，历史报告保留，见 [比对](evidence/expression-lookup-ai-regression.json)。独立 HTTP/Edge 的17项检查通过，包括模型开启时算式分支零网络调用、仅练习题拒答、明确等式正例、23份测试文档的25个片段全部直显、原文第7页定位、文本安全、零结果、QA恢复与统计隔离、1440px/375px布局，见 [验收](evidence/expression-lookup-ui.json)、[桌面](evidence/expression-lookup-desktop.png)、[手机](evidence/expression-lookup-mobile.png)。测试截图包含合成资料。规则自动估算仍可能把操作数重合判作可回答，原始误判结果保留；这些百分比不作为真实质量分数。

现有网站已更新：输入 `2` 的9份文档及全部命中均在主结果下直接显示；当前资料的临时副本中 `1+1` 返回拒答和空引用。21份文档、41个片段及7条历史的所有字段与更新前备份一致，统计未变，Qwen/BGE正常，见 [本机验收](evidence/expression-lookup-live.json)。算式验收在隔离环境完成，没有向真实历史增加测试问答。

前次增量（2026-11-24）：用户选择将纯数字输入改为内容查找。修复前，内置资料中9份正文含 `2`，旧问答流程仅返回1条引用，见 [复现记录](evidence/numeric-lookup-repro.json)。当时实现纯数字按正文连续子串查找全部匹配文档，每份展示首处匹配附近原文；`2` 也匹配 `12`、`2024`。不受问答 TopK 限制，不调用生成或评估模型，不新增问答记录。完整问题仍走问答流程。

本轮 **35 项后端/HTTP/MCP 回归 + 11 项评估器测试**、编译、密钥扫描与32题原 AI 开发集评测门槛通过，见 [提交前检查](evidence/numeric-lookup-preflight.txt)。原 AI 评测的非时间结果保持一致，见 [比对结果](evidence/numeric-lookup-ai-regression.json)，历史报告未覆盖。隔离 HTTP/Edge 的19项检查覆盖25份匹配全列、长前缀/跨片段数字、高亮与原文定位、文本安全、零结果、问答模式恢复、统计隔离和1440px/375px布局，见 [结果](evidence/numeric-lookup-ui.json)、[桌面](evidence/numeric-lookup-desktop.png)、[手机](evidence/numeric-lookup-mobile.png)。原指标9项回归亦通过，见 [指标回归](evidence/numeric-lookup-metrics-regression.json)；旧证据逐字节恢复。截图中的25份匹配包含合成测试资料。

现有网站已重启并用 HTTP 与无界面 Edge 验证：输入 `2` 列出全部9份匹配文档，片段和原文均高亮，当前核验入口隐藏并禁用；21份文档、41个片段、4条历史问答的所有字段与升级前备份一致，三项统计不变，Qwen/BGE 服务正常，见 [现有网站验收](evidence/numeric-lookup-live.json)。此前已保存的数字问答记录不追溯删除；私人历史正文与数据库未提交。

前次增量（2026-11-24）：知识库从 AI 扩展为不限领域，新增20张入门资料卡并保留原 AI 示例。**27 项后端/HTTP/MCP 回归 + 11 项评估器测试**、编译、密钥扫描和32题原 AI 开发集评测门槛通过，见 [`general-knowledge-preflight.txt`](evidence/general-knowledge-preflight.txt)。本轮 AI 开发集的非时间结果与原报告一致，新输出单独保存在 [报告](evidence/general-knowledge-ai-regression-report.md) 与 [逐题数据](evidence/general-knowledge-ai-regression-results.json)，不覆盖历史证据。

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
