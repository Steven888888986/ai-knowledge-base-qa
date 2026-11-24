# 原始课程要求验收审计

审计日期：2026-11-24。审计直接阅读项目父目录的五张原始 PNG，不以项目自行编写的 SPEC 代替课程要求。以下“已验证”仅指列出的证据，不推断未执行的操作。

## 原始依据与范围

| 原图文件名 | 内容 |
|---|---|
| `d907e849dafe575f6af24159e4a53fd4.png` | 选题方向；B 为“知识库问答系统（RAG）” |
| `7d6ccfab73145c2be4112d2c6ec52d29.png` | 仓库最低要求与推荐结构 |
| `24c2ba4940ec40be272813f39f2e59b9.png` | 协作日志、Bug 档案与原文留存要求 |
| `d74ce6b80977a353fea92fe82cec2405.png` | 一周里程碑与最终提交内容 |
| `5848010b37d102426db5b6e09528a907.png` | 评分维度与个人贡献要求 |

用户选择 B 题、AI 领域，明确排除交叉红队。仓库要求图将 Skills/MCP/Hooks/Subagent/测试/Loop 一组标注为“可选”；本项目仍按用户“除交叉红队外”的范围对照这些项。A/C/D 和自拟题目的专属功能不属于本项目范围。原图只要求至少一种属性/E2E/差分测试，没有单独写必须做浏览器 UI E2E。

## B 题产品要求

| 原始要求 | 当前状态与证据 | 尚需处理或边界 |
|---|---|---|
| 导入 PDF/网页 | `docs/evidence/import-smoke.json` 记录真实双页 PDF 上传后第 2 页引用，以及公开 PyTorch 网页导入和来源/片段一致性；5 个断言组全通过 | PDF 依赖 `pypdf`，扫描图片型 PDF 没有 OCR；初次缺依赖与安装后成功均有原始记录 |
| 切分、向量化 | `app.py` 保存分片与页码；`retrieval.py` 使用 BGE 向量；100 组随机文本切分边界测试通过 | BGE 不可用时是词项哈希回退，不能称为预训练语义向量 |
| 混合检索 | BM25、vector、hybrid 可切换；RRF 融合；`eval/` 保存三模式逐题结果 | 开发集规模小；不能据此声明真实业务泛化 |
| 带出处引用的回答 | 引用包含 title/source/chunk/page/snippet；HTTP、中文查询和页码测试通过；本地 Qwen 实测见 `eval/local-model/` | 引用编号有效不等于每个生成主张都已核实 |
| MCP server 对外检索 | `mcp_server.py` 提供 `search_knowledge_base`；stdio 初始化、工具列表和实际搜索测试通过 | 本次自动测试证明协议入口，不声称所有第三方客户端均已接入 |
| 自建评测集、召回率、引用准确率、拒答率 | 12 篇短文、24 个可回答问题、8 个库外问题；标注来源与证据；离线和本地生成分别报告 | `eval/README.md` 定义指标；没有独立盲测集 |
| 需求分析、功能拆解、目标、完成标准、测试验证 | `docs/SPEC.md`、`docs/feature-map.md`、`tests/test_app.py`、`docs/test-report.md` | 两分钟启动目标不包含首次约 1.2 GB 下载；首次安装耗时没有计入验收 |

## 仓库与工程要求

