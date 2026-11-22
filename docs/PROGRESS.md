# 进度记录

## 2026-11-19 · v0.1.0 首版

**完成**
- 以 QCYTSN/ds-local-pet（MIT）的 Python + PySide6 代码为基础搭建，换掉了品牌标识：数据目录 `AgyDesktopPet`、单实例名 `agy-pet-*`、日志 `agy-pet.log`；删除了指向原仓库的自动更新器；台词里的「大肥鱼」改成了「小A」。
- 三种形态：`carbon/`、`hydergon/`、`neon/` 原地使用。`AssetRegistry` 新增了 `base_manifest` 参数：角色清单里缺的 `actions`/`fallbacks` 从 `assets/manifests/actions_base.json` 合并；帧路径里的 `assets/` 前缀改为相对角色目录解析。
- 形态切换的入口有控制面板、托盘，以及「跟随模型」（模型标签 Neon/Carbon/Hydrogen → 对应形态）。拖拽或下落途中会延迟切换，切换后脚底位置不变。
- `agy/telemetry.py`：语言服务自动发现 → `hud_live.json`（15 秒内）→ transcript 离线兜底；统计按模型汇总，以及每一步的速率和 TTFT。
- `agy/hud_bar.py`：Qt 版 agy-hud-bar，支持跟随桌宠或独立悬浮。`agy/token_meter.py`：Qt 版 token-meter 面板。
- `agy/reactions.py`：开始和完成生成、速率很快、限额不足、上下文过高时，桌宠会做出反应（带冷却）。

**验证**
- `pytest`：66 项全部通过，其中新增 `tests/test_agy.py` 的 12 项，覆盖解析、数据源回退、反应逻辑和形态切换；三种形态的全部动作和方向都能加载帧。
- 真机：语言服务发现耗时约 0.16 秒；统计 14 个会话的完整报告首次约 2.3 秒，命中缓存后约 0.05 秒；桌宠和 HUD 条在桌面上正常显示实时数据。

## 2026-11-19 · 第二轮改进

- **HUD 位置**：跟随模式下，没有气泡时贴着精灵头顶（按地面线减去精灵高度计算）；有气泡时移到窗口上方，不再遮挡台词和头部。
- **增量轮询**：改用 `GetCascadeTrajectorySteps` 的 `stepOffset` 参数，只拉新增的步数，并多回退 2 步，把可能还在生成中的那一步重新取一遍；会话变短时退回全量拉取。实测 1983 步的会话：全量 0.65 秒 / 31 MB，增量 0.027 秒，结果和全量一致。
- **自适应频率**：生成中 1.5 秒、空闲 5 秒、Antigravity 未运行时 15 秒轮询一次。
- **测试隔离**：`tests/conftest.py` 默认关闭遥测，测试不再连接本机语言服务。
- **修复**：手动切换形态后再打开「跟随模型」，现在能正确切回来；语言服务出任何异常都会退回读本地文件；psutil 要求 ≥ 6。
- **真机验证**（临时数据目录、真实遥测、真实屏幕）：跟随模型从 Carbon 自动切到 Neon；悬浮模式下拖动桌宠时 HUD 不动；跟随模式下 HUD 贴着头顶。
- 素材尺寸检查：三种形态的运行帧高度统一为 187/238/306（正好对应小、中、大三档），宽度随动作变化，不需要再统一。
- 测试：68 项全部通过。

**已知限制和后续可做**
- 离线日志里只有部分行带 `model` 字段，所以离线榜单的模型归属是推断出来的。
- 部分模型没有标签（显示为 `Model M322`），因为当前 `GetUserStatus` 的模型列表里没有这些模型的标签。
- 还没有打包成 exe（原作的 PyInstaller 和 Inno Setup 工具没有复制过来）。

## 2026-11-19 · 第三轮：自主行为

- **新动作**：`WORKING`、`PERCH`、`CELEBRATE`、`TIRED`、`STRETCH`、`WAVE`、`TRANSFORM`。定义在 `actions_base.json`，替身（fallback）链可以防循环，渲染器为每个动作加了程序装饰。美术规格见 `docs/ACTION_DESIGN.md`。
- **`agy/autonomy.py`**：纯逻辑的自主层，规则包括陪着干活、跳上窗口、坐窗沿、小睡和唤醒、限额疲惫和恢复、伸懒腰、重连时打招呼；用户正在互动时一律让开。`plan_hop` 计算弹道，窗口最大化、太窄或超过速度上限时放弃跳跃。
- **`agy/windows.py`**：只读取 Antigravity 主窗口的位置和大小，不读内容。只有 Antigravity 是前台窗口时才会跳，避免窗口被别的窗口挡住时桌宠看起来「坐在空气上」。
- **物理**：计划好的跳跃单独设速度上限 3200，落到平台后立刻站稳，不会滑出窗口边缘。坐在窗沿上时 HUD 显示在头顶上方。
- **设置**：控制面板新增「自主行为」开关；配置项 `agy.autonomy` 和 `agy.hop_to_window`。
- **验证**：`pytest` 80 项全部通过（另有 3 个子测试）。真机上用一个替身窗口验证了跳上窗口、站稳、跟随窗口移动（当时真实的 Antigravity 窗口是最小化的）；离屏截图确认新动作的装饰都能渲染。
- **未验证**：在真实 Antigravity 窗口上长时间运行的效果；小睡、伸懒腰等长时间规则只有单元测试覆盖。

## 2026-11-19 · 第四轮：Agent 控制接口

