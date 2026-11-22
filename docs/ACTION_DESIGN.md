# 新动作美术规格

> 2026-11-19 更新：这些动作已经用 `tools/sprite_gen/` 生成了真帧（三个形态各一套，动作风格不同），下面的规格保留作为重画或替换时的参考。重新生成某个动作：删掉 `art_work/<形态>/raw/<asset>/`，然后依次运行 `gen.py frames --form <形态> --assets <asset>`、`process` 和 `install`。

自主行为新增了 7 个动作。现在它们都借用已有素材（见「当前替身」一列），再叠加程序绘制的装饰（代码字符、彩纸、哈欠弧线、光环等），所以没有新图也能正常运行。画好真帧后按文末步骤放进清单，替身会自动失效，**不用改代码**。

## 通用要求（和现有素材一致）

- 三种形态各画一套：`carbon/`、`hydergon/`、`neon/`。
- 每帧导出三个尺寸，**按高度**分别为 187 / 238 / 306 px，宽度随姿势变化；背景透明 PNG。
- 脚底对齐：角色脚底落在画布底部往上约 1.5%（anchor `y = 0.985`；`TIRED`、`STRETCH` 和现有 `HEAD_PAT` 一样用 0.96）。同一动作的所有帧脚底必须在同一条线上，否则播放时会上下抖。
- 横向居中（anchor `x = 0.5`），默认面朝前。需要左右区分的动作再加 `_left` / `_right` 变体（参考 `walk_side` / `walk_side_right`）。
- 帧时长：非循环动作 = 动作总时长 ÷ 帧数（最短 70 ms）；循环动作每帧 180 ms。
- 程序装饰仍会叠加在帧上方，所以头顶右侧约 40 px 范围内留空，别画太满的特效。

## 动作清单

| 动作 | asset id | 时长 | 建议帧数 | 当前替身 | 触发时机 |
| --- | --- | --- | --- | --- | --- |
| WORKING | `work_typing` | 循环 | 4 | `idle_think` | Antigravity 正在生成时陪着干活 |
| PERCH | `sit_edge` | 循环 | 2–3 | `idle_front` | 跳上 Antigravity 窗口顶边后坐着 |
| CELEBRATE | `celebrate` | 1800 ms | 6 | `happy` | 一轮生成结束、限额恢复 |
| TIRED | `tired_yawn` | 2600 ms | 6 | `idle_think` | 限额 ≤25% 时不时打哈欠 |
| STRETCH | `stretch` | 2200 ms | 5 | `happy` | 连续工作超过 90 分钟 |
| WAVE | `wave` | 1400 ms | 4 | `talk` | 从小睡中被唤醒、Antigravity 重新打开 |
| TRANSFORM | `transform` | 900 ms | 5 | `happy` | 切换形态（不可打断） |

### WORKING · `work_typing`（4 帧循环）
坐姿或微微前倾，面前悬浮一块半透明小屏或键盘。双手交替敲击：
1. 左手落下；2. 双手抬起，眼睛看屏幕；3. 右手落下；4. 歪头看屏幕，尾巴轻晃。

眼神专注，不要闭眼。屏幕光可以映在脸上（Neon 偏紫，Carbon 偏灰白，Hydrogen 偏冷蓝）。

### PERCH · `sit_edge`（2–3 帧循环）
坐在窗口顶边上，**画布底边就是窗口边**，所以腿要垂到画布底边以下的位置，裁掉的部分不画。两条腿交替轻晃，尾巴垂下。最后一帧可以加一次眨眼。

### CELEBRATE · `celebrate`（6 帧）
蓄力下蹲 → 起跳、双手举高 → 空中最高点（闭眼笑）→ 下落 → 落地小屈膝 → 比个 V 或握拳。起跳帧的脚可以离开基线，但第 1 帧和第 6 帧的脚底必须在基线上。

### TIRED · `tired_yawn`（6 帧）
肩膀下垂 → 张嘴打哈欠、一只手捂嘴 → 哈欠最大（眼角挂泪）→ 揉眼睛 → 半睁眼 → 回到略微无精打采的站姿。耳朵（如果有）逐渐耷拉下来。

### STRETCH · `stretch`（5 帧）
双手交叉向上 → 踮脚伸到最高（身体最长的一帧，注意不要超出画布顶部）→ 向左侧弯 → 向右侧弯 → 放下手，满足地呼一口气。

### WAVE · `wave`（4 帧）
面朝前，右手举起挥动：手在左 → 手在中间 → 手在右 → 手回中间，脸上带笑。被叫醒时可以略带睡眼。

### TRANSFORM · `transform`（5 帧）
原地转身加发光：正面 → 侧身 → 背面（全身被光包住，剪影化）→ 侧身 → 正面摆姿势。这段帧属于**新形态**：切换时先换素材再播放，所以每种形态画的都是「变成自己」的过程。中间帧可以大面积用该形态的主题色剪影，降低绘制成本。

## 各形态的气质参考

- **Carbon**：沉稳、动作幅度小，庆祝时更像点头握拳；打哈欠克制。
- **Hydrogen**：轻盈、飘，跳起来更高，落地更轻；工作时手指快。
- **Neon**：张扬、发光元素多，庆祝和变身可以加霓虹光带。

## 放入清单

以 Neon 的 `celebrate` 为例：

1. 帧放到 `neon/processed/runtime/states/celebrate/celebrate_{尺寸}_{序号}.png`，例如 `celebrate_238_03.png`；原图可以放在 `neon/processed/masters/generated/`。
2. 在 `neon/manifests/actions.json` 的 `assets` 下加一项（路径写成 `assets/processed/...`，会相对形态目录解析）：

```json
"celebrate": {
  "source_masters": ["assets/processed/masters/generated/celebrate_00.png"],
  "frames": {
    "187": ["assets/processed/runtime/states/celebrate/celebrate_187_00.png", "…共 6 张"],
    "238": ["assets/processed/runtime/states/celebrate/celebrate_238_00.png", "…"],
    "306": ["assets/processed/runtime/states/celebrate/celebrate_306_00.png", "…"]
  },
  "frame_count": 6
}
```

3. 三个尺寸的帧数必须相同。动作的时长、优先级和替身都定义在 `assets/manifests/actions_base.json`，一般不用改；画好以后可以把对应动作的 `quality` 从 `agy_fallback_until_art` 改成正式值，方便区分。
4. 跑 `py -3.13 -m pytest -q tests/test_animation_system.py`：它会检查每种形态、每个动作、每个方向都能加载到帧。

某个形态先画、其他形态还没画也没关系：没有真帧的形态会继续用替身。