| 原始要求 | 当前状态与证据 | 尚需处理或边界 |
|---|---|---|
| AI 采访产生 SPEC，含可测试验收标准 | `transcripts/requirements-interview.md` 保留实际问答；`docs/SPEC.md` 有 A1–A9 | 已有证据 |
| AGENTS 或 CLAUDE，并在 Git 历史体现演化 | 初始提交 `74ed939` 与实现提交 `b35cde6` 保存上下文演化；`docs/configuration-evolution.md` 提供复核命令 | 真实提交日期，不伪造早期开发时间线 |
| ≥2 个自定义 skill，其中一个 verify | `.claude/skills/verify`、`kb-research`；`.agents/skills/` 提供对应版本 | `docs/skill-demo.md` 保存 kb-research 流程的一次真实调用；验证命令实测见测试报告 |
| ≥1 个 MCP server，并说明为何不用 CLI | MCP 实现及测试存在；`docs/mcp-design.md` 说明结构化客户端调用的用途及 CLI 分工 | 已有实现与说明 |
| ≥1 个确定性 hook | `.claude/settings.json` 的 Stop hook 调用 `.claude/hooks/preflight.ps1`；脚本真实运行通过 | 记录为脚本执行通过；不声称在未使用的宿主上已触发 Stop 事件 |
| ≥1 个自定义子智能体，如只读 reviewer | `.claude/agents/reviewer.md` 定义只读职责；`docs/evidence-review.md` 记录按该职责对32题的实际独立审阅 | 使用Codex协作工具，不声称调用Claude原生命令；审核发现真实生成错误并保留 |
| 自动测试 + ≥1 种属性/E2E/差分测试 | 14 项测试通过；随机文本切分性质检查与临时 HTTP E2E 均存在 | 没有要求三类全部实现；不宣称做过差分测试 |
| AI 组件离线评测集；CI 中运行 | `.github/workflows/verify.yml` 在 push/PR 运行测试与离线评测；`eval/no-model/` 在关闭两个模型的环境通过门槛；首次远端 [Actions 45411516210](https://github.com/Steven888888986/ai-knowledge-base-qa/actions/runs/45411516210) 实际通过 | 元数据与日志节选在 `docs/evidence/github-actions*`；CI 为无模型环境 |
| 至少一次 /goal、/loop 或 claude -p 完成任务 | `docs/goal-workflow.md` 与 `docs/evidence/goal-status.json` 保存主会话实际 Codex goal 目标和当时的 active 状态；修复后重复验证及公开发布结果见 `docs/release.md` | 工具形式与原图 slash 命令不同；没有伪造 `/goal` 或 `claude -p` 运行记录，也不自行声称课程等价；结束状态以会话实际工具返回为准 |

## 过程、汇报与最终交付

| 原始要求 | 当前状态与证据 | 尚需处理或边界 |
|---|---|---|
| 每人 ≥1 条、组内 ≥8 条记录 | `collab-log/LOG.md` 有 19 项可核验 AI 开发与发布记录；五人模板存在 | **五位成员各自至少一条真实记录仍需本人补充**；AI 记录不能代替成员贡献 |
| Bug 档案 ≥2，至少一个为 AI 引入 | `collab-log/bugs/` 有两份 AI 辅助实现产生的逻辑缺陷，含复现、原因、修复和回归 | 档案补明事后分析与原始记录的区别；无保存的首轮 prompt/输出不补造 |
| 现象→复现→假设→证据→根因→修复→回归→沉淀 | 两份 Bug 档案有可运行复现、已记录错误现象、复盘假设、修复约束与回归用例；规则沉淀于 AGENTS | 当前回归可重复执行；未保留的修复前完整终端输出仍是证据边界 |
| 保留 prompt 与关键输出原文；导出关键会话到 transcripts | `requirements-interview.md` 保存原话与当前实际 system prompt；`conversation-export.md` 保存工具能读取的已结束回合公开消息 | 导出使用 Codex `read_thread`，并非原图 `/export` 命令；覆盖范围在文件内说明，不包含内部推理 |
| 失败也要记、日志与 Git/会话一致 | Bug-01、Bug-02 和 K23 引用错误均记录失败及修复；日志明确记录者为 AI | 不补造“被否定方案”、token 消耗、成员姓名或个人反思；后续组员须据实增加 |
| 选题、分工、技术选型 | 选题/领域确认有原话；`docs/models.md`、MCP 设计与架构文档说明选型 | 五人姓名、实际分工待成员填写 |
| 核心功能 TDD、CI 初期跑通空测试 | 当前有失败回归驱动修复、测试与 CI 工作流 | 没有证据证明全项目采用先测后码，或第一天已跑通空测试；不补写虚构开发时间线 |
| 整理日志、配置演化回顾、汇报幻灯片 | LOG、`configuration-evolution.md`、12 页 PPTX/PDF、答辩稿与演示脚本均存在 | 幻灯片成员页与讲稿中的个人部分需本人确认；演示与指标须与最终报告一致 |
| 录制备用演示视频 | `presentation/AI领域知识库问答系统-API操作实录.mp4` 为60秒H.264视频，真实请求日志见 `docs/evidence/demo-api.json`；完整解码与7处抽帧核验通过 | 画面由真实API请求日志渲染，明确不是浏览器屏幕录像；未伪造回答或计时 |
| 最终提交：仓库 + 日志 + 幻灯片 | [公开仓库](https://github.com/Steven888888986/ai-knowledge-base-qa) 已推送源码、日志、PPTX/PDF 与备用API视频；首次发布提交 `92925d4` 的 CI 通过 | `docs/release.md` 保存远端验证、提交 SHA、tree 校验与真实运行链接 |
| 每位成员讲清本人负责部分 | 五人模板与答辩材料保留填写位置 | 需成员真实参与、填写、练习；无法由 AI 代替口头答辩 |
| 交叉红队 | 按用户要求排除；原图也列为选做/加分 | 不实施、不记为已完成 |

## 评分维度对应证据

| 原图维度 | 分值 | 核查入口 |
|---|---:|---|
| 需求与上下文工程 | 20 | SPEC、访谈原文、AGENTS/CLAUDE、配置演化 |
| 扩展的运用 | 5 | 两个 skill、MCP 选型、hook、reviewer 配置及实际验证边界 |
| 测试与验证体系 | 15 | 自动化测试、HTTP E2E、随机切分、离线与本地生成逐题结果 |
| 调试与问题解决 | 10 | 两份 Bug 档案和 K23 回归 |
| 协作日志与反思 | 10 | AI 过程日志与会话原文；成员个人记录待补 |
| 产品结果 | 20 | README、导入/检索/回答/MCP 实现与测试 |
| 汇报与答辩 | 20 | 幻灯片、讲稿、演示脚本；成员真实讲解待完成 |
| 加分 | +5 | 自建 MCP、可复用 skill；交叉红队排除 |

本表为交付审计，不预测教师评分。公开发布及 CI 的真实证据已补入；需要成员自行完成的部分仍保留明确待办。
