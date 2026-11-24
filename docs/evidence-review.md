# 只读 reviewer 实际审阅记录

日期：2026-11-24。通过 Codex 协作子智能体加载 `.claude/agents/reviewer.md` 的职责，对本地生成评测 hybrid 的 24 个回答和 8 个拒答逐项检查。不是交叉红队，也未声称运行 Claude 原生命令。审核只读，未改写被审答案。

## 审核版本

`eval/local-model-before-prompt-fix/results.json` 保存本次审核的原始快照，生成时间 `2026-11-24T21:11:08.643658+08:00`，SHA-256 为 `3f1a53bdc9a3e245bb3500e4f682b9b320b461efddef5a275c26bbacf6dd64d3`。目录名来自原计划做提示词修复；后续候选未稳定改善，因此没有部署新提示词，当前 `eval/local-model/` 仍为同一版结果。

24 条引用的 source、title、snippet 均与 `eval/corpus.json` 一致，chunk/document ID 与索引顺序一致，页码均为 null；全部单引用。**引用证据指标 100% 并不代表生成答案全部正确：K04 混淆了 Q/K/V 的角色，另有漏答与限定词丢失。**

| claim | evidence（来源均在 eval/，页码 null） | verdict | fix / 后续建议 |
|---|---|---|---|
| K01：RAG 先检索资料 | rag.md · d1-p0-c1：先查找相关证据 | supported | 无 |
| K02：缺少证据应拒答 | rag.md · d1-p0-c1：没有足够证据时应拒答 | supported | 回答的是拒答规则 |
| K03：分母问题回答了整个缩放运算 | attention.md · d2-p0-c1：点积除以键向量维度的平方根 | 内容受支持，未直答 | 直接指出键向量维度的平方根 |
| K04：Q/K/V 都用于计算注意力分数 | attention.md · d2-p0-c1：Query 与 Key 的点积，softmax 归一化并对 Value 加权求和 | **unsupported：角色混淆** | 分开说明 Q/K 计算分数、权重对 V 加权求和；检索正确，生成错误 |
| K05：余弦相似度公式与方向含义 | embedding.md · d3-p0-c1 | supported | 无 |
| K06：哈希不等于语义嵌入 | embedding.md · d3-p0-c1 | supported | 无 |
| K07：BM25 的三项因素 | bm25.md · d4-p0-c1 | supported | 无 |
| K08：RRF 不要求同尺度原始分数 | bm25.md · d4-p0-c1 | supported | 无 |
| K09：只回答验证集用途 | splits.md · d5-p0-c1：验证集选超参数，测试集最终评估 | 已答主张 supported，漏项 | 补充测试集用途 |
| K10：测试集选阈值导致泄漏 | splits.md · d5-p0-c1 | supported | 无 |
| K11：过拟合及缓解方法 | overfitting.md · d6-p0-c1 | supported | 无 |
| K12：早停依据验证集表现 | overfitting.md · d6-p0-c1 | supported | 无 |
| K13：学习率过大震荡或发散 | gradient.md · d7-p0-c1 | supported | 无 |
| K14：梯度累积模拟更大有效批次 | gradient.md · d7-p0-c1 | supported | 无 |
| K15：LoRA 冻结权重并训练低秩增量 | lora.md · d8-p0-c1 | supported | 无 |
| K16：秩 r 控制增量容量 | lora.md · d8-p0-c1 | supported | 无 |
| K17：量化减少占用 | quantization.md · d9-p0-c1：通常减少占用 | 核心 supported，限定丢失 | 保留“通常” |
| K18：GGUF 携带权重、分词器、元数据 | quantization.md · d9-p0-c1 | supported | 无 |
| K19：Precision 公式 | metrics.md · d10-p0-c1 | supported | 无 |
| K20：F1 为调和平均数 | metrics.md · d10-p0-c1 | supported | 无 |
| K21：CNN 局部感受野和权重共享 | cnn.md · d11-p0-c1 | supported | 无 |
| K22：池化下采样、可能丢细节 | cnn.md · d11-p0-c1：常用于下采样 | 核心 supported，限定丢失 | 保留“常用于” |
| K23：提示注入是试图改变任务的恶意指令 | prompt.md · d12-p0-c1 | supported，处置要点遗漏 | 补充资料仅作数据、不能成为系统指令 |
| K24：引用格式正确不等于支持结论 | prompt.md · d12-p0-c1 | supported | 无 |
| U01–U08：8 个库外问题均拒答 | 语料无天气、食谱、密码、食堂、天文、退票、人物年表或地理依据 | 正确拒答 | 均无引用 |

## 未采用的提示词试验

原始请求与真实响应保存在 `docs/evidence/prompt-trial*.json`。没有更改线上 prompt、评测标签、证据门槛或回答模式来掩盖失败。

- 解除一句话限制、要求分别说明：K09 改善，K04 仍混淆角色。
- 要求逐字摘录与保留限定词：部分题改善，但 K03/K23 出现只有编号或标题的回答。
- 要求先完整引用再解释：单次 K04 能返回正确原句；放回通用证据格式后仍出现错误概括，部分题丢失引用。未采用。

当前交付保留小模型可运行的基线和上述已知质量限制；使用时应对照引用原文核验。引用编号门控只验证编号有效，不能作事实蕴含验证。后续改进应使用独立问题集复测更强模型或主张核验机制，不能只挑成功样例。
