# 上下文与配置演化记录

初始提交为 `74ed939`（`chore: preserve initial prototype and acceptance draft`）。它保存了 `AGENTS.md`、`CLAUDE.md` 与初始 SPEC。实现提交 `b35cde6` 已保存以下实际修改，可通过 Git 差异核查；两个提交均为本次工作实际创建，没有回填或修改提交日期。

本次实现后修正了以下上下文：

| 初始或中间描述 | 当前约定 | 修改依据 |
|---|---|---|
| 初版提及 SQLite FTS5 | SQLite 负责持久化，BM25 与向量排序在 `retrieval.py` 中执行 | 当前检索实现 |
| 只有 BASE_URL 和 API_KEY 同时存在才调用模型 | 默认调用本机 Qwen，无需密钥；支持显式关闭生成 | 用户无模型/API 的需求与本机实测 |
| 只要求一般回归测试 | 特别要求区分检索候选与答案证据，保留库外拒答回归 | BUG-01、BUG-02 |
| 未强调证据分数可比性 | 不得将 BM25 和 cosine 直接比较强弱；引用存在不等于支持主张 | K23 真实生成引用错误与回归测试 |

查看演化的命令：

```powershell
git log --oneline -- AGENTS.md CLAUDE.md
git diff 74ed939 HEAD -- AGENTS.md CLAUDE.md
```

两项项目 skill 分别约束验证和证据研究；Stop hook 执行确定性检查；只读 reviewer 的职责是逐条核对主张与引用。它们为复现、检查与审阅提供固定入口，不能替代实际运行证据或成员自己的判断。
