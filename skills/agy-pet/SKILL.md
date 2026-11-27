---
name: agy-pet
description: 管理与控制 AGY 桌宠 / Manage & control AGY Desktop Pet / AGY デスクトップペットの管理（Carbon / Hydrogen / Neon / Argon / Claude 五形态切换、中/英/日三语切换、启动唤醒、查看精确上下文与 5h/周限额、打开侧边栏控制台）。Trigger when the user mentions desktop pet, 桌宠, デスクトップペット, switch form/切换形态/形態切替, change pet language/切换语言/言語切替, or opening the AGY Pet sidebar.
---

# AGY 桌宠控制与遥测插件

此插件把桌面宠物接入 Antigravity 生命周期，提供会话焦点追踪与侧边栏控制台。

## 桌宠根目录定位（`<PET_ROOT>`）

- 标准整仓安装时，`<PET_ROOT>` 即插件自身所在目录（默认 `~/.gemini/config/plugins/agy-pet`）。
- 若插件目录下存在 `.pet_root` 开发链接文件，则以 `.pet_root` 记录的路径为准；若当前工作区包含 `main.py` 也可直接指向当前工作区。

## 快捷入口

- 打开侧边栏控制台：[AGY 桌宠](sidecar://agy-pet/pet-bridge/)
- 打开插件设置页（启用 / 停用）：[AGY 桌宠](customization://agy-pet)

## 五种形态 ID

| 形态名 | `config.json` 中 `agy.form` 值 | 对应模型关键词 |
| --- | --- | --- |
| Carbon | `carbon` | Carbon / Orchestrator (Carbon) |
| Hydrogen | `hydergon` | Hydrogen |
| Neon | `neon` | Neon / Orchestrator (Neon) |
| Argon | `argon` | Argon |
| Claude | `claude` | Claude |

## 会话追踪与上下文数据

1. **Hook 实时锁定**：插件根目录 `hooks.json` 在 `SessionStart` 与 `PreInvocation` 时运行 `hooks/track_session.mjs`，把最新 `conversationId` 写入 `~/.gemini/antigravity/sidecar_data/agy-pet/active_session.json`。
2. **桥接实时快照**：`sidecars/pet-bridge` 每 2 秒融合 Hook、`annotations/*.pbtxt`（用户点击浏览时间）、`projects/*.json`（工作区切换）与语言服务指标，写出 `~/.gemini/antigravity/sidecar_data/agy-pet/pet-bridge/data/pet_live.json`。
3. **上下文计算口径**：已用上下文为最近一步 `inputTokens + cacheReadTokens + responseOutputTokens`（剔除单步内部 `thinkingOutputTokens`），窗口上限按当前活动模型单独判断。

## 配置热同步

- 桌宠主配置文件位于 `<PET_ROOT>/config.json` 的 `agy` 字段（支持 `language`（`auto` / `zh` / `en` / `ja`）、`form`、`follow_model`、`hud_enabled`、`hud_mode`、`hud_appearance`、`hud_locked`、`pinned_conversation`、`autonomy`、`reactions`、`ai_comments`）。
- 外部或侧边栏控制台更新 `<PET_ROOT>/config.json` 后，运行中的桌宠会在约 1.5 秒内自动热生效（包括语言热切）并保持坐标位置。
- 启动或唤醒桌宠命令（在 `<PET_ROOT>` 下）：`pyw -3.13 main.py`（或双击 `启动AGY桌宠.cmd`）。
