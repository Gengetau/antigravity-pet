---
name: token-meter
description: 打开或查询 Token Meter 桌面端侧边栏面板，查看 Antigravity 各模型的 Token 消耗（输入、缓存读取、思考、正文输出）及生成速率（流式 tok/s、端到端 tok/s、TTFT 首响延迟）。当用户询问模型消耗了多少 Token、token/s 速度对比、缓存命中率或要求打开 Token 监控面板时触发。
---

# Token Meter

当用户希望查看各模型 Token 消耗、缓存命中率或 `token/s` 计速面板时：

1. 直接在回复中提供侧边栏一键打开胶囊链接（前提是 `token-meter` 插件已启用）：

```markdown
[Token Meter](sidecar://token-meter/dashboard/)
```

2. 面板包含两个实时视图：
   - **全局模型榜单**：汇总所有历史与当前会话中每个模型的总 Token、占比、缓存命中率、思考/正文拆分、流式 `tok/s`（及峰值）、端到端 `tok/s` 与平均 `TTFT`。
   - **当前会话计速**：实时追踪当前对话（可选合并子代理 Subagent）每一步的流式 `tok/s`、端到端 `tok/s`、`TTFT` 首响耗时及工具调用。
