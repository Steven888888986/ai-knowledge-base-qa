# 功能地图

1. 导入：Markdown/HTML/TXT/PDF/公开网页 → 清洗 → 重复 source 更新 → 保留页码的 chunks。
2. 检索：问题 → BM25 和 BGE cosine → RRF 混合排序；可切换 BM25/vector 消融模式。
3. 回答：证据阈值 → Qwen 引用生成（或离线原文摘录）→ 引用编号校验；证据不足明确拒答。
4. 交互：导入、删除和预览文档；输入问题、选择检索模式、查看状态、用时和来源引用。
5. 扩展：`/api/query`、`/api/ingest`、`/api/upload`、`/api/import-url`、`/api/search`、`mcp_server.py`。
6. 实时统计：记录完成的 HTTP 问答 → 自动累计拒答率 → 用户核验正确来源与逐条引用 → 更新召回率和引用准确率；历史快照与核验持久化，修改核验不重复计数。
