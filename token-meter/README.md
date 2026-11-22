# Token Meter (Antigravity Desktop UI Plugin)

实时展示 Antigravity 桌面端各模型的 Token 消耗明细与生成速率（`token/s`）的侧边栏（Aux Pane）插件。

## 核心指标说明

- **总 Token 消耗**：`Input Tokens`（常规输入）+ `Cache Read`（上下文缓存命中读取）+ `Output Tokens`（总输出，含 `Thinking` 思考 Token 与 `Response` 正文/工具调用 Token）。
- **流式解码速率 (Decode `tok/s`)**：`outputTokens / ((finishedGeneratingAt - viewableAt) / 1000)`，剔除首包 Prefill 等待时间后的纯流式输出速率。
- **端到端速率 (E2E `tok/s`)**：`outputTokens / ((finishedGeneratingAt - createdAt) / 1000)`，从发起模型请求到生成完毕的整体吞吐速率。
- **TTFT (首包延迟)**：`viewableAt - createdAt`，反映长上下文输入 Prefill 与排队耗时。
- **缓存命中率**：`cacheReadTokens / (inputTokens + cacheReadTokens)`。

## 打开方式

1. 在 Antigravity 桌面端对话顶部栏点击 `+`（打开辅助面板），选择 **Token Meter**；
2. 或在对话中点击插件生成的 `[Token Meter](sidecar://token-meter/dashboard/)` 快捷胶囊链接。