- **`agy/control.py`**：`QTcpServer` 只绑定 127.0.0.1，端口随机，一行一个 JSON，在 GUI 主线程处理，没有跨线程调度。每次启动生成随机 token，用 `hmac.compare_digest` 比较，不写日志。`control.json`（端口、token、pid）原子写入 `%LOCALAPPDATA%\AgyDesktopPet\`，退出时删除（只删自己 pid 写的）。单条消息上限 16 KB，空闲连接 15 秒断开。
- **命令**：`ping`、`status`、`say`、`action`（白名单，只有一次性动作）、`task`（start 思考 / progress 内心独白 / done 庆祝 / failed 眩晕）、`set_form`、`set_autonomy`、`set_hud`、`set_follow_model`、`open_token_meter`、`list_actions`。用户正在拖拽、桌宠在空中时返回 busy；文字最多 60 字，0.8 秒内最多一条。
- **客户端**：`agy/pet_client.py`（只用标准库）、`agy/petctl.py` 命令行（退出码 0/1/2）、`agy/mcp_server.py`（零依赖 MCP stdio，5 个工具，不回复通知，桌宠没运行时返回工具错误）。`integrations/` 里有 MCP 配置示例和 SKILL.md。**没有改动用户的任何 MCP 或 skill 配置。**
- **配置**：`agy.control_api`（默认开启）。测试默认关闭这个接口，控制文件指向临时目录。
- **验证**：`pytest` 93 项全部通过（新增 `tests/test_control.py` 13 项，含真实 TCP 往返、伪造 token、控制文件过期、MCP 协议、子进程逐行应答）。真机：用临时数据目录启动一只桌宠，`petctl status` 返回了真实遥测，`task start` 播放了思考动作和气泡，`action DRAGGING` 被拒绝（退出码 1），通过 stdin 管道调用 MCP 的 `pet_task done` 播放了庆祝动作；临时桌宠退出后控制文件已被删除。
- **已注册**：2026-11-19 按用户要求，用 `claude mcp add --scope user agy-pet -- py -3.13 D:/agy-pet/agy/mcp_server.py` 注册到 Claude Code 的用户级配置；`claude mcp get agy-pet` 显示已连接。移除命令：`claude mcp remove agy-pet -s user`。

## 2026-11-19 · 第五轮：三形态差异化（动作 + 台词 + 图标）

- **方向**：按用户要求，三个形态保留原来的猫娘外形，差异化只放在动作风格和台词上。Carbon 冷静、克制、傲娇；Hydrogen 轻飘、元气、带泡泡；Neon 是霓虹偶像，比 V、眨眼、带光效。
- **生图工具** `tools/sprite_gen/`：
  - `spec.py`：每个形态的动作风格、几个招牌动作的单独描述、34 个 asset 的分帧姿势。
  - `gen.py`：子命令 probe / frames / process / install / icon / make-ico。
  - 模型 `gpt-image-2.5-flare`，透明背景。
  - 参考图用各形态原来的 `idle_front` 立绘。多帧动画的后续帧同时参考第 0 帧，保证帧间一致。
  - 每个动画按所有帧的合并外框裁剪后，统一缩放到 187 / 238 / 306 三档。向右的走路动画由向左的镜像得到。
  - `install` 会先备份到 `art_backup/<形态>-<时间>/`，并保留清单的 `format_version` 等字段。
  - 密钥从环境变量或 `gpt-key.key` 读取，不打印也不写日志。`*.key`、`art_work/`、`art_backup/` 都已加入 .gitignore。
- **产出**：每个形态重新生成 91 帧（`idle_front` 是参考图本身，没有重画），三个形态共 273 帧。新动作（WORKING、PERCH、CELEBRATE、TIRED、STRETCH、WAVE、TRANSFORM）现在都有真帧，不再用替身。
- **限速**：账号每分钟最多 20 张输入图。第一轮因 429 失败了 57 帧，之后加了退避重试，并把缺第 0 帧的动画整组重出。
- **人工检查后重出的帧**：三个形态 `work_typing` 第 4 帧都丢了屏幕；Neon `stretch` 第 2 帧带了不透明背景。
- **台词**：`assets/dialogue/forms/<形态>.json`，每个形态 197 条。其中 152 条覆盖全部 38 个对话场景；45 条是对 Antigravity 的反应和自主行为台词，覆盖 15 种情况。
  - 个性设为「标准」时用形态台词，其他个性沿用共用台词。切换形态时台词同步切换。
  - 占位符逐条检查过，例如 finished 的每一条都含 `{total}`。
- **图标**：用三个原版猫娘作参考生成圆形徽章，转成 16 到 256 的多尺寸 `icon.ico`。旧图标备份在 `art_work/icon-backup-*.ico`。
- **验证**：
  - `pytest` 95 项全部通过，新增 `tests/test_form_voice.py`。
  - 用真实渲染器离屏截图，生成 `docs/forms_preview.png`，三个形态的各个动作尺寸和脚底对齐都正常。
- **已知不足**：
  - 入睡、醒来动画里躺姿和站姿的比例是模型自己画的，过渡时会有轻微的大小变化。
  - 生成帧之间仍有细小差异（饰品、发丝），快速循环的动画（眨眼、走路）可能有一点闪烁。
- **实机检查（用户重启后）**：通过控制接口让正在运行的桌宠依次切换三个形态，播放 IDLE、HAPPY、CELEBRATE 等动作并说话，同时截取桌宠所在区域。精灵、动作、HUD 和气泡显示都正常。
- **实机检查后修复**：
  - 气泡名牌原来三个形态都写着「小A」，现在按形态显示 Carbon / 小氢 / Neon，名牌颜色也分开了；控制面板标题同步修改。
  - 切换形态时的播报改用各形态自己的 `announce` 台词。
- **坑**：Claude 桌面应用对 `%LOCALAPPDATA%` 做了文件虚拟化。离屏预览脚本留下的过期 `control.json` 只在应用的虚拟视图里，会挡住桌宠真正写的那份，导致应用内的 petctl 和 MCP 连不上。处理方法是删掉过期文件；预览脚本已改为把控制文件写到临时目录。

## 2026-11-19 · 第六轮：Claude 形态

- **形象**：按用户提供的设定图（珊瑚橙长卷发、白色蕾丝哥特洛丽塔裙）出了两版 Q 版定妆图，用户选了不加耳朵的 #0。生图时同时参考设定图和 Carbon 的立绘，让画风、比例和另外三人一致。
- **动作**：92 帧，含正面立绘。动作风格是端庄认真，常拿小本子、托腮思考。她没有尾巴，所以「碰尾巴」改成轻拉裙摆。一次生成，0 失败；人工检查没发现问题，也没有不透明背景。
- **台词**：`assets/dialogue/forms/claude.json`，结构和条数与另外三个形态一致，名牌是橙色的「Claude」。
- **代码**：
  - `characters.py` 新增第四个形态。模型标签含 Claude 时，「跟随模型」会切到这个形态。
  - **临时登场**：控制接口的 `say` / `task` 接受 `agent` 参数，`agent=claude` 时 `PetWindow.agent_activity()` 会临时切到 Claude 形态。任务进行中最长保持 30 分钟；`done` / `failed` 后 8 秒，或单独说一句话后 20 秒，切回原来的形态。`set_form` 新增 `persist=False`，临时切换不写配置；用户手动选形态会取消自动切回。
  - MCP 服务默认带 `agent=claude`，可以用环境变量 `AGY_PET_AGENT` 改掉或清空。`petctl` 新增 `--agent` 参数。
  - 配置项 `agy.agent_guest_form`，默认开启。
- **验证**：`pytest` 96 项全部通过，新增 GuestFormTests，测试里的形态列表都扩到了 4 个。`docs/forms_preview.png` 用真实渲染器重新出图，四个形态尺寸和对齐都正常。
- **未验证**：还没在用户桌面上实际检查。正在运行的桌宠是旧代码，需要重启才能用上 Claude 形态。

## 2026-11-19 · 第七轮：面板尺寸与 HUD 对话框

- **控制面板**：形态按钮改成两列网格，三个开关也改成网格排列，不再被截断。
- **HUD 对话框外观**（`agy/hud_bar.py`，`hud_appearance = "dialog"`，新配置默认用它）：浅色圆角卡片。第一行显示会话标题，生成中时加「生成中 ·」前缀；第二行显示当前模型（`model_for_form`），锁定会话时标「（已锁定）」；下面 2×2 排列速率、限额、缓存、上下文，限额和上下文按阈值变色。卡片带一个小尖角，HUD 在桌宠上方时尖角朝下，在下方时朝上，并跟着桌宠中心移动。浮动模式没有尖角。已有配置里存的 `capsule` 不会自动改，需要在右键菜单的外观里切换。
- **HUD 和跟随模型读哪个会话**：两者用同一份快照。锁定了会话就读锁定的那个；否则在 Antigravity 语言服务器返回的会话里，先取正在生成的，再按最后修改时间取最新的，子代理会话不算。模型取值：生成中用最后一步实际用的模型，空闲时用选择器里选中的模型。
- **验证**：`pytest` 98 项全部通过，新增 `tests/test_hud_dialog.py`。离屏渲染 `art_work/hud.png` 检查了尖角朝上、朝下两种情况和胶囊外观，文字不再被截断。离屏环境没有彩色 emoji 字体，所以图里的图标显示成方框；真机上正常。
- **未验证**：还没在用户桌面上实际检查。

## 2026-11-19 · 第八轮：动作更动态（程序化，不用生图）

- **原因**：开心、说话、生气、思考、扫地、睡觉、眩晕、被拖拽、下落这些动作只有一帧立绘，以前叠加的程序化动作幅度很小（例如走路起伏不到 1 像素），看起来很僵。
- **`animation/effects.py` 重写**，动作名和接口不变：
  - 新增 `_hop()`：一次完整的跳跃，包括下蹲预备、空中拉伸、落地挤压。开心是两次弹跳（约 15 像素），庆祝是三次大跳（约 22 像素），生气是原地跺脚加抖动，碰尾巴是先吓一跳再晃。
  - 待机：呼吸幅度加大，并加上慢速的左右重心转移。走路：迈步时有起伏，落脚时挤压，胯部左右摆。
  - 被拖拽时像钟摆一样摆动并略微拉长；下落时手脚乱晃；落地挤压更明显；眩晕时绕圈晃；说话、挥手、扫地、思考、伸懒腰的摆幅都加大了。
- **`pet/renderer.py`**：站在地上的动作以脚为支点，所以不再允许往下的位移，倾斜时会自动抬高，避免鞋底穿出窗口底部。旧版在走路、开心、吃东西、扫地、落地时都会贴到底边。
- **「减少动态」开关照旧**：打开后关闭全部程序化动作。
- **验证**：
  - `pytest` 101 项全部通过，新增 `tests/test_effects.py`，覆盖幅度上限、跳跃离地加落地挤压、单帧动作必须有明显动作三类检查。
  - `art_work/motion_check.py` 对 4 个形态的全部动作逐帧离屏渲染，没有任何动作碰到窗口边缘。
  - `art_work/motion_claude.gif` 是预览动图。
- **还能做的**：给待机、走路补帧，或者多做几种待机小动作。这些要用生图 API，开工前先确认预算。

## 2026-11-19 · 第九轮：生图补帧

- **起因**：用户实机看过程序化动作后，决定改用生图补帧。
- **补了哪些动作**（每个形态都补）：
  - 开心、说话、生气、思考、扫地、眩晕：1 帧 → 4 帧
  - 睡觉、被拖拽：1 帧 → 3 帧
  - 下落：1 帧 → 2 帧
  - 共 4 个形态 × 23 张新帧 = 92 张，另外重生成了 5 张。
- **提示词写法**：新帧都写成「和图 2（第 1 帧）的角色、服装、比例、构图一致，只改动某个部位」。只改手臂、表情、头发、扫帚位置这类局部，整体的上下移动交给程序化动作，两者不会叠成两次跳。
  - `spec.poses()` 改了规则：形态如果只覆盖前几帧（例如自己独有的开心第 1 帧），后面的帧沿用通用描述。
- **代码**：动作清单可以写 `frame_ms`。写了它的一次性动作会按这个节奏循环播放所有帧，而不是平分到整个时长后停在最后一帧（`ActionSpec.frame_ms`、`AnimationClip.cycle`）。各动作设置：
  - 开心 260 ms、说话 220 ms、生气 180 ms、思考 420 ms、扫地 230 ms
  - 睡觉 750 ms、眩晕 170 ms、被拖拽 220 ms、下落 150 ms
- **人工检查**：发现并重新生成了 5 张有问题的帧：
  - Claude 开心有一圈光晕
  - Hydergon 睡觉有 2 帧睁着眼在笑
  - Neon 扫地有 1 帧扫帚不见了，变成比耶
  - Hydergon 开心有一圈发光描边
  - 修正后的提示词已写回 `spec.py`。
- **安装**：4 个形态都已安装，旧素材备份在 `art_backup/<form>-20261119-11xxxx`。
- **验证**：
  - `pytest` 103 项全部通过，新增 `FrameCycleTests`。
  - 离屏逐帧检查 4 个形态的全部动作，没有任何动作碰到窗口边缘。
  - 预览动图：`art_work/motion_claude.gif`、`art_work/motion_hydergon.gif`。
- **还没做**：待机正面仍是 1 帧，只靠眨眼、张望和呼吸。待机最常出现，帧之间稍有不一致就会抖，所以这次没补。

## 2026-11-19 · 第十轮：去掉程序化动作，全部用图像

- 按用户要求删掉了程序化动作。
- **删除的文件**：`animation/effects.py`（位移、缩放、旋转、挤压拉伸、跳跃）和对应的 `tests/test_effects.py`。
- **`pet/renderer.py` 的变化**：
  - 每一帧按原样画在锚点上，只保留左右镜像。
  - 去掉了画出来的装饰：思考小圆点、闪光、说话声波、怒气符号、晕眩星星、彩带、Zzz、代码符号等。这些在生成的帧里本身就有。
  - 脚下的阴影保留，因为它是静态的，不算动画。被拖起来或下落时不画阴影。
- **「减少动态」开关现在管什么**：只管气泡的淡入淡出和自主行为的频率。
- **保留的部分**：动作清单里的 `procedural_motion` 字段和 clip 的 `effect` 字段还在，只作元数据，渲染器不再读取。
- **验证**：
  - `pytest` 100 项全部通过（少的 3 项是删掉的程序化动作测试）。
  - 离屏逐帧检查 4 个形态：没有任何一行像素被裁掉。站立动作鞋底最低的不透明像素距窗口底边 1 像素，和最早的版本一样。

## 2026-11-19 · 第十一轮：待机和开心补帧

- **待机正面**：1 帧 → 4 帧，依次是自然站立、吸气（肩略抬）、轻微左倾、轻微右倾。脚位置不变，每帧 550 ms 循环（`IDLE.frame_ms`）。
  - 参考图只当种子帧，不播放（`spec.DROP_FIRST`）。原因：只照参考图重画的那一帧，和由它派生出来的帧在头发蓬度、裙子蕾丝上对不上，循环时会跳。现在播放的 4 帧都是同一批派生出来的，和眨眼、张望的帧风格一致。
  - 待机提示词加了「双眼睁开、手势不变、不眨单眼、不比手势」。Neon 第一版待机全变成了眨眼比耶，已重新生成。
- **开心**：4 帧 → 6 帧，新增「跳起来双脚离地」和「落地屈膝」。每帧 175 ms，正好一轮 1.05 秒。程序化的弹跳删掉后，这两帧补回了跳跃感。
- **生成量**：4 个形态共生成 28 张，重新生成 6 张（Claude 待机 2 张、Neon 待机 4 张）。旧素材备份在 `art_backup/<form>-20261119-115xxx`。
- **验证**：
  - `pytest` 100 项全部通过。
  - 离屏检查没有任何动作被裁掉。
  - 各动作渲染出的人物高度相差不超过约 6 像素，切换动作时不会忽大忽小。
  - 预览动图：`art_work/motion_neon.gif`、`art_work/motion_claude.gif`。

## 2026-11-19 · 第十二轮：恢复程序化动作（调轻），和图像帧叠加

- **起因**：查了上游 QCYTSN/ds-local-pet（大肥鱼）。它一共只有 67 帧，待机、开心、说话等都只有 1 帧。看着流畅，靠的是每 20 ms 刷新一次的程序化动作，加上切换动作时的淡入淡出。纯靠生图补到每秒 12 帧，每个形态要约 300 张，而且生成的帧之间细节对不齐，帧率越高越闪。用户因此决定恢复程序化动作。
- **`animation/effects.py` 恢复**，基于第八轮的版本，并把和图像帧重叠的部分调轻：
  - 待机：重心转移 1.4 → 0.8 px、倾斜 1.1° → 0.6°，呼吸缩放保留。
  - 开心：弹跳 15 → 6 px，因为帧里已经有起跳和落地。
  - 说话：点头 1.8° → 1.0°。生气：抖动 2.8 → 1.6 px。扫地：摆动 4.5 → 2.5 px。庆祝：跳高 22 → 14 px。
  - 其余动作不变：走路起伏、拖拽钟摆、落地挤压、眩晕绕圈等。
- **`pet/renderer.py`**：恢复姿态应用，包括站立动作「不穿地、倾斜时自动抬高」的修正。画出来的装饰（思考圆点、星星、彩带、Zzz 等）不再画，生成的帧里已经有了。
- **分工**：帧负责手势、表情、头发、道具；程序化动作只负责整体的呼吸、起伏、挤压拉伸、摆动。「减少动态」开关可以整层关掉程序化动作。
- **验证**：
  - `pytest` 103 项全部通过，恢复了 `tests/test_effects.py` 并按新幅度调整。
  - 离屏逐帧检查 4 个形态的全部动作，没有被裁掉的。
  - 预览：`art_work/motion_claude.gif`、`art_work/motion_carbon.gif`。

## 2026-11-19 · 第十三轮：程序化动作整体调小

- 用户实测后反馈幅度太大。
- 新增整体幅度系数 `comfort.motion_scale`，默认 0.4：所有位移、缩放、旋转、阴影变化都按这个系数缩小（`animation.effects.scaled()`，渲染器读取 `PetRenderer.motion_scale`）。动作曲线本身没改，只是统一调小。
- **想再调的话**：在 `config.json` 的 `comfort` 下改 `motion_scale`（0 关掉，1 是原始幅度，最大 1.5），重启后生效。面板里还没有这个滑块。
- **验证**：`pytest` 104 项全部通过，新增 `test_scaled_shrinks_every_delta`。

## 2026-11-19 · 第十四轮：待机改回单帧（与大肥鱼对比后）

- **对比方法**：把上游 QCYTSN/ds-local-pet 下载到 `D:\dafeiyu-compare`（关掉了自动更新），和 AGY 桌宠并排运行，同一时间连拍待机，并缩放到同一大小比较。对比脚本是 `art_work/compare.py`。注意：副屏缩放是 150%，脚本要开每个显示器单独的 DPI 感知，截到的位置才对。
- **结论**：
  - 大肥鱼的待机是 1 张图加呼吸，相邻两张截图的变化一直在 0.2～6 之间。
  - 我们的 4 帧待机在 1～3 和 11～17 之间来回跳。原因是各帧的头发细节不一致，换帧时会突跳，并不是程序化动作的问题。
- **修改**：
  - 待机只播 1 帧：`spec.KEEP_FRAMES = {"idle_front": 1}`，`IDLE` 去掉 `frame_ms`。
  - 用的是派生出来的那张自然站立帧，和眨眼、张望的帧风格一致。
  - 另外 3 张原始帧还留在 `art_work/<form>/raw/idle_front/`，没有删。
  - 其他动作的多帧保留，程序化动作保留，幅度系数仍是 0.4。
- **验证**：
  - `pytest` 104 项全部通过。
  - 已确认安装的待机图就是新处理出来的那张。
  - 各动作之间人物高度最多差约 12 像素（Claude 的开心）。

## 2026-11-19 · 第十五轮：走路重做为 6 帧，说话、跺脚放慢

- **走路问题**：先排除了播放问题。离屏模拟走路时 4 帧正常轮换；实机连拍放大后，帧也在切换，人也在移动。真正的原因是旧的 4 帧走路图腿只是小幅交替，手臂和身体几乎不动，缩小后看起来像同一个姿势。
- **走路重做**：每个形态重新生成 6 帧的完整步态：
  1. 左脚大步着地，右手前摆
  2. 下沉，重心在前腿
  3. 抬膝过腿，身体最高，头发、裙子上扬
  4. 右脚大步着地，左手前摆
  5. 下沉，重心在前腿
  6. 抬膝过腿，身体最高
  - 每帧 120 ms，一个循环 0.72 秒。
  - 程序化走路起伏的频率从 2.08 改成 2.78，对上新的步频。
  - 4 个形态共生成 24 张，0 失败。旧的 4 帧在 `art_work/<form>/raw/walk_side.old4/`，安装前的素材在 `art_backup/<form>-20261119-1244xx~1247xx`。
- **放慢的循环**（`frame_ms`）：

  | 动作 | 原来 | 现在 |
  |---|---|---|
  | 说话 | 220 ms | 380 ms |
  | 生气（跺脚） | 180 ms | 300 ms |
  | 眩晕 | 170 ms | 260 ms |
  | 扫地 | 230 ms | 320 ms |
  | 被拖拽 | 220 ms | 300 ms |
  | 下落 | 150 ms | 200 ms |
  | 思考 | 420 ms | 500 ms |

- **验证**：
  - `pytest` 104 项全部通过。走路帧数的断言已从 4 改为 6。
  - 离屏模拟走路时 6 帧按 120 ms 轮换。
  - 4 个形态全部动作都没有被裁掉。
  - 预览：`art_work/motion_claude.gif`、`art_work/motion_carbon.gif`，内容是走路、说话、生气。

## 第 16 轮：表情切换（2026-11-19）

- 四个形态各 6 个表情：happy / focused / worried / sleepy / shy / pout，外加 calm（原待机帧）。
- 素材：`tools/sprite_gen/expressions.py`（gen → composite → install → sheet）。以待机帧为底图编辑，只合成脸部：环形对齐 + 脸核心椭圆 ∪ 脸附近真正变化的像素（避免椭圆羽化边缘出现半透明重影）。安装到 `<form>/processed/runtime/expressions/<name>_<h>.png`，清单 `expressions` 段。已校验：尺寸与 idle_front 完全一致，下半身像素差为 0。
- 运行时：`animation/expressions.py` 的 `ExpressionDirector`。优先级：悬停→shy；动作提示（HAPPY/CELEBRATE→happy，ANGRY→pout，DIZZY→worried，持续 20 s）；额度 <20%→worried；Agent 运行中→focused；烦躁≥0.3 或心情<0.3→pout；精力<0.25 或用户空闲≥10 分钟→sleepy；心情≥0.8→happy；否则 calm。每个表情至少保持 12 s，悬停与动作提示立即生效。
- 渲染：只在 IDLE 帧（idle_front）上换脸，0.2 s 淡入（旧脸铺底、新脸叠加，身体不会半透明）。程序化呼吸/摇摆照常叠加。
- 开关：`comfort.expressions`（默认开）。
- 测试：`tests/test_expressions.py`（规则、保持/立即切换、淡入、四形态素材齐全且与待机帧同尺寸、渲染只替换待机帧）。全量 109 passed。
- 预览：`art_work/expressions_preview.png`。待用户重启实机验证。

## 第 17 轮：对 agent 语音输入（2026-11-19）

- 方式：不自己录音，桌宠通过 Windows UI Automation 按 Antigravity 自带的按钮（`Record voice memo` → `Stop recording` → `Send message`），识别由 Antigravity 完成，文字进入当前对话。实测：停止后文字填进输入框、不会自动发送；麦克风按钮恢复即识别完成。
- `agy/voice/agy_voice.ps1`（纯 ASCII，PowerShell 5.1）：`-Action probe|start|finish|cancel [-Send]`，输出一行 JSON 状态码。只按按钮，不读取对话内容。
- `agy/voice/__init__.py`：`VoiceBridge` 用 QProcess 异步调用，不阻塞；两次按下（开始 / 结束并发送），最长 90 s 自动结束；退出桌宠时若在录音会先停止。
- 入口：快速控制面板“对 agent 说话”、托盘菜单“对 agent 说话 / 发送”；录音中单击桌宠 = 结束并发送。录音中是“专注”脸，发送成功开心，失败担心。
- 配置：`agy.voice_input`（默认开）、`agy.voice_auto_send`（默认开；关掉则只填进输入框）。
- 测试：`tests/test_voice_input.py`（解析、状态码都有中文提示、脚本 ASCII、用假脚本跑真实 QProcess 的状态机）。全量 116 passed。真实 Antigravity 上 probe 返回 ready（0.8 s）。
- 未实测：桌宠内的完整录音→发送流程（待用户重启后试）；窗口最小化；Claude 桌面版（按住录音，未接）。

## 第 18 轮：agent 接口的朗读和听写（2026-11-19）

- 用户反馈第 17 轮（按 Antigravity 麦克风）用处不大；功能保留，重点改为 agent 接口（MCP / petctl）的语音交互。
- **朗读**：`agy/voice/speech.py` `PetSpeaker`，Qt TextToSpeech（WinRT 优先，SAPI 兜底），离线无新依赖。本机可用：慧慧、瑶瑶（WinRT），慧慧 Desktop（SAPI）。各形态不同音色/音高。只念 agent 经 `say` / `task` 发来的话（内心独白不念），朗读期间气泡不消失。配置 `agy.speak_aloud`（默认开）、`speech_volume` 0.8、`speech_rate` 0。测试用 `AGY_PET_TTS_ENGINE=mock` 保持静音（conftest 已设）。
- **听写**：`agy/voice/listen.ps1`（ASCII，System.Speech 离线 zh-CN 识别器 MS-2052-80-DESK）+ `agy/voice/listen.py`（纯标准库）。新 MCP 工具 `pet_listen(prompt?, timeout?)` 和 `petctl listen ["问题"]`：先念问题、等她念完（避免录到自己），桌宠显示“在听”+专注脸，识别后气泡显示“听到了：…”，把文字返回给 agent。控制接口新增 `listen` 命令（phase start/done），status 新增 `speaking`、`listening`。
- `agy/voice/__init__.py` 不再引入 Qt（第 17 轮的桥接挪到 `bridge.py`），MCP 服务保持零依赖。
- SKILL.md / README 已更新：识别会有错字，重要操作要复述确认。
- 测试：`tests/test_speech.py`（可读化、mock 引擎、无引擎静默、解析、等朗读结束再听的顺序、桌宠 listen 命令）。全量 123 passed。真实识别脚本冒烟：安静环境 3 秒返回 silence（总耗时约 7.5 s）。
- 待实机：重启桌宠后听朗读音色；`petctl listen` 真实识别中文效果。

## 清理：删除大肥鱼对比副本（2026-11-19）

- 用户已删除 `D:\dafeiyu-compare`（约 208 MB，上游源码副本，数据都在目录内，无开机自启）。`art_work/compare.py` 因此无法再运行，需要时重新克隆上游。

## 第 19 轮：删除 agent 接口和语音对话；限额分两档；用量看板（2026-11-22）

- **删除**（用户选“接口 + 语音对话”，桌宠日常台词气泡保留）：`agy/control.py`、`pet_client.py`、`petctl.py`、`mcp_server.py`、`agy/voice/`（按 Antigravity 麦克风、朗读、听写）、`integrations/`；窗口里的控制 API、Claude 临时登场（guest form）、语音入口；配置 `control_api`、`agent_guest_form`、`voice_*`、`speak_aloud`、`speech_*`；对应测试。删前备份在 `art_backup/removed_agent_interface_20261122/`（测试改成 `.py.bak` 免得被 pytest 收集）。
- **MCP 注册**：CLI 不在 PATH，直接从 `~/.claude.json` 的顶层 `mcpServers` 删掉 `agy-pet`（只剩 `rea`），原文件备份为 `~/.claude.json.bak-before-agy-pet-removal`。正在运行的 Claude Code 会话可能还挂着旧连接，新会话不会再加载。
- **限额数据调研**（子代理）：`GetUserStatus` 每个模型只有一个 `quotaInfo{remainingFraction, resetTime}`，没有周额度字段。LS v2.34.0 有新 RPC `GetUserQuotaSummary` → `summary.buckets[] / groups[].buckets[]`，每个桶有 `window`、`remainingFraction`、`resetTime`，尚未实测返回值。另外：新版 LS 用 `--read_host_bridge_token_from_stdin`，项目自己的 LS 发现拿不到 CSRF token，现在实时数据来自侧边栏插件写的 `hud_live.json`（或本地日志）。
- **侧边栏插件**（`token-meter/sidecars/dashboard/main.mjs`）：每 60 s 调一次 `GetUserQuotaSummary`，只保留桶的 id/名称/描述/分组/window/剩余/重置/disabled，写入 `hud_live.json` 的 `quotaBuckets` 和 `quotaSummaryStatus`。**项目里已改，未部署**：Antigravity 实际加载的是 `~/.gemini/config/plugins/token-meter`（与项目副本一致），需用户同意后复制过去并重载插件。
- **Python**：`telemetry.QuotaWindow`、`classify_window`（5h / week 正则）、`parse_quota_buckets`、`LiveSnapshot.quota_for("5h"|"week")`：有桶用桶（同类取最紧的），没有就把单一限额按重置距离归类（≤5.2 h 算 5h，否则算每周）。
- **HUD**：胶囊里“限额”一格改成上下两行（5h / 周）；对话框卡片下方两行“5h 限额 / 周限额 + 重置倒计时”；悬停提示也分两档。
- **Token Meter**：新增首个标签页“用量看板”（`agy/usage_dashboard.py` + 纯计算 `agy/usage_stats.py`）：累计 Token、单日峰值、最长连续工作（同会话步骤间隔 ≤5 分钟的最长一段，估算）、最长/当前连续天数、5 小时 / 每周两条进度、每日热力图（模型、指标筛选；每天/每周/累计）。`MeterReport` 新增 `conversations`。顶部限额卡片显示 5h 和周。
- 测试：`tests/test_usage_dashboard.py`（连续天数、峰值、最长任务、周/累计、中文数字、桶分类、单一限额归类、看板渲染）；更新 test_agy / test_hud_dialog。全量 102 passed。
- 实测数据：本地日志 24 个会话，最早 2026-11-16，累计约 9.7 亿 token；当前单一限额 61%（1h41m 后重置）→ 归为 5h，周额度显示“暂无数据”，等插件部署后看 `quotaBuckets`。

## 第 20 轮：爬窗口和坐窗沿（2026-11-22）

- 新素材（四个形态，各 4 帧）：`climb_side`（侧面朝左爬墙，`climb_side_right` 由镜像得到）、`perch_sit`（正面坐在边沿上、双腿垂下晃动）。旧素材备份在 `art_backup/<form>-20261122-23*`，spec 备份在 `art_backup/spec_before_climb.py`。
- 新动作 `CLIMBING`（优先级 95，不可打断，220 ms/帧）；没有素材时回退到 `walk_side`，`perch_sit` 回退到 `sit_edge`。
- `pet/climb.py`：纯几何的爬窗控制器。走到窗口较近一侧 → 沿边竖直上爬（62 px/s）→ 手够到顶边时用 `plan_hop` 小跳翻上去并附着。条件：窗口底部贴近她脚下、上方有空间、不是全宽、距离 420 px 内；窗口移动、关闭或最小化，或者被抓住时会掉下来。
- 坐窗沿：在窗口上时 `PERCH` 改用 `perch_sit`，并按各形态 manifest 的 `seat_line`（Claude 0.74，其他 0.68）往下沉，让窗口边沿对齐膝弯。挂墙和坐沿时不画影子，也不倾斜。
- 触发：自主跳窗时，能爬就先爬；面板「高级」新增「爬窗口」「坐窗沿」按钮。
- 测试：109 项通过；新增 `tests/test_climb.py`（规划、阶段推进、中止，以及完整的「走→爬→翻→落→坐沿」窗口级流程）。离屏合成检查了四个形态的坐沿效果，以及 Claude、carbon 在窗口左右两侧的攀爬（朝向墙、手贴边）。窗口级测试也覆盖了从 WORKING 状态出发的情况（走过去时会切到 WALKING）；坐下和起身改成直接切换，不交叉淡入淡出。
- 未做：真机效果待重启后确认；平时闲逛不会自己去爬窗口（只在陪 Antigravity 干活和手动按钮时爬）。

## 第 21 轮：坐窗沿打磨、自己找窗口爬、竖向 HUD、上下文 512k（2026-11-22）

- **坐窗沿保持安静**：`perch_sit` 只播第 0 帧（基础 manifest 新增 `frame_pick`）；挂在墙上或坐在窗沿上时，程序动画（晃动、上下浮动、倾斜）全部关掉。
- **切形态不站起来**：在窗沿上坐着（PERCH/WORKING）时切形态，不再播放 TRANSFORM，只换素材。
- **坐着干活**：新素材 `perch_work`（四个形态，4 帧：坐在窗沿上，腿垂下，膝上悬浮屏幕打字），帧间几乎没有变化。在窗口上进入 WORKING 时用它，同样会往下沉。`EDGE_ASSETS = {PERCH: perch_sit, WORKING: perch_work}`；每个形态的 `seat_line` 都包含 `perch_work`。
- **自己找窗口爬**：`Win32WindowRectReader.list_windows()` 用 EnumWindows 列出可见的普通应用窗口，过滤掉最小化、工具窗口、有 owner 的弹窗、cloaked 窗口和本进程窗口。`_nearest_climbable()` 挑能爬的最近那个窗口；面板「爬窗口」优先用它。空闲时（IDLE，漫步模式，Antigravity 不在生成）每 70–160 秒试一次，爬上去后 60% 概率坐下。在窗口上待 2–5 分钟后，走到窗口一端轻跳下来，这次落地不算重摔、不会晕；跳下的那个窗口 3 秒内不算平台。新增配置 `agy.explore_windows`（默认开启）。
- **HUD 改竖向卡片**：从上到下是 ⚡速率、5h（进度条 + %）、周（进度条 + %）、缓存、上下文。旧版备份在 `art_backup/hud_bar_before_vertical.py`。
- **上下文窗口**：以前并没有真正读取，sidecar 和桌宠都把 Gemini 写死成 1M。现在 sidecar 会在 `GetUserStatus` 的每个模型配置里找上下文窗口字段，找到就用（`contextLimitSource: "ls"`），找不到就用 512k（524,288）；同时把配置的字段名写进 `model_configs.json`，方便确认字段到底在哪里。桌宠只在 source 为 `ls` 时采用 sidecar 给的值，否则按 512k 推断。
- **sidecar 已部署**（经主人同意）：复制到 `~/.gemini/config/plugins/token-meter/sidecars/dashboard/main.mjs`，旧版备份在 `art_backup/token-meter-deployed-20261122/`。重载插件后才生效，周额度依赖它。
- 补充：只会从自己爬上去（或面板让她上去）的窗口自动跳下，Antigravity 的窗口仍归自主行为管，生成结束后照样坐一会儿；窗口被其他窗口挡住侧边或大半顶边时不爬（`is_exposed`）；在窗沿上被戳、说话之类的一次性动作结束后回到坐着或干活，不会站起来。
- 上下文「已用」= 最近一步的 input + cache read + output（约等于下一次请求的 prompt 大小），这部分没问题，错的只是上限。
- 测试：114 项通过。离屏预览：`art_work/preview_edge_work.png`、`art_work/preview_hud_vertical.png`。
- 待真机确认：重载 token-meter 插件后，`hud_live.json` 里是否有 `quotaBuckets`（周额度），以及 `model_configs.json` 里是否有上下文窗口字段。对话框样式的 HUD 卡片仍是原来的两列布局。

- 补充：开了「跟随模型」时，自动换形态会附带一个 HAPPY（站着欢呼），让她在窗沿上站起来。现在坐在窗沿上时，只保留台词、跳过这类站立反应，保持坐着或继续干活（测试已覆盖）。

## 第 22 轮：等效 API 费用；活动热力图默认按月（2026-11-23）

- `assets/pricing.json`：从 Gemini API 官方价格页（aistudio.google.com/docs/pricing，付费 Standard 档）核对的价格，单位 USD/1M tokens，2026-11-23 核对。Neon 3/15/0.15；Hydrogen 1.5/7.5/0.075；Carbon 和 Argon 2/10/0.10，2026-12-01 起变为 4/20/0.20。按模型 id 里的关键词匹配，思考档位同价；支持生效日期；`unknown_as` 用于没记录模型的离线日志步骤（默认按 Carbon 估算，单独列出）；`usd_to_cny` 默认 7.1。
- `agy/pricing.py`：逐步计费（输入只算未命中缓存的部分，缓存读按缓存价，输出含思考），给出按模型的明细、按天的金额、估算部分、缓存省下的钱，以及未定价的 token 数。
- 用量看板新增「等效 API 费用」卡片：总额（USD 和约合人民币）、今天、近 7 天、本月、缓存省下，以及按模型的输入、缓存读、输出金额明细。热力图的指标下拉框新增「等效金额（USD）」。
- 当时的数据（24 个会话，2026-11-16 起）：约 **$296 ≈ ¥2,099**，其中 $103 是未记录模型按 Carbon 估算的部分；缓存省下约 $1,580。
- 热力图：默认「按月」日历（7 列，单格 46px，带日期数字，‹ › 切换月份，不能翻到未来），可以切到「按年」看原来的整年视图。
- 测试：118 项通过（新增 `tests/test_pricing.py`，扩展了看板测试）。预览：`art_work/preview_dashboard_cost.png`。

## 第 23 轮：周额度改用正确的 RPC；费用不换算人民币（2026-11-23）

- 新 sidecar 生效后，`quotaSummaryStatus` 显示「GetUserQuotaSummary HTTP 404」：语言服务器上没有这个方法。在 language_server.exe 的字符串里找到，语言服务器提供的是 `exa.language_server_pb.LanguageServerService/RetrieveUserQuotaSummary`（`GetUserQuotaSummary` 是 Google 后端 JetskiRemoteAgentProxyService 上的方法）。
- sidecar 改为先调用 `RetrieveUserQuotaSummary`，失败再试旧名。回复里任何带 `remainingFraction` 的对象都当作额度桶（适应未知的字段结构），收集各种窗口、名称、类型字段的文字交给桌宠分类；原始回复写进 `quota_summary_raw.json`，用于核对结构。桌宠的窗口识别也认 `FIVE_HOUR`、`7_DAY` 这类枚举写法。已重新部署（上一版备份为 `art_backup/token-meter-deployed-20261122/main_round21.mjs`）。需要再重启一次 Antigravity，真实返回还没验证。
- `model_configs.json` 已确认：模型配置里没有上下文窗口字段，只有一个 `quotaInfo`（所有模型共用，49.3%）。上下文上限只能用默认的 512k。
- 等效费用只显示美元，去掉了人民币换算（`usd_to_cny`）。测试 118 项通过。
- 实测（重启 Antigravity 后）：`RetrieveUserQuotaSummary` 返回 `response.groups[]`，分为「Gemini Models」和「Claude and GPT models」两组，每组各有 `window: "weekly"` 和 `"5h"` 两个桶，字段有 `bucketId`、`displayName`、`description`、`remainingFraction`、`resetTime`，sidecar 都正确解析了。问题出在桌宠取了所有组里最紧的那个，于是显示成 Claude/GPT 组的周额度（54%，实际 Gemini 是 59%）。现在按当前模型选组：标签含 claude/gpt/oss/opus/sonnet 的用 Claude/GPT 组，其他用 Gemini 组；不知道当前模型时才取最紧的。新增测试，共 119 项通过。不需要重新部署 sidecar。

- 真机确认（2026-11-23 00:24 重启桌宠后）：HUD 显示 5h 49%、周 59%，与 Antigravity 设置页的 Gemini 组一致；`quotaSummaryStatus: ok`，没有新的崩溃日志。

## 2026-11-23 · 第二十四轮：Argon（氩猫）形态

- **形象**：新画的猫娘，淡紫银发，发梢带紫光，眼睛半睁，戴放电管发夹，穿白紫色宽大连帽外套、灰紫百褶裙、白色过膝袜和猫猫拖鞋，总抱着猫猫枕。先出了 3 版定妆图，用户选 #1，并要求去掉身边的星光粒子，保留抱枕和拖鞋。去粒子的版本 `art_work/argon/reference.png` 作为参考图。生成时用 Carbon 的立绘锁定画风和比例。
- **动作**：按用户的要求「大部分时候抱着，动作配合抱枕做优化」，`spec.py` 里给 argon 写了专门的 `FORM_POSES`：
  - 开心：抱紧枕头蹭一蹭。
  - 生气：把半张脸埋进枕头。
  - 庆祝：把枕头举过头顶，不跳。
  - 伸懒腰：举着枕头伸。
  - 睡觉：脸枕在枕头上。
  - 扫地和吃东西：枕头夹在腋下。
  - 坐窗沿：枕头放在腿上；在窗沿工作时，屏幕浮在枕头上方。
- **新机制 `FORM_NOTES`**：给某个形态的某个动作，每一帧后面追加一句。Argon 用它做到：
  - 走路时双手抱枕头，不摆臂。
  - 爬窗时枕头用丝带绑在背上，空出双手。
- **生成过程**：先用 7 个关键动作试生成，检查通过后再生成其余帧，0 失败。在窗沿工作的第 2、3 帧丢了屏幕，第 3 帧腿也变了，加强提示后重生成。
- **数量**：共 135 帧，处理成 39 个 asset。
- **表情**：6 个（happy/focused/worried/sleepy/shy/pout），sleepy 等用了偏慵懒的版本。脸部区域 `FACE_BOX["argon"] = (495, 535, 165, 95)`，合成后接缝正常。
- **坐线**：`seat_line` 定为 perch_sit 0.71、perch_work 0.70，和 Claude、Carbon 对比膝盖位置后确定。离屏预览坐窗沿和在窗沿工作都贴合：`art_work/preview_argon_edge.png`、`art_work/preview_argon_actions.png`。
- **台词**：`assets/dialogue/forms/argon.json`，结构和条数与其他形态完全一致。语气慢悠悠、拖长音、惰性气体梗，名牌「Argon」。
- **代码**：
  - `characters.py` 的形态顺序改为 carbon → hydergon → neon → argon → claude，名牌颜色 `#c4b5fd`。
  - 模型标签含 argon 时，「跟随模型」会切到 Argon（以前不切换）。
  - 气泡强调色 `#8b5cf6`。
  - 额度按 Gemini 组算。
