# 评审检查点

- 需求：SPEC 有范围、验收标准和非目标；AGENTS/CLAUDE 说明证据链与 API 安全。
- 原始要求：五张课程要求图片的逐项核对见 [`acceptance-audit.md`](acceptance-audit.md)，区分实现证据、待补材料和明确排除项。
- 扩展：`.claude/skills/verify`、`.claude/skills/kb-research`、MCP server、hook、reviewer 子智能体均可读、可复现；真实本机调用记录见 [`skill-demo.md`](skill-demo.md)。
- 测试：`tests/test_app.py` 覆盖导入/切分/检索/引用/更新/拒答、MCP stdio 和临时本地 HTTP E2E（健康、上传、查询、引用、列表、删除及 loopback URL 拒绝）。自动化通过不代表浏览器视觉检查已完成；手动 UI 检查结果需单独记录。
- 过程：`transcripts/requirements-interview.md` 保存访谈原文与关键 prompt；`collab-log/LOG.md` 保存真实修复过程；`collab-log/bugs/` 有复现与回归证据；五人分工在 `collab-log/team-template.md` 待成员填写。
- 模型：`docs/models.md` 记录预训练模型、锁定来源、许可、校验和、启动与真实调用验证；权重不提交到仓库。
- 选型与演化：[`mcp-design.md`](mcp-design.md) 说明 MCP 与 CLI 的分工；[`configuration-evolution.md`](configuration-evolution.md) 记录上下文规则的实际修改依据。
- 评测：`eval/` 保存 24 个可回答和 8 个库外问题的离线开发集逐题结果；真实 Qwen 评测单独保存到 `eval/local-model/`，两者不混为一谈。
- 未完成：交叉红队按题目要求跳过。
