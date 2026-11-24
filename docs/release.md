# 公开发布记录

仓库：https://github.com/Steven888888986/ai-knowledge-base-qa

可见性：Public。分支：`main`。创建及推送由用户授权，GitHub 设备登录由用户在已有浏览器中手动确认。

## 发布前复验

2026-11-24 再次执行 `powershell -ExecutionPolicy Bypass -File .claude/hooks/preflight.ps1`，退出码为 0：编译、14 项应用/HTTP/MCP 测试、敏感信息扫描及 32 题离线评测门槛通过。14 项测试耗时 3.342 秒。

本轮逐题结果保存于 [`../eval/release-check/results.json`](../eval/release-check/results.json)，摘要见 [`../eval/release-check/report.md`](../eval/release-check/report.md)。与先前提交的 `eval/results.json` 对比，移除生成时间和耗时字段后完全相同。因此保留原评测与答辩材料的对应关系，没有用本轮耗时覆盖先前快照。

本机 `http://127.0.0.1:8765/api/health` 返回 `ok=true`、Qwen `available=true`、BGE `mode=pretrained-bge`。实际提问“什么是检索增强生成（RAG）？”返回：

> 答案：检索增强生成是一种先从外部知识库检索相关片段，再把片段交给语言模型生成回答的方法。 [1]

该次响应 `mode=llm`、`model=local-qwen`、`refused=false`，引用来源为 `data/sample.md`，耗时 1205 ms。这里只记录这次观测，不保证所有问题的生成正确性；已知生成错误见 [`evidence-review.md`](evidence-review.md)。

## 远端验证

源码已推送到 `main`，首次发布提交为 `92925d4595e360049b36dad51c8be832a7e791dc`。GitHub 返回的 tree SHA 与本地一致：`f1ff36777bf563e3f5435804c09eceb409a1f259`；三个先前提交与本次发布准备提交均保留。

[首次 GitHub Actions](https://github.com/Steven888888986/ai-knowledge-base-qa/actions/runs/45411516210) 于 `2026-11-24T14:12:41Z` 完成，结论为 `success`。Ubuntu / Python 3.12 环境下，14 项测试通过，32 题离线评测门槛通过。该环境没有本地模型，使用已标记的词法哈希回退：Hybrid Recall@3 为 100%，证据引用准确率为 96%，可追溯率与正确拒答率均为 100%，误拒率为 0%。这不是 BGE 或 Qwen 的线上质量分数。

原始运行元数据与各步骤状态见 [`evidence/github-actions.json`](evidence/github-actions.json)，测试与评测日志节选见 [`evidence/github-actions-checks.txt`](evidence/github-actions-checks.txt)。后续文档提交的最新状态可在 [Actions 工作流](https://github.com/Steven888888986/ai-knowledge-base-qa/actions/workflows/verify.yml) 查看。

推送过程最初直连 `github.com:443` 失败；通过本机已配置的 `127.0.0.1:7897` 代理，使用仅对该次命令生效的 Git 选项后成功，没有修改系统代理配置。

## 交付边界

模型权重、运行时、数据库和凭据不进入 Git；模型安装脚本提供固定下载版本与 SHA-256 校验。课程代码、评测、日志、prompt、配置、PPTX、PDF 与备用 API 实录都随仓库交付。

交叉红队按用户要求跳过。五位成员姓名、真实个人贡献及口头答辩由组员补充，模板在 [`../collab-log/team-template.md`](../collab-log/team-template.md)。