- **测试**：
  - 形态列表扩到 5 个，Argon 映射的断言改成 `"argon"`。
  - `test_external_config_hot_reload_preserves_position` 原来写死 x=321。但切换形态会保持脚底中心，Carbon 和 Neon 最宽帧不一样（373 和 385），x 会偏 6px，所以这个断言不对。改成检查中心不变。这个问题与 Argon 无关：退回旧的 `characters.py` 也会失败。
  - 全量 122 passed。
- **备份**：`art_backup/spec_before_argon.py`、`characters_before_argon.py`、`expressions_before_argon.py`、`argon-20261123-005947`。
- **待实机验证**：需要用户重启桌宠。

## 2026-11-23 · 第二十五轮：精确追踪当前会话与上下文 + 注册为 Antigravity 插件

- **上下文计算口径修正**：
  - `agy/telemetry.py` 新增 `StepUsage.context_tokens = input_tokens + cache_read_tokens + response_tokens`（剔除单步 `thinking_tokens`；`total_tokens` 仍保留思考部分供累计消耗与计费使用）；`parse_transcript_lines` 同步拆分 `thinking_tokens` / `response_tokens`。
  - 修复 `infer_context_limit` 把 `selected_model_label` 和 `last_step_model_label` 拼接匹配造成切模型后上下文上限污染的问题：改为按运行态（取最近一步模型）或空闲态（取选择器模型）单独匹配，跳过「未选择模型」等占位符。
