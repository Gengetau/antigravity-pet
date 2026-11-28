"""Turn telemetry changes into rate-limited pet reactions, particles, and seasonal greetings."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from datetime import datetime

from app.i18n import get_language, tr
from app.i18n_lines import GREETING_LINES, REACTION_LINES, REACTION_TOOL_STATUS
from .characters import form_for_model_label
from .milestone import MilestoneEvent
from .telemetry import LiveSnapshot, format_reset_countdown, format_tokens, parse_iso_ms


def tool_status_name(category: str, *, lang: str | None = None) -> str:
    code = lang or get_language()
    if code != "zh":
        loc = REACTION_TOOL_STATUS.get(code, {}).get(category)
        if loc:
            return loc
    return TOOL_STATUS_NAMES.get(category, "")

TOOL_STATUS_NAMES: dict[str, str] = {
    "reading": "陪你读代码",
    "writing": "陪你写代码",
    "running": "盯终端跑命令",
    "searching": "一起查资料",
    "drawing": "围观画图中",
    "delegating": "指挥子代理",
    "asking": "等你确认啦",
}

LINES: dict[str, tuple[str, ...]] = {
    "started": (
        "Antigravity 开始干活了，我在旁边盯着 token。",
        "新一轮推理启动，起飞！",
        "模型在思考，我帮你数 token/s。",
    ),
    "finished": (
        "这一轮跑完了，共 {total} tokens。",
        "回复完成～本轮共 {total} tokens。",
        "落地成功！本轮 {total} tokens，平均 {rate} tok/s。",
    ),
    "turn_error": (
        "哎呀，刚才那轮出错中断了，我们一起看看报错吧。",
        "好像翻车了……别急，我陪你排查！",
    ),
    "waiting": (
        "喂喂，Antigravity 卡在等你确认或回复啦！",
        "那边有确认弹窗/提问在等你哦～",
    ),
    "subagent_start": (
        "召唤出小分身帮忙干活啦！",
        "子代理小分身就位，人多力量大！",
    ),
    "subagent_many": (
        "哇，同时派出 {count} 个小分身！排面拉满～",
        "{count} 个小分身并行开工，效率起飞！",
    ),
    "subagent_done": (
        "辛苦啦 {name}，成果我收下啦～",
        "{name} 交卷成功！配合满分～",
        "太棒了，{name} 顺顺利利收工啦！",
    ),
    "subagent_cheer": (
        "喂，摸完 {name} 也要多摸摸我才行～",
        "谢谢帮我给 {name} 打气呀！",
        "{name} 被夸得干劲翻倍啦～",
    ),
    "subagent_report": (
        "收到 {name} 的汇报：{title}！",
        "了解啦 {name}，{title} 交给我衔接～",
    ),
    "subagent_high_five": (
        "和 {name} 击掌成功！合作无间～",
        "贴贴！我和 {name} 默契拉满～",
        "耶！和 {name} 并肩作战效率起飞！",
    ),
    "subagent_group_cheer": (
        "全员干劲拉满，一起冲鸭！",
        "我和小分身合体共舞，势不可挡！",
    ),
    "subagent_relay": (
        "收到 {name} 传来的线索啦～",
        "干得漂亮 {name}，我来整合！",
        "信号同步完毕，继续推进～",
    ),
    "subagent_pet_rub": (
        "哇，{name} 被揉得呼噜呼噜的～",
        "揉完 {name} 记得也揉揉我呀～",
    ),
    "subagent_trick": (
        "拍手！{name} 这招表演满分～",
        "哇！{name} 转圈圈好可爱～",
    ),
    "subagent_gift_share": (
        "哇，谢谢 {name} 送的小礼物！",
        "收到 {name} 的小鱼干啦，干劲满血～",
    ),
    "subagent_clone_buddy": (
        "哈哈，{name} 和同伴配合得真默契～",
        "大家击掌贴贴，团队氛围满分！",
    ),
    "subagent_clone_chat": (
        "咦，{name} 们在交流什么小秘密呀～",
        "听到你们互相打气，我也更有劲啦！",
    ),
    "subagent_host_pat": (
        "摸摸 {name} 的小脑袋，辛苦啦～",
        "乖啦乖啦，{name} 今天表现满分～",
        "姐姐给你摸摸头，干完活一起吃小鱼干！",
    ),
    "subagent_clone_train": (
        "呜呜——小分身列车出发啦，队形好整齐！",
        "排好队跟紧哦，小小巡游队太可爱啦～",
    ),
    "subagent_clone_wave": (
        "轮到姐姐收尾啦，大家的人浪接力大成功！",
        "哇！全员人浪整齐起飞，士气满分～",
    ),
    "subagent_snack_party": (
        "发小鱼干啦！辛苦的小分身们快来补充能量～",
        "姐姐请客，排排坐吃小鱼干歇会儿～",
    ),
    "subagent_group_huddle": (
        "哇哇！被小分身们团团抱住啦，好暖和～",
        "大家贴得这么紧，姐姐瞬间满血复活！",
    ),
    "subagent_twin_mirror": (
        "哇！同款 {name} 双子镜面舞，同步率满分～",
        "一模一样的 {name} 们太默契啦，效率双倍起飞！",
    ),
    "subagent_mini_me_mimic": (
        "呀！迷你版 {name} 跟我摆同款姿势，太可爱啦～",
        "大小 {name} 同框干活，姐姐干劲拉满！",
    ),
    "subagent_tea_party": (
        "工作间隙开场桌面下午茶会！大家快来喝杯热茶～",
        "叮～奶油小圆桌摆好啦，尝尝草莓蛋糕补充能量！",
    ),
    "subagent_tea_party_interact": (
        "再来一杯暖花果茶，点心管够哦～",
        "叮～刚切好的草莓蛋糕，大家趁热吃！",
    ),
    "subagent_campfire_night": (
        "点起暖暖小篝火，加班夜里烤串棉花糖歇会儿～",
        "围着小火堆聊聊天，夜深了也不孤单！",
    ),
    "subagent_campfire_night_interact": (
        "火苗更旺啦，小心棉花糖别烤焦哦～",
        "添块暖柴，整张桌面都暖烘烘的啦！",
    ),
    "subagent_art_studio": (
        "桌面小画室开张！大家这是要给姐姐画肖像吗～",
        "好呀，姐姐摆好姿势，记得画得亮晶晶的！",
    ),
    "subagent_art_studio_interact": (
        "哇，这幅肖像画得超像我！姐姐珍藏起来～",
        "太厉害啦，每换一幅都比上一幅更可爱！",
    ),
    "subagent_cloud_nap": (
        "软乎乎云朵窝铺好啦，大家一起小憩片刻吧～",
        "盖上星星小被子，打个盹再继续精神满满！",
    ),
    "subagent_cloud_nap_interact": (
        "轻轻帮大家掖好小被角，好梦哦～",
        "云朵拍得更蓬松啦，呼噜呼噜真舒服～",
    ),
    "subagent_cloud_nap_wake": (
        "呼——小憩完精神满格，继续一起推进吧！",
        "伸个懒腰，睡完一觉效率翻倍～",
    ),
    "playmate_summon": (
        "闲着没事，摇来 {names} 陪我玩会儿～",
        "叮！随机召唤出 {names} 来串门啦～",
        "摸鱼时间！叫来 {names} 一起玩～",
    ),
    "playmate_add": (
        "越热闹越好！欢迎 {names} 加入派对～",
        "叮！又摇来 {names} 一起玩啦～",
    ),
    "playmate_done": (
        "拜拜啦 {name}，下次闲了再一起玩～",
        "今天和 {name} 玩得好开心，回见！",
        "{name} 回口袋休息啦，下次再约～",
    ),
    "playmate_cheer": (
        "喂，摸完 {name} 也要顺手摸摸我呀～",
        "哈哈，{name} 被你逗得好开心！",
    ),
    "playmate_report": (
        "好呀好呀，和 {name} 一起{title}！",
        "嗯嗯，我也喜欢和 {name} {title}～",
    ),
    "playmate_high_five": (
        "和 {name} 击掌贴贴！摸鱼搭子满分～",
        "耶！和 {name} 玩得超开心～",
    ),
    "playmate_group_cheer": (
        "闲时小派对！大家一起蹦起来～",
        "和随机小分身们开趴体啦！",
    ),
    "playmate_relay": (
        "接住啦 {name}！我也回你一颗星星～",
        "哈哈 {name} 好调皮，再来一次！",
    ),
    "playmate_pet_rub": (
        "哇，{name} 被揉得眼睛都眯起来啦～",
        "偏心！揉完 {name} 也要多揉揉我～",
    ),
    "playmate_trick": (
        "拍手拍手！{name} 转圈圈超可爱～",
        "哇！{name} 还会变小花样呢，再来一个！",
    ),
    "playmate_gift_share": (
        "哇，谢谢 {name} 塞给我的小礼物！",
        "收到 {name} 的小鱼干啦，贴贴～",
    ),
    "playmate_clone_buddy": (
        "哈哈，{name} 和同伴贴贴得好开心～",
        "姐妹们玩得这么热闹，带我一个呀！",
    ),
    "playmate_clone_chat": (
        "咦，我好像听到 {name} 在偷偷夸我～",
        "你们俩聊什么悄悄话呢，也告诉我嘛！",
    ),
    "playmate_host_pat": (
        "摸摸 {name} 的小脑袋，乖啦～",
        "揉揉 {name}，今天也要开开心心的～",
        "来，姐姐给你摸摸头，贴贴～",
    ),
    "playmate_clone_train": (
        "呜呜——小火车开过来啦，排得真整齐～",
        "小小列车出发咯，记得带姐姐一程呀！",
    ),
    "playmate_clone_wave": (
        "轮到姐姐收尾啦，人浪接力大成功！",
        "哇！大家的人浪好整齐，耶——！",
    ),
    "playmate_snack_party": (
        "发小鱼干啦！大家排排坐一起来吃～",
        "姐姐请客！小鱼干管够，慢慢吃哦～",
    ),
    "playmate_group_huddle": (
        "哇哇！被小分身们团团抱住啦～",
        "好暖和呀，大家贴得这么紧好幸福～",
    ),
    "playmate_twin_mirror": (
        "哇！双胞胎 {name} 跳镜面舞，姐姐眼花啦～",
        "同步率拉满！哪只才是真正的 {name} 呀～",
        "一模一样的 {name} 们，双倍可爱暴击！",
    ),
    "playmate_mini_me_mimic": (
        "呀！迷你版我自己也太可爱了吧～",
        "大小 {name} 同框！姐姐都忍不住想捏捏脸～",
        "喂喂，学我摆姿势学得也太像啦！",
    ),
    "playmate_tea_party": (
        "叮～桌面下午茶会开张，大家快围坐喝茶！",
        "红茶配草莓蛋糕，和大家一起最甜啦～",
    ),
    "playmate_tea_party_interact": (
        "再来一杯热花果茶，点心管够哦～",
        "哇，谢谢帮大家续杯！茶香飘满桌面啦～",
    ),
    "playmate_campfire_night": (
        "点起暖暖小篝火，今晚一起烤棉花糖聊八卦吧～",
        "围着火堆看星星，夜色都变温柔啦～",
    ),
    "playmate_campfire_night_interact": (
        "火苗更旺啦，小心棉花糖别烤焦哦～",
        "咔嚓添块新柴，烤出的棉花糖外焦里嫩！",
    ),
    "playmate_art_studio": (
        "诶？大家支起小画架要给我画肖像吗，那我摆好姿势！",
        "桌面小画室开张～记得把姐姐画得可爱一点哦！",
    ),
    "playmate_art_studio_interact": (
        "哇画得超像我！姐姐要贴在最显眼的地方～",
        "锵锵～又出新作啦，大家都是天才小画手！",
    ),
    "playmate_cloud_nap": (
        "软乎乎云朵午睡窝铺好啦，大家团在一起打个盹吧～",
        "云朵垫子好松软，盖上星星小被子好安心～",
    ),
    "playmate_cloud_nap_interact": (
        "帮大家把星星小被盖严实啦，做个甜梦哦～",
        "云朵拍得软绵绵的，姐姐也想眯一会儿啦～",
    ),
    "playmate_cloud_nap_wake": (
        "呼——和大家睡得好香，伸个懒腰精神满格啦～",
        "醒啦醒啦，云朵午睡窝也太舒服了吧！",
    ),
    "fast": ("好快！{rate} tok/s，反重力加速中。", "{rate} tok/s，风都追不上。"),
    "quota_low": ("限额只剩 {quota}% 了，省着点用哦。", "提醒：当前模型限额 {quota}%。"),
    "quota_critical": ("限额快见底了（{quota}%），{reset}。", "只剩 {quota}% 限额！{reset}"),
    "quota_reset_soon": (
        "小鱼干马上补货！限额 {reset}～",
        "坚持一下，限额 {reset}，马上满血！",
    ),
    "quota_refilled": (
        "限额补满啦（{quota}%）！干活能量回满～",
        "耶！小鱼干到账，限额恢复到 {quota}%！",
    ),
    "context_high": (
        "上下文已经用了 {ctx}%，可以考虑开新会话了。",
        "上下文窗口 {ctx}% 了，我有点挤。",
    ),
    "form": ("检测到 {model}，切换成 {form} 形态！", "{model} 上线，{form} 形态就位。"),
    "offline": ("Antigravity 好像没开，我先自己玩会儿。",),
    "update": ("GitHub 上有新版本 v{version} 啦，可以在侧边栏点一下更新哦～",),
    "update_commit": ("GitHub 主分支有新提交（{sha}）啦，侧边栏可以一键拉取更新～",),
}

# Solar-calendar fixed holidays: (month, day) -> (id, greeting)
_FIXED_FESTIVALS: dict[tuple[int, int], tuple[str, str]] = {
    (1, 1): ("newyear", "元旦快乐！新年新代码，零 bug 起步～"),
    (10, 1): ("national", "国庆快乐！放假也别忘了好好休息哦～"),
    (10, 31): ("halloween", "不给小鱼干就捣蛋！万圣节快乐～"),
    (12, 25): ("christmas", "圣诞快乐！送你一份热乎乎的圣诞礼物～"),
}

# Lunar festivals mapped to solar (year, month, day) for 2025-2030.
_LUNAR_FESTIVALS: dict[tuple[int, int, int], tuple[str, str]] = {
    (2025, 1, 29): ("spring", "春节快乐！新年万事顺意，代码一次跑通～"),
    (2025, 2, 12): ("lantern", "元宵节快乐！记得吃碗汤圆再写代码～"),
    (2025, 5, 31): ("dragonboat", "端午安康！甜粽还是咸粽，我都喜欢～"),
    (2025, 10, 6): ("midautumn", "中秋快乐！今晚月亮圆圆的，早点休息哦～"),
    (2026, 2, 17): ("spring", "春节快乐！新年万事顺意，代码一次跑通～"),
    (2026, 3, 3): ("lantern", "元宵节快乐！记得吃碗汤圆再写代码～"),
    (2026, 6, 19): ("dragonboat", "端午安康！甜粽还是咸粽，我都喜欢～"),
    (2026, 9, 25): ("midautumn", "中秋快乐！今晚月亮圆圆的，早点休息哦～"),
    (2027, 2, 6): ("spring", "春节快乐！新年万事顺意，代码一次跑通～"),
    (2027, 2, 20): ("lantern", "元宵节快乐！记得吃碗汤圆再写代码～"),
    (2027, 6, 9): ("dragonboat", "端午安康！甜粽还是咸粽，我都喜欢～"),
    (2027, 9, 15): ("midautumn", "中秋快乐！今晚月亮圆圆的，早点休息哦～"),
    (2028, 1, 26): ("spring", "春节快乐！新年万事顺意，代码一次跑通～"),
    (2028, 2, 9): ("lantern", "元宵节快乐！记得吃碗汤圆再写代码～"),
    (2028, 5, 28): ("dragonboat", "端午安康！甜粽还是咸粽，我都喜欢～"),
    (2028, 10, 3): ("midautumn", "中秋快乐！今晚月亮圆圆的，早点休息哦～"),
    (2029, 2, 13): ("spring", "春节快乐！新年万事顺意，代码一次跑通～"),
    (2029, 2, 27): ("lantern", "元宵节快乐！记得吃碗汤圆再写代码～"),
    (2029, 6, 16): ("dragonboat", "端午安康！甜粽还是咸粽，我都喜欢～"),
    (2029, 9, 22): ("midautumn", "中秋快乐！今晚月亮圆圆的，早点休息哦～"),
    (2030, 2, 3): ("spring", "春节快乐！新年万事顺意，代码一次跑通～"),
    (2030, 2, 17): ("lantern", "元宵节快乐！记得吃碗汤圆再写代码～"),
    (2030, 6, 5): ("dragonboat", "端午安康！甜粽还是咸粽，我都喜欢～"),
    (2030, 9, 12): ("midautumn", "中秋快乐！今晚月亮圆圆的，早点休息哦～"),
}


def greeting_for_moment(dt: datetime | None = None, *, lang: str | None = None) -> tuple[str, str, str | None]:
    """Return ``(kind, greeting_line, particle_effect)`` for the local clock/festival."""
    now = dt.astimezone() if (dt is not None and dt.tzinfo is not None) else (dt or datetime.now())
    code = lang or get_language()

    def _loc(kind: str, zh_text: str) -> str:
        if code != "zh":
            return GREETING_LINES.get(code, {}).get(kind, zh_text)
        return zh_text

    lunar = _LUNAR_FESTIVALS.get((now.year, now.month, now.day))
    if lunar is not None:
        kind = f"fest_{lunar[0]}"
        return kind, _loc(kind, lunar[1]), "confetti"
    fixed = _FIXED_FESTIVALS.get((now.month, now.day))
    if fixed is not None:
        kind = f"fest_{fixed[0]}"
        return kind, _loc(kind, fixed[1]), "confetti"
    hour = now.hour
    if 1 <= hour < 5:
        return "late_night", _loc("late_night", "已经凌晨啦，快去睡觉吧，明天再继续～"), "sweat"
    if 5 <= hour < 11:
        return "morning", _loc("morning", "早安！新的一天，一起把今天的任务稳稳拿下～"), "sparkles"
    if 11 <= hour < 14:
        return "noon", _loc("noon", "中午好呀，记得按时吃午饭别饿着！"), None
    if 14 <= hour < 18:
        return "afternoon", _loc("afternoon", "下午好～泡杯茶或咖啡，状态拉满！"), None
    if 18 <= hour < 23:
        return "evening", _loc("evening", "晚上好！辛苦一天啦，今晚也陪着你。"), "sparkles"
    return "night", _loc("night", "夜深啦，注意保护眼睛，收完这波早点休息哦。"), None


@dataclass
class Reaction:
    kind: str
    text: str
    action: str | None = None  # PetAction name
    form: str | None = None
    particle: str | None = None  # sparkles / confetti / hearts / sweat / fish / alert
    milestone: MilestoneEvent | None = None
    meta: str = ""


class ReactionTracker:
    def __init__(self, rng: random.Random | None = None, *, cooldown_seconds: float = 90.0) -> None:
        self.rng = rng or random.Random()
        self.cooldown_seconds = cooldown_seconds
        self._last_running: bool | None = None
        self._last_conversation = ""
        self._last_form: str | None = None
        self._last_at: dict[str, float] = {}
        self._quota_band = 2  # 2 ok, 1 low, 0 critical
        self._last_quota_pct: float | None = None
        self._last_quota_group: str | None = None
        self._reset_soon_active = False
        self._was_waiting = False
        self._last_subagent_count = 0
        self._context_warned_for: set[str] = set()
        self._update_notified_for = ""
        self._last_ai_comment_id = ""
        self._seeded_milestone_conv = ""
        self._seen_milestone_ids: set[str] = set()
        self._seen_milestone_sigs: dict[str, tuple[str, float]] = {}
        self._was_offline = False
        self._last_cumulative_tokens: int | None = None
        self._turn_start_tokens: int | None = None
        self._overrides: dict[str, tuple[str, ...]] = {}
        self.lines: dict[str, tuple[str, ...]] = dict(LINES)

    def _default_lines_for_lang(self) -> dict[str, tuple[str, ...]]:
        code = get_language()
        if code != "zh":
            base = dict(LINES)
            base.update(REACTION_LINES.get(code, {}))
            return base
        return dict(LINES)

    def set_lines(self, overrides: dict | None) -> None:
        """Per-form voice; unknown kinds are ignored, missing kinds keep localized defaults."""
        parsed: dict[str, tuple[str, ...]] = {}
        for kind, lines in (overrides or {}).items():
            if kind in LINES and isinstance(lines, list) and lines:
                parsed[kind] = tuple(str(line) for line in lines)
        self._overrides = parsed
        merged = self._default_lines_for_lang()
        merged.update(parsed)
        self.lines = merged

    def reset_follow(self) -> None:
        """Forget the last followed form so re-enabling follow switches again."""
        self._last_form = None

    def _ready(self, kind: str, now: float, cooldown: float | None = None) -> bool:
        last = self._last_at.get(kind)
        if last is not None and now - last < (self.cooldown_seconds if cooldown is None else cooldown):
            return False
        self._last_at[kind] = now
        return True

    def _line(self, kind: str, **values: object) -> str:
        code = get_language()
        pool = self._overrides.get(kind)
        if not pool:
            if code != "zh":
                pool = REACTION_LINES.get(code, {}).get(kind)
            if not pool:
                pool = self.lines.get(kind) or LINES.get(kind)
        try:
            return self.rng.choice(pool).format(**values)
        except (KeyError, IndexError, ValueError, TypeError):
            fallback = REACTION_LINES.get(code, {}).get(kind) if code != "zh" else None
            return self.rng.choice(fallback or LINES[kind]).format(**values)

    def _effective_quota(self, snapshot: LiveSnapshot) -> tuple[float | None, str | None]:
        q5, reset5 = snapshot.quota_for("5h")
        if q5 is not None:
            return q5, reset5
        return snapshot.quota_remaining_pct, snapshot.quota_reset_time

    def _observe_milestone(self, snapshot: LiveSnapshot, *, now: float, enabled: bool) -> MilestoneEvent | None:
        cid = snapshot.conversation_id or ""
        ms = getattr(snapshot, "milestone", None)
        if not cid:
            return None
        if cid != self._seeded_milestone_conv:
            # Silent baseline on startup or switching conversations so stale history never pops.
            self._seeded_milestone_conv = cid
            if isinstance(ms, MilestoneEvent):
                if len(self._seen_milestone_ids) >= 256:
                    self._seen_milestone_ids.clear()
                self._seen_milestone_ids.add(ms.id)
                self._seen_milestone_sigs[cid] = (f"{ms.kind}|{ms.title}|{ms.body}", now)
            return None
        if not isinstance(ms, MilestoneEvent):
            return None
        if ms.id in self._seen_milestone_ids:
            return None
        if len(self._seen_milestone_ids) >= 256:
            self._seen_milestone_ids.clear()
        self._seen_milestone_ids.add(ms.id)
        sig = f"{ms.kind}|{ms.title}|{ms.body}"
        prev_sig, prev_ts = self._seen_milestone_sigs.get(cid, ("", -9999.0))
        if sig == prev_sig and now - prev_ts < 20.0:
            return None
        self._seen_milestone_sigs[cid] = (sig, now)
        return ms if enabled else None

    def observe(
        self,
        snapshot: LiveSnapshot | None,
        *,
        now: float,
        follow_model: bool,
        current_form: str,
        progress_bubbles: bool = True,
    ) -> list[Reaction]:
        reactions: list[Reaction] = []
        if snapshot is None:
            if not self._was_offline and self._last_running is not None and self._ready("offline", now, 600):
                reactions.append(Reaction("offline", self._line("offline")))
            self._was_offline = True
            return reactions
        self._was_offline = False

        if follow_model:
            target = form_for_model_label(snapshot.model_for_form)
            if target and target != current_form and target != self._last_form:
                reactions.append(
                    Reaction(
                        "form",
                        self._line("form", model=snapshot.model_for_form, form=target.capitalize()),
                        "HAPPY",
                        form=target,
                        particle="sparkles",
                    )
                )
            self._last_form = target or self._last_form

        new_milestone = self._observe_milestone(snapshot, now=now, enabled=progress_bubbles)

        cur_tokens = max(0, int(snapshot.cumulative_total_tokens or 0))
        same_conversation = snapshot.conversation_id == self._last_conversation
        if not same_conversation:
            self._turn_start_tokens = cur_tokens if snapshot.running else None
        elif self._last_running is not None:
            if snapshot.running and not self._last_running:
                baseline = (
                    min(self._last_cumulative_tokens, cur_tokens)
                    if self._last_cumulative_tokens is not None
                    else cur_tokens
                )
                self._turn_start_tokens = baseline
                if self._ready("started", now, 45):
                    reactions.append(Reaction("started", self._line("started"), "WORKING"))
            elif snapshot.running and self._last_running:
                if self._turn_start_tokens is None:
                    self._turn_start_tokens = cur_tokens
            elif not snapshot.running and self._last_running:
                baseline = self._turn_start_tokens
                self._turn_start_tokens = None
                if snapshot.termination_reason.upper() == "ERROR":
                    if self._ready("turn_error", now, 30):
                        reactions.append(Reaction("turn_error", self._line("turn_error"), "DIZZY", particle="sweat"))
                else:
                    turn_tokens = (
                        cur_tokens - baseline
                        if (baseline is not None and cur_tokens >= baseline)
                        else cur_tokens
                    )
                    rate = snapshot.avg_decode_tps or snapshot.display_rate or 0
                    if new_milestone is not None and new_milestone.kind in {"summary", "progress"}:
                        meta = (
                            tr("milestone.turn_meta", total=format_tokens(turn_tokens), rate=f"{rate:.0f}")
                            if (turn_tokens > 0 or baseline is None or cur_tokens == 0)
                            else ""
                        )
                        self._last_at["finished"] = now
                        reactions.append(
                            Reaction(
                                "milestone",
                                new_milestone.body or new_milestone.title,
                                "CELEBRATE",
                                particle="confetti",
                                milestone=new_milestone,
                                meta=meta,
                            )
                        )
                        new_milestone = None
                    elif (turn_tokens > 0 or baseline is None or cur_tokens == 0) and self._ready("finished", now, 30):
                        reactions.append(
                            Reaction(
                                "finished",
                                self._line("finished", total=format_tokens(turn_tokens), rate=f"{rate:.0f}"),
                                "CELEBRATE",
                                particle="confetti",
                            )
                        )
        self._last_running = snapshot.running
        self._last_conversation = snapshot.conversation_id
        self._last_cumulative_tokens = cur_tokens

        if new_milestone is not None:
            ms_action = (
                "CELEBRATE"
                if new_milestone.kind == "summary"
                else ("HAPPY" if new_milestone.kind == "step_done" else None)
            )
            ms_particle = "confetti" if new_milestone.kind == "summary" else "sparkles"
            reactions.append(
                Reaction(
                    "milestone",
                    new_milestone.body or new_milestone.title,
                    ms_action,
                    particle=ms_particle,
                    milestone=new_milestone,
                )
            )

        # Waiting for user confirmation / answer (e.g. approval prompt or ask_question)
        if snapshot.waiting_for_user and not self._was_waiting and self._ready("waiting", now, 60):
            reactions.append(Reaction("waiting", self._line("waiting"), "WAITING_USER", particle="alert"))
        self._was_waiting = bool(snapshot.waiting_for_user)

        # Active subagent clones
        sub_count = len(snapshot.active_subagents)
        if sub_count >= 2 and self._last_subagent_count < 2:
            if self._ready("subagent_many", now, 180):
                reactions.append(
                    Reaction("subagent_many", self._line("subagent_many", count=sub_count), "CELEBRATE", particle="sparkles")
                )
        elif sub_count >= 1 and self._last_subagent_count == 0:
            if self._ready("subagent_start", now, 120):
                reactions.append(Reaction("subagent_start", self._line("subagent_start"), "HAPPY", particle="sparkles"))
        self._last_subagent_count = sub_count

        rate = snapshot.latest_decode_tps or 0
        if snapshot.running and rate >= 180 and self._ready("fast", now, 300):
            reactions.append(Reaction("fast", self._line("fast", rate=f"{rate:.0f}"), "HAPPY", particle="sparkles"))

        quota, quota_reset = self._effective_quota(snapshot)
        if quota is not None:
            model_lower = (snapshot.model_for_form or "").lower()
            quota_group = (
                "third_party"
                if any(w in model_lower for w in ("claude", "gpt", "oss", "opus", "sonnet"))
                else ("gemini" if model_lower else "")
            )
            switched_group = (
                self._last_quota_group is not None
                and quota_group != ""
                and self._last_quota_group != ""
                and quota_group != self._last_quota_group
            )
            band = 0 if quota <= 10 else 1 if quota <= 25 else 2
            now_ms = int(time.time() * 1000)
            if switched_group:
                # Model quota group switched (e.g. Gemini <-> Claude): re-baseline without fake refill/alert spam.
                self._last_quota_pct = quota
                self._quota_band = band
            elif band < self._quota_band:
                reset = format_reset_countdown(quota_reset, now_ms=now_ms) or "等待重置"
                kind = "quota_critical" if band == 0 else "quota_low"
                if self._ready(kind, now, 300):
                    reactions.append(
                        Reaction(
                            kind,
                            self._line(kind, quota=f"{quota:.0f}", reset=reset),
                            "TIRED" if band == 0 else None,
                            particle="sweat" if band == 0 else None,
                        )
                    )
            elif (
                self._last_quota_pct is not None
                and quota - self._last_quota_pct >= 12.0
                and self._ready("quota_refilled", now, 1800)
            ):
                reactions.append(
                    Reaction(
                        "quota_refilled",
                        self._line("quota_refilled", quota=f"{quota:.0f}"),
                        "QUOTA_GIFT",
                        particle="fish",
                    )
                )

            reset_ms = parse_iso_ms(quota_reset)
            remaining_reset_ms = (reset_ms - now_ms) if reset_ms else None
            reset_soon = remaining_reset_ms is not None and 0 < remaining_reset_ms <= 20 * 60_000 and quota <= 50.0
            if reset_soon and not self._reset_soon_active and self._ready("quota_reset_soon", now, 1800):
                countdown = format_reset_countdown(quota_reset, now_ms=now_ms) or "不到 20 分钟后重置"
                reactions.append(
                    Reaction(
                        "quota_reset_soon",
                        self._line("quota_reset_soon", reset=countdown),
                        "HAPPY",
                        particle="sparkles",
                    )
                )
            self._reset_soon_active = reset_soon
            self._quota_band = band
            self._last_quota_pct = quota
            if quota_group:
                self._last_quota_group = quota_group

        ctx = snapshot.context_pct
        ctx_key = snapshot.conversation_id or "__default__"
        if ctx >= 80 and ctx_key not in self._context_warned_for:
            if len(self._context_warned_for) >= 64:
                self._context_warned_for.clear()
            self._context_warned_for.add(ctx_key)
            reactions.append(
                Reaction("context_high", self._line("context_high", ctx=f"{ctx:.0f}"), "WORK_COMPACTING", particle="sweat")
            )

        latest_ver = str(getattr(snapshot, "available_update_version", "") or "").strip()
        latest_sha = str(getattr(snapshot, "available_update_sha", "") or "").strip()
        update_token = latest_ver or latest_sha
        if update_token and update_token != self._update_notified_for:
            self._update_notified_for = update_token
            if latest_ver:
                reactions.append(Reaction("update", self._line("update", version=latest_ver), "WAVE", particle="sparkles"))
            else:
                reactions.append(Reaction("update", self._line("update_commit", sha=latest_sha[:7]), "WAVE", particle="sparkles"))

        ai_id = str(getattr(snapshot, "ai_comment_id", "") or "").strip()
        ai_text = str(getattr(snapshot, "ai_comment_text", "") or "").strip()
        if ai_id and ai_text and ai_id != self._last_ai_comment_id:
            self._last_ai_comment_id = ai_id
            reactions.append(Reaction("ai_comment", ai_text, None, particle="sparkles"))
        return reactions
