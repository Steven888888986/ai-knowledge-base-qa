# 现场演示脚本

建议用时：3–4 分钟。演示前在项目根目录打开两个 PowerShell 窗口；模型文件已下载时不需要重复安装。

## 演示前准备

如果模型文件尚未安装，先执行一次下载与 SHA-256 校验（约 1.2 GB）：

```powershell
py -3 scripts/install_models.py
```

启动本地 Qwen 和 BGE 服务：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-models.ps1 -Mode all
```

如端口 8081 或 8082 已有旧进程，先确认它使用当前脚本参数；已运行的旧服务不会被启动脚本自动替换。启动日志在 `.runtime/llm.err` 与 `.runtime/embedding.err`。BGE 服务应使用 CLS pooling。

在第二个 PowerShell 窗口启动问答系统：

```powershell
py -3 server.py
```

确认状态并打开 `http://127.0.0.1:8765`：

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/health | ConvertTo-Json -Depth 6
```

页面启动后会自动索引 `data/sample.md`。状态中应显示模型可用，向量模式为 `pretrained-bge`。如果显示 `local-lexical`，演示仍可运行，但应说明当前使用词项回退。

## 演示步骤

1. 在首页指出当前回答模式与知识库统计，说明这是本地服务。
2. 输入“什么是 RAG？”。等待回答，展示答案模式、来源标题和引用片段。
3. 展开引用，核对来源 `data/sample.md` 与原文片段；说明引用支持追溯，仍需逐条判断生成主张。
4. 输入“明天的天气如何？”。知识库没有天气资料，系统应显示明确拒答，不应生成天气预报。
5. 可选：通过页面导入一份 Markdown 或 TXT，然后对该资料中的概念提问。

## 可选 API 演示

```powershell
$body = @{ question = '什么是 RAG？' } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8765/api/query -Method Post -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 8
```

## 结束检查

- 能打开首页，`/api/health` 返回 `ok: true`。
- RAG 问题返回非空答案和可展开的来源片段。
- 库外问题得到明确拒答。
- 模式标识与健康接口报告一致；不要把离线摘录称为模型生成。