- **当前会话焦点精确追踪**：
  - 结合四路本地信号判定当前正在看的会话：`annotations/<cid>.pbtxt` 与 `summary.annotations.lastUserViewTime`（点开旧会话只看不发即切换）、`active_session.json`（插件 Hook `SessionStart` / `PreInvocation` 零延迟锁定新建或刚发送会话）、`~/.gemini/config/projects/*.json`（切到无会话项目时重置为 `0 · 0%`），以及 `lastUserInputTime`。
  - `TelemetryCollector` 读取源优先级改为 `ls → pet_live.json → hud_live.json → transcript.jsonl`；`agy/hud_bar.py` 与 `agy/token_meter.py` 新增 `pet_live` 来源显示。
  - 同步更新仓库内 `token-meter/sidecars/dashboard/main.mjs` 与 `app.js`（不覆盖全局已安装副本）。
- **外部配置热加载**：`settings/config.py` 新增 `reload_if_external_change`，`pet/window.py` 主循环每 1.5s 检查且在 `save_snapshot` 保存前先同步外部修改（保留实时 `x`/`y` 坐标），支持插件侧边栏修改即时生效。
- **Antigravity 插件 `agy-pet`**：
  - 新增 `agy-plugin/` 并部署到 `~/.gemini/config/plugins/agy-pet/`，包含 `plugin.json`、`assets/logo.png`（从 `icon.ico` 导出的 256×256 PNG）、`hooks.json` + `hooks/track_session.mjs`（`SessionStart` / `PreInvocation`）、`sidecars/pet-bridge/`（`pet_live.json` 桥接 + 侧边栏控制台，支持 Carbon/Hydrogen/Neon/Argon/Claude 五形态切换、跟随模型、HUD 外观、启动/唤醒）与 `skills/agy-pet/SKILL.md`。
- **验证**：`node --check` 校验 5 个 JS 文件全部通过；隔离环境变量下 `track_session.mjs` Hook 冒烟返回 `{}` 且退出码 0；`GetAllPlugins` RPC 确认 `agy-pet` 已发现并启用（`hooks = True`、`skills = agy-pet`）；全量 `pytest` 通过（需注意 `tests/test_agy.py::test_summary_cache_context_and_rows` 将 `context_used_tokens` 期望值由 `4400` 更新为 `4200` 以匹配剔除 `thinking_tokens=200` 后的口径）。
- **标准根目录插件重构**：按发布规范将原 `agy-plugin/` 的 `plugin.json`、`hooks.json`、`hooks/`、`sidecars/pet-bridge/`、`skills/agy-pet/` 与 `assets/logo.png` 提升至仓库根目录；移除 `sidecar.json` 中硬编码的 `AGY_PET_ROOT`，`main.mjs` 改为相对插件目录 + `.pet_root` 自动解析并扩展 Python 启动器探测链；`.gitignore` 新增 `.pet_root` 及中间高分辨率母版图过滤（`*/processed/masters/*` 仅保留 `idle_front.png`）。`agy plugin validate --strict` 与 `GetAllPlugins`、`pytest` 均验证通过。
