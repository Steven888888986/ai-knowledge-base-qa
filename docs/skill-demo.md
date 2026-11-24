# 知识库研究 Skill 实测

日期：2026-11-24。按项目内 `kb-research` skill 的流程，通过本地检索 API 搜索，再调用问答 API 合成答案；检查返回来源与证据片段。

- 问题：`RAG 检索增强生成如何工作？`
- 检索模式：`hybrid`（BM25 + BGE cosine / RRF）
- 来源：`data/sample.md`，chunk `d1-p0-c1`，无页码（Markdown）
- 支持片段：`检索增强生成是一种先从外部知识库检索相关片段，再把片段交给语言模型生成回答的方法。它能让回答引用资料，降低模型凭空编造的风险。`
- 实际回答：`RAG 检索增强生成是一种先从外部知识库检索相关片段，再把片段交给语言模型生成回答的方法。它能让回答引用资料，降低模型凭空编造的风险。`
- API 返回：`mode=llm`、`refused=false`、引用来源与 chunk 匹配。

此记录是一次本机功能演示，不代表独立评测。离线开发集和本地模型全量评测见 [`../eval/README.md`](../eval/README.md) 与 [`../eval/local-model/report.md`](../eval/local-model/report.md)。
