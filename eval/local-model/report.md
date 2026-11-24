# 实测评估报告

生成时间：2026-11-24T21:11:08.643658+08:00

回答模式：`configured-local-llm`；12 篇自编短文、24 个可回答问题、8 个库外问题。

| 检索模式 | Recall@1 | Recall@3 | 证据引用准确率 | 可追溯率 | 正确拒答率 | 误拒率 | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| bm25 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 2502.92 |
| vector | 95.8% | 95.8% | 100.0% | 100.0% | 100.0% | 4.2% | 3208.22 |
| hybrid | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 3879.21 |

证据引用准确率按人工标注来源与原句计算，**不等价于大模型全部主张的事实正确率**。
这是开发集，不能宣称未见真实场景上的泛化能力。`results.json` 保存逐题输出供复查。

## 混合检索逐题结果

| 题号 | 类型 | 证据命中@3 | 拒答 | 支持引用/全部引用 | 模式 |
|---|---|---|---|---|---|
| K01 | 可回答 | True | False | 1/1 | llm |
| K02 | 可回答 | True | False | 1/1 | llm |
| K03 | 可回答 | True | False | 1/1 | llm |
| K04 | 可回答 | True | False | 1/1 | llm |
| K05 | 可回答 | True | False | 1/1 | llm |
| K06 | 可回答 | True | False | 1/1 | llm |
| K07 | 可回答 | True | False | 1/1 | llm |
| K08 | 可回答 | True | False | 1/1 | llm |
| K09 | 可回答 | True | False | 1/1 | llm |
| K10 | 可回答 | True | False | 1/1 | llm |
| K11 | 可回答 | True | False | 1/1 | llm |
| K12 | 可回答 | True | False | 1/1 | llm |
| K13 | 可回答 | True | False | 1/1 | llm |
| K14 | 可回答 | True | False | 1/1 | llm |
| K15 | 可回答 | True | False | 1/1 | llm |
| K16 | 可回答 | True | False | 1/1 | llm |
| K17 | 可回答 | True | False | 1/1 | llm |
| K18 | 可回答 | True | False | 1/1 | llm |
| K19 | 可回答 | True | False | 1/1 | llm |
| K20 | 可回答 | True | False | 1/1 | llm |
| K21 | 可回答 | True | False | 1/1 | llm |
| K22 | 可回答 | True | False | 1/1 | llm |
| K23 | 可回答 | True | False | 1/1 | llm |
| K24 | 可回答 | True | False | 1/1 | llm |
| U01 | 库外 | 不适用 | True | 0/0 | refusal |
| U02 | 库外 | 不适用 | True | 0/0 | refusal |
| U03 | 库外 | 不适用 | True | 0/0 | refusal |
| U04 | 库外 | 不适用 | True | 0/0 | refusal |
| U05 | 库外 | 不适用 | True | 0/0 | refusal |
| U06 | 库外 | 不适用 | True | 0/0 | refusal |
| U07 | 库外 | 不适用 | True | 0/0 | refusal |
| U08 | 库外 | 不适用 | True | 0/0 | refusal |
