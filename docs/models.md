# 本地预训练模型

本项目在 Windows x64 CPU 上使用 llama.cpp 提供的 OpenAI 兼容接口。模型已在本机启动验证，不需要外部 API 密钥。

| 用途 | 模型文件 | 来源与锁定版本 | 仓库许可 | SHA-256 |
|---|---|---|---|---|
| 中文生成 | Qwen2.5-1.5B-Instruct Q4_K_M | [Qwen GGUF 仓库](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/tree/91cad51170dc346986eccefdc2dd33a9da36ead9) | Apache-2.0 | `6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e` |
| 中文向量 | BGE-small-zh-v1.5 Q8_0 | [CompendiumLabs GGUF 仓库](https://huggingface.co/CompendiumLabs/bge-small-zh-v1.5-gguf/tree/5bf683e6a1bd454bbb60ba051088c50731d63fcb) | MIT | `5a88d266870fbd27c6f329df60de80e2d4cf3bbd5e6f080bd5c1b2e5abb12039` |
| CPU 推理运行时 | llama.cpp Windows CPU x64 | [ggml-org 发布包 b12675](https://github.com/ggml-org/llama.cpp/releases/tag/b12675) | MIT | `bc362be03528651701e6218672bb0cbf48b55ba7acad0eb5006449567f4cf821` |

以上仓库许可字段于 2026-11-24 从 Hugging Face 模型卡读取；再分发前应检查上游许可及模型卡的额外条款。下载 URL、提交版本和校验和由 `scripts/install_models.py` 固定。模型权重不会提交到 GitHub。

## 启动和验证

```powershell
py -3 scripts/install_models.py
powershell -ExecutionPolicy Bypass -File scripts/start-models.ps1
py -3 server.py
```

脚本默认在 `127.0.0.1:8081` 启动 Qwen、在 `127.0.0.1:8082` 启动 BGE。`/api/health` 会报告服务状态；问答返回 `mode: "llm"` 才代表回答通过有效引用检查并确实来自生成模型。否则系统展示原文摘录并带告警。模型容量小，可能拒绝输出或遗漏引用，因此应用不接受无效引用的生成文本。离线检索仍可独立运行。

知识库拒答后，用户可确认调用同一 Qwen 生成补充回答。此路径返回 `mode: "llm-general"`，单独显示“无知识库依据”，不提供引用，不改写原知识库拒答或三项指标。关闭模型或调用失败时明确报错；不会以离线摘录冒充补充生成。提示词见 [需求访谈](../transcripts/requirements-interview.md)。

## 本机实测

只读主张审核发现小模型会概括错误和漏答，即使引用编号有效也可能不被原文支持。K04 的 Q/K/V 角色混淆和多项提示词试验均原样保留在 [`evidence-review.md`](evidence-review.md)；当前基线没有应用不稳定的候选提示词。

2026-11-24，本机 CPU 服务的 Qwen `/v1/models` 和 BGE `/v1/models` 均返回 HTTP 200。固定的 RAG 定义、Transformer 注意力和 BM25 评测问题，在修改提示格式后均得到带有效 `[1]` 引用的生成回答，应用返回 `mode: "llm"` 且无 warning。完整 32 题本地生成评测结果另见 [`../eval/local-model/report.md`](../eval/local-model/report.md)（评测完成后生成）。
