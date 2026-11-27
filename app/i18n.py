"""Centralized internationalization (zh / en / ja) for Antigravity Pet."""

from __future__ import annotations

import locale
import os
from typing import Any, TypeVar

SUPPORTED_LANGUAGES: tuple[str, ...] = ("zh", "en", "ja")
LANGUAGE_SETTINGS: tuple[str, ...] = ("auto", "zh", "en", "ja")

_language_setting: str = "auto"
_active_language: str | None = None

T = TypeVar("T")


def normalize_language_setting(value: object) -> str:
    """Normalize a user config value into ``'auto' | 'zh' | 'en' | 'ja'``."""
    raw = str(value or "").strip().lower().replace("_", "-")
    if not raw or raw == "auto" or raw == "system":
        return "auto"
    if raw.startswith(("ja", "jp", "japanese")):
        return "ja"
    if raw.startswith(("en", "english")):
        return "en"
    if raw.startswith(("zh", "chinese", "chs", "cht")):
        return "zh"
    return "auto"


def _locale_tag_to_lang(tag: object) -> str | None:
    raw = str(tag or "").strip().lower().replace("_", "-")
    if not raw or raw in {"c", "posix"}:
        return None
    if raw.startswith(("ja", "jp", "japanese")):
        return "ja"
    if raw.startswith(("zh", "chinese", "chs", "cht")):
        return "zh"
    if raw.startswith(("en", "english")):
        return "en"
    return "en"


def detect_system_language() -> str:
    """Detect the OS / environment UI language, resolving to ``'zh' | 'en' | 'ja'``."""
    env_override = os.environ.get("AGY_PET_LANG", "").strip()
    if env_override and env_override.lower() != "auto":
        mapped = _locale_tag_to_lang(env_override)
        if mapped:
            return mapped

    try:
        from PySide6.QtCore import QLocale

        qt_name = QLocale.system().name()
        mapped = _locale_tag_to_lang(qt_name)
        if mapped:
            return mapped
    except Exception:
        pass

    try:
        loc = locale.getlocale()[0]
        mapped = _locale_tag_to_lang(loc)
        if mapped:
            return mapped
    except Exception:
        pass

    for env_key in ("LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(env_key, "").split(".", 1)[0]
        mapped = _locale_tag_to_lang(val)
        if mapped:
            return mapped

    return "zh"


def resolve_language(setting: object = None) -> str:
    """Resolve ``setting`` (or the current configured setting) to ``'zh' | 'en' | 'ja'``."""
    norm = normalize_language_setting(_language_setting if setting is None else setting)
    if norm == "auto":
        return detect_system_language()
    return norm


def set_language(setting: object) -> str:
    """Set the active language preference and return the resolved language code."""
    global _language_setting, _active_language
    _language_setting = normalize_language_setting(setting)
    _active_language = resolve_language(_language_setting)
    return _active_language


def get_language_setting() -> str:
    return _language_setting


def get_language() -> str:
    global _active_language
    if _active_language is None:
        _active_language = resolve_language(_language_setting)
    return _active_language


def pick_lang(table: dict[str, T], *, lang: str | None = None) -> T:
    code = resolve_language(lang) if lang is not None else get_language()
    if code in table:
        return table[code]
    return table["zh"]


def tr(key: str, *, lang: str | None = None, **kwargs: Any) -> str:
    """Look up a localized UI string by key, falling back cleanly to Chinese."""
    code = resolve_language(lang) if lang is not None else get_language()
    entry = STRINGS.get(key)
    if entry is None:
        return key
    template = entry.get(code) or entry.get("zh") or key
    if not kwargs:
        return template
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return template


def format_tokens_localized(value: float, *, lang: str | None = None) -> str:
    """Format large token counts according to active locale (zh: 万/亿, ja: 万/億, en: K/M/B)."""
    code = resolve_language(lang) if lang is not None else get_language()
    num = float(value)
    if code == "en":
        for unit, size in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
            if abs(num) >= size:
                scaled = num / size
                return f"{scaled:.0f}{unit}" if scaled >= 100 else f"{scaled:.1f}{unit}".replace(".0" + unit, unit)
        return f"{num:.0f}"
    units = (("億", 1e8), ("万", 1e4)) if code == "ja" else (("亿", 1e8), ("万", 1e4))
    for unit, size in units:
        if abs(num) >= size:
            scaled = num / size
            return f"{scaled:.0f}{unit}" if scaled >= 100 else f"{scaled:.1f}{unit}".replace(".0" + unit, unit)
    return f"{num:.0f}"


def format_duration_localized(ms: int, *, lang: str | None = None) -> str:
    code = resolve_language(lang) if lang is not None else get_language()
    minutes = int(ms // 60000)
    hours, minutes = divmod(minutes, 60)
    if code == "en":
        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes} min" if minutes else "< 1 min"
    if code == "ja":
        if hours:
            return f"{hours}時間{minutes}分"
        return f"{minutes}分" if minutes else "1分未満"
    if hours:
        return f"{hours} 小时 {minutes} 分"
    return f"{minutes} 分钟" if minutes else "不到 1 分钟"


def format_month_label(year: int, month: int, *, lang: str | None = None) -> str:
    code = resolve_language(lang) if lang is not None else get_language()
    if code == "en":
        names = (
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        )
        return f"{names[max(1, min(12, month)) - 1]} {year}"
    if code == "ja":
        return f"{year}年{month}月"
    return f"{year} 年 {month} 月"


def format_short_month(month: int, *, lang: str | None = None) -> str:
    code = resolve_language(lang) if lang is not None else get_language()
    if code == "en":
        names = (
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        )
        return names[max(1, min(12, month)) - 1]
    return f"{month}月"


def weekday_labels(*, lang: str | None = None) -> tuple[str, ...]:
    code = resolve_language(lang) if lang is not None else get_language()
    if code == "en":
        return ("M", "T", "W", "T", "F", "S", "S")
    if code == "ja":
        return ("月", "火", "水", "木", "金", "土", "日")
    return ("一", "二", "三", "四", "五", "六", "日")


# ---------------------------------------------------------------------------
# Master UI translation catalog (zh / en / ja)
# ---------------------------------------------------------------------------

STRINGS: dict[str, dict[str, str]] = {
    # --- Language names ---
    "lang.label": {"zh": "语言", "en": "Lang", "ja": "言語"},
    "lang.auto": {"zh": "自动", "en": "Auto", "ja": "自動"},
    "lang.zh": {"zh": "中文", "en": "中文", "ja": "中文"},
    "lang.en": {"zh": "EN", "en": "EN", "ja": "EN"},
    "lang.ja": {"zh": "日本語", "en": "日本語", "ja": "日本語"},

    # --- Character taglines ---
    "char.tagline.carbon": {"zh": "稳重的碳基搭档", "en": "Calm carbon-based partner", "ja": "クールな炭素パートナー"},
    "char.tagline.hydergon": {"zh": "轻快的氢形态", "en": "Breezy hydrogen spirit", "ja": "軽やかな水素フォーム"},
    "char.tagline.neon": {"zh": "闪亮的霓虹形态", "en": "Radiant neon idol", "ja": "きらめくネオンアイドル"},
    "char.tagline.argon": {"zh": "慢悠悠的氩猫", "en": "Sleepy noble-gas kitty", "ja": "のんびりアルゴン猫"},
    "char.tagline.claude": {"zh": "认真优雅的 Claude", "en": "Composed & thoughtful Claude", "ja": "丁寧で優雅な Claude"},

    # --- Personalities ---
    "personality.standard": {"zh": "标准小A", "en": "Standard", "ja": "標準"},
    "personality.sharp": {"zh": "轻微毒舌", "en": "Snarky", "ja": "ちょい毒舌"},
    "personality.gentle": {"zh": "温和陪伴", "en": "Gentle", "ja": "やさしい"},
    "personality.community": {"zh": "社区梗", "en": "Dev Memes", "ja": "ネットミーム"},

    # --- Control Panel ---
    "panel.default_title": {"zh": "小A", "en": "AGY", "ja": "AGY"},
    "panel.close": {"zh": "关闭", "en": "Close", "ja": "閉じる"},
    "panel.feed": {"zh": "投喂", "en": "Feed", "ja": "おやつ"},
    "panel.say": {"zh": "说话", "en": "Chat", "ja": "おしゃべり"},
    "panel.playmates": {"zh": "唤玩伴", "en": "Clones", "ja": "分身召喚"},
    "panel.rest": {"zh": "休息", "en": "Nap", "ja": "休憩"},
    "panel.dock": {"zh": "贴边", "en": "Dock", "ja": "端隠れ"},
    "panel.dock_tip": {
        "zh": "贴到屏幕边缘藏身 / 取消贴边",
        "en": "Peek from screen edge / undock",
        "ja": "画面端に隠れる／解除",
    },
    "panel.climb": {"zh": "爬窗", "en": "Climb", "ja": "窓登り"},
    "panel.climb_tip": {
        "zh": "爬到附近窗口顶部",
        "en": "Climb onto a nearby window top",
        "ja": "近くのウィンドウ上端へ登る",
    },
    "panel.perch": {"zh": "坐沿", "en": "Perch", "ja": "窓座り"},
    "panel.perch_tip": {
        "zh": "坐在附近窗口顶部边缘",
        "en": "Perch on a nearby window edge",
        "ja": "近くのウィンドウの縁に座る",
    },
    "panel.recall": {"zh": "召回主屏", "en": "Recall", "ja": "メイン画面へ"},
    "panel.recall_tip": {
        "zh": "取消贴边并召回到主屏幕",
        "en": "Undock and recall to primary display",
        "ja": "端隠れを解除してメイン画面に戻す",
    },
    "panel.scene.tea_party": {"zh": "茶会", "en": "Tea", "ja": "お茶会"},
    "panel.scene.tea_party_tip": {
        "zh": "🫖 摆开奶油下午茶会（左键茶桌续杯，右键收起）",
        "en": "🫖 Afternoon Tea Party (left-click table to refill, right-click to dismiss)",
        "ja": "🫖 アフタヌーンティー会（左クリックでおかわり・右クリックで片付け）",
    },
    "panel.scene.campfire_night": {"zh": "篝火", "en": "Camp", "ja": "焚き火"},
    "panel.scene.campfire_night_tip": {
        "zh": "🏕️ 升起暖光小篝火烤棉花糖（左键添柴，右键熄火）",
        "en": "🏕️ Campfire Night with marshmallows (left-click to stoke, right-click to put out)",
        "ja": "🏕️ 焚き火ナイトでマシュマロ焼き（左クリックで薪追加・右クリックで消火）",
    },
    "panel.scene.art_studio": {"zh": "画室", "en": "Art", "ja": "画室"},
    "panel.scene.art_studio_tip": {
        "zh": "🎨 支起小画架给姐姐画肖像（左键换新作，右键收起）",
        "en": "🎨 Mini Art Studio portrait session (left-click easel for new art, right-click to close)",
        "ja": "🎨 ミニアトリエでお姉さまの肖像画（左クリックで新作・右クリックで片付け）",
    },
    "panel.scene.cloud_nap": {"zh": "午睡", "en": "Cloud", "ja": "お昼寝"},
    "panel.scene.cloud_nap_tip": {
        "zh": "☁️ 铺开云朵午睡窝一起打盹（左键盖小被，右键收起）",
        "en": "☁️ Fluffy Cloud Nap nest (left-click to tuck starry blanket, right-click to wake)",
        "ja": "☁️ ふわふわ雲のお昼寝（左クリックで星柄毛布・右クリックで起床）",
    },
    "scene.click_hint": {"zh": "点我互动", "en": "Click me!", "ja": "クリックで遊ぶ"},
    "panel.mode": {"zh": "移动", "en": "Move", "ja": "移動"},
    "panel.mode.wander": {"zh": "散步", "en": "Wander", "ja": "散歩"},
    "panel.mode.follow": {"zh": "跟随", "en": "Follow", "ja": "追従"},
    "panel.mode.still": {"zh": "静止", "en": "Still", "ja": "静止"},
    "panel.form": {"zh": "形态", "en": "Form", "ja": "フォーム"},
    "panel.follow_model": {"zh": "跟随模型", "en": "Auto Form", "ja": "モデル連動"},
    "panel.follow_model_tip": {
        "zh": "根据 Antigravity 当前使用的模型（Carbon / Hydrogen / Neon / Argon / Claude）自动切换形态",
        "en": "Automatically switch form to match the active Antigravity model",
        "ja": "Antigravity で使用中のモデルに合わせてフォームを自動切替",
    },
    "panel.hud": {"zh": "HUD 条", "en": "HUD Bar", "ja": "HUDバー"},
    "panel.hud_tip": {
        "zh": "显示 tok/s · 限额 · 缓存 · 上下文 迷你悬浮条",
        "en": "Show live tok/s, quota, cache & context floating bar",
        "ja": "tok/s・クォータ・キャッシュ・コンテキストのミニ HUD を表示",
    },
    "panel.autonomy": {"zh": "自主行为", "en": "Autonomy", "ja": "自律行動"},
    "panel.autonomy_tip": {
        "zh": "模型干活时陪着干活、跳上 Antigravity 窗口、闲久了打盹、限额低会犯困、久坐提醒",
        "en": "Work alongside runs, hop onto windows, nap when idle, yawn on low quota, stretch nudges",
        "ja": "生成中に並走・ウィンドウに飛び乗り・放置でお昼寝・低残量であくび・休憩リマインド",
    },
    "panel.hud_hover_only": {"zh": "悬停HUD", "en": "Hover HUD", "ja": "ホバーHUD"},
    "panel.hud_hover_only_tip": {
        "zh": "平时隐藏 HUD 卡片还桌面清爽，鼠标悬停在桌宠身上时再弹出",
        "en": "Keep desktop clean and reveal HUD only when hovering over the pet",
        "ja": "普段は HUD を隠し、ペットにカーソルを合わせた時だけ表示",
    },
    "panel.open_meter": {"zh": "Token Meter 面板", "en": "Token Meter", "ja": "Token Meter パネル"},
    "panel.more": {"zh": "更多设置", "en": "More", "ja": "詳細設定"},
    "panel.less": {"zh": "收起设置", "en": "Less", "ja": "設定を閉じる"},
    "panel.hide": {"zh": "隐藏", "en": "Hide", "ja": "隠す"},
    "panel.size": {"zh": "大小", "en": "Size", "ja": "大きさ"},
    "panel.size.small": {"zh": "小", "en": "S", "ja": "小"},
    "panel.size.medium": {"zh": "中", "en": "M", "ja": "中"},
    "panel.size.large": {"zh": "大", "en": "L", "ja": "大"},
    "panel.action": {"zh": "动作", "en": "Pose", "ja": "動作"},
    "panel.action.think": {"zh": "发呆", "en": "Daydream", "ja": "ぼーっと"},
    "panel.action.sweep": {"zh": "扫地", "en": "Sweep", "ja": "お掃除"},
    "panel.rhythm": {"zh": "节奏", "en": "Pace", "ja": "テンポ"},
    "panel.rhythm_tip": {"zh": "陪伴节奏", "en": "Companion activity cadence", "ja": "お供アクションの頻度"},
    "panel.rhythm.calm": {"zh": "安静", "en": "Calm", "ja": "静か"},
    "panel.rhythm.balanced": {"zh": "适中", "en": "Normal", "ja": "ふつう"},
    "panel.rhythm.lively": {"zh": "活泼", "en": "Lively", "ja": "活発"},
    "panel.speed": {"zh": "步速", "en": "Speed", "ja": "歩速"},
    "panel.speed_tip": {"zh": "走路速度", "en": "Walking speed", "ja": "歩くスピード"},
    "panel.speed.slow": {"zh": "慢", "en": "Slow", "ja": "遅い"},
    "panel.speed.normal": {"zh": "适中", "en": "Med", "ja": "普通"},
    "panel.speed.fast": {"zh": "快", "en": "Fast", "ja": "速い"},
    "panel.awareness": {"zh": "本地感知", "en": "Awareness", "ja": "画面認識"},
    "panel.topmost": {"zh": "窗口置顶", "en": "On Top", "ja": "最前面表示"},
    "panel.read_window_title": {"zh": "读取标题", "en": "Read Title", "ja": "タイトル読取"},
    "panel.fullscreen_hide": {"zh": "全屏隐藏", "en": "Hide Full", "ja": "全画面時隠す"},
    "panel.idle_detection": {"zh": "检测空闲", "en": "Idle Detect", "ja": "放置検知"},
    "panel.passthrough": {"zh": "鼠标穿透", "en": "Click-Thru", "ja": "透過クリック"},
    "panel.autostart": {"zh": "开机自启", "en": "Autostart", "ja": "自動起動"},
    "panel.reduced_motion": {"zh": "减少动态", "en": "Low Motion", "ja": "動きを抑える"},
    "panel.follow_cursor": {"zh": "目光跟随", "en": "Eye Track", "ja": "目線追従"},
    "panel.hover_pause": {"zh": "悬停暂停", "en": "Hover Pause", "ja": "ホバー停止"},
    "panel.desktop_surfaces": {"zh": "窗口落脚", "en": "Win Perch", "ja": "窓上着地"},
    "panel.snap": {"zh": "回到屏幕内", "en": "Center", "ja": "画面内へ"},
    "panel.privacy": {"zh": "隐私", "en": "Privacy", "ja": "プライバシー"},
    "panel.quit": {"zh": "退出", "en": "Quit", "ja": "終了"},

    # --- Pet States ---
    "state.idle": {"zh": "待机", "en": "Idle", "ja": "待機"},
    "state.walk": {"zh": "散步", "en": "Walk", "ja": "散歩"},
    "state.sleep": {"zh": "休息", "en": "Nap", "ja": "お昼寝"},
    "state.eat": {"zh": "吃东西", "en": "Eating", "ja": "もぐもぐ"},
    "state.happy": {"zh": "开心", "en": "Happy", "ja": "ごきげん"},
    "state.drag": {"zh": "被拎起", "en": "Carried", "ja": "もちあげ中"},
    "state.fall": {"zh": "下落", "en": "Falling", "ja": "落下中"},
    "state.climb": {"zh": "爬窗口", "en": "Climbing", "ja": "窓登り中"},
    "state.perch": {"zh": "坐窗沿", "en": "Perched", "ja": "窓に腰掛け"},
    "state.dock": {"zh": "贴边藏身", "en": "Peeking", "ja": "端からひょっこり"},
    "state.work": {"zh": "陪你干活", "en": "Working", "ja": "お供作業中"},
    "state.dizzy": {"zh": "头晕", "en": "Dizzy", "ja": "くらくら"},
    "state.sulk": {"zh": "闹脾气", "en": "Sulking", "ja": "すね中"},
    "state.purr": {"zh": "呼噜", "en": "Purring", "ja": "ごろごろ"},
    "state.think": {"zh": "发呆", "en": "Thinking", "ja": "考え中"},
    "state.sweep": {"zh": "扫地", "en": "Sweeping", "ja": "お掃除中"},
    "state.tired": {"zh": "犯困", "en": "Sleepy", "ja": "ねむい"},

    # --- Tray Menu & Window ---
    "tray.tooltip": {"zh": "AGY 桌宠 · {name}", "en": "AGY Pet · {name}", "ja": "AGY ペット · {name}"},
    "tray.toggle_visible": {"zh": "显示/隐藏", "en": "Show / Hide", "ja": "表示／非表示"},
    "tray.open_panel": {"zh": "打开快速控制", "en": "Open Quick Panel", "ja": "クイック操作を開く"},
    "tray.recall_primary": {"zh": "取消贴边 / 召回主屏", "en": "Undock / Recall to Primary", "ja": "端隠れ解除／メイン画面へ"},
    "tray.switch_form": {"zh": "切换形态", "en": "Switch Form", "ja": "フォーム切替"},
    "tray.follow_model": {"zh": "跟随 Antigravity 当前模型", "en": "Follow Active Antigravity Model", "ja": "Antigravity のモデルに連動"},
    "tray.language": {"zh": "语言 / Language", "en": "Language / 言語", "ja": "言語 / Language"},
    "tray.open_meter": {"zh": "Token Meter 面板", "en": "Token Meter Dashboard", "ja": "Token Meter パネル"},
    "tray.toggle_hud": {"zh": "显示 / 隐藏 HUD 悬浮条", "en": "Show / Hide HUD Bar", "ja": "HUDバーを表示／非表示"},
    "tray.quit": {"zh": "退出", "en": "Quit", "ja": "終了"},

    # --- Food Panel ---
    "food.close": {"zh": "关闭", "en": "Close", "ja": "閉じる"},
    "food.fallback.0": {"zh": "小鱼", "en": "Fish", "ja": "小魚"},
    "food.fallback.1": {"zh": "虾", "en": "Shrimp", "ja": "えび"},
    "food.fallback.2": {"zh": "贝", "en": "Clam", "ja": "貝"},
    "food.fallback.3": {"zh": "海藻", "en": "Kelp", "ja": "海藻"},
    "food.fallback.4": {"zh": "点心", "en": "Treat", "ja": "おやつ"},

    # --- Pet Window Direct Bubbles & Dialogs ---
    "pet.head_rub_forgive": {"zh": "哼……摸头就算原谅你啦～", "en": "Hmph... head pats mean you're forgiven~", "ja": "ふんっ……頭なでてくれたから許してあげる〜"},
    "pet.sulk_poke": {"zh": "别一直戳我啦，哼！", "en": "Hey, stop poking me! Hmph!", "ja": "もう、つつきすぎだよっ、ぷん！"},
    "pet.full_feed": {"zh": "吃饱了，先让我消化一下～", "en": "I'm full! Let me digest a bit~", "ja": "おなかいっぱい〜ちょっと休憩させてね！"},
    "pet.dislike_food": {"zh": "唔…这个我不太爱吃……", "en": "Mmm... not really my favorite...", "ja": "うぅ…それはちょっと苦手かも……"},
    "pet.favorite_food": {"zh": "最喜欢这个啦！超开心～", "en": "My absolute favorite! So happy~", "ja": "これ大好き！すっごくうれしい〜！"},
    "pet.normal_food": {"zh": "真好吃，谢谢投喂～", "en": "Yummy, thanks for the snack~", "ja": "おいしい！ごちそうさま〜"},
    "pet.recall_bubble": {"zh": "回来主屏啦，随时待命～", "en": "Back on the main screen and ready!", "ja": "メイン画面に戻ったよ、いつでもOK〜！"},
    "pet.dock_peek": {"zh": "偷偷探头看看你在写什么～", "en": "Peeking out to see what you're coding~", "ja": "何書いてるのかひょっこり覗き見〜"},
    "pet.no_window_climb": {"zh": "附近没有合适高度的窗口可以爬哦～", "en": "No reachable window nearby to climb right now~", "ja": "近くに登れそうなウィンドウがないみたい〜"},
    "pet.no_window_perch": {"zh": "附近没有可坐的窗口边缘哦～", "en": "No nearby window edge to perch on~", "ja": "近くに腰掛けられるウィンドウがないよ〜"},
    "pet.safe_mode_notice": {
        "zh": "检测到上次异常退出，已临时用安全配置启动。",
        "en": "Recovered from an unexpected exit; started in safe mode.",
        "ja": "前回の異常終了を検知したため、セーフモードで起動しました。",
    },
    "pet.privacy_title": {"zh": "隐私规则", "en": "Privacy Rules", "ja": "プライバシールール"},
    "pet.privacy_body": {
        "zh": "AGY 桌宠所有感知与遥测均只在本地运行，绝不上传窗口标题、代码或凭据。\n\n可在配置文件 privacy.custom_process_names 中追加需要忽略的进程名（如密码管理器或银行软件）。",
        "en": "All awareness and telemetry run 100% locally. Window titles, code, and credentials are never uploaded.\n\nYou can add process names to ignore (e.g. password managers) under privacy.custom_process_names in config.json.",
        "ja": "AGY ペットの画面認識とテレメトリはすべてローカル完結で、ウィンドウ名・コード・認証情報は一切外部送信されません。\n\n無視したいプロセス名（パスワード管理ツールなど）は config.json の privacy.custom_process_names に追加できます。",
    },
    "pet.twin_tag": {"zh": "{name}双胞胎", "en": "{name} twins", "ja": "{name}の双子"},
    "pet.triplet_tag": {"zh": "{name}三胞胎", "en": "{name} triplets", "ja": "{name}の三つ子"},
    "pet.multi_tag": {"zh": "{name}×{count}", "en": "{name}×{count}", "ja": "{name}×{count}"},
    "pet.name_join": {"zh": "、", "en": ", ", "ja": "・"},

    # --- HUD Bar ---
    "hud.appearance.dialog": {
        "zh": "对话框（指向桌宠的漫画卡片）",
        "en": "Speech Card (points to pet)",
        "ja": "吹き出しカード（ペット向き）",
    },
    "hud.appearance.capsule": {
        "zh": "暗紫星夜胶囊",
        "en": "Starry Night Capsule",
        "ja": "星夜ダークカプセル",
    },
    "hud.appearance.seamless": {
        "zh": "无边框融合（透明底）",
        "en": "Borderless Transparent",
        "ja": "枠なしシームレス（透過）",
    },
    "hud.appearance.glass": {
        "zh": "轻透紫雾毛玻璃",
        "en": "Frosted Mist Glass",
        "ja": "すりガラス風",
    },
    "hud.source.ls": {"zh": "语言服务实时", "en": "Language Server Live", "ja": "言語サーバー（リアルタイム）"},
    "hud.source.pet_live": {"zh": "AGY 桌宠插件实时", "en": "AGY Pet Plugin Live", "ja": "AGY ペット連携（リアルタイム）"},
    "hud.source.hud_live": {"zh": "Token Meter 侧边栏", "en": "Token Meter Sidecar", "ja": "Token Meter サイドカー"},
    "hud.source.transcript": {"zh": "本地会话日志（离线）", "en": "Local Transcripts (Offline)", "ja": "ローカルログ（オフライン）"},
    "hud.cap.week": {"zh": "周", "en": "Wk", "ja": "週"},
    "hud.cap.cache": {"zh": "缓存", "en": "Cache", "ja": "キャッシュ"},
    "hud.cap.context": {"zh": "上下文", "en": "Ctx", "ja": "文脈"},
    "hud.card.speed": {"zh": "⚡ 速率", "en": "⚡ Speed", "ja": "⚡ 速度"},
    "hud.card.cache": {"zh": "🎯 缓存", "en": "🎯 Cache", "ja": "🎯 ｷｬｯｼｭ"},
    "hud.card.context": {"zh": "🧠 上下文", "en": "🧠 Context", "ja": "🧠 文脈"},
    "hud.card.quota_5h": {"zh": "🔋 5h 限额", "en": "🔋 5h Quota", "ja": "🔋 5h枠"},
    "hud.card.quota_week": {"zh": "📅 周限额", "en": "📅 Weekly", "ja": "📅 週枠"},
    "hud.loading": {"zh": "正在读取 Antigravity 实时遥测数据…", "en": "Reading live Antigravity telemetry…", "ja": "Antigravity テレメトリを読込中…"},
    "hud.waiting": {"zh": "等待 Antigravity 会话…", "en": "Waiting for Antigravity…", "ja": "Antigravity セッション待機中…"},
    "hud.not_running": {"zh": "Antigravity 没有在运行", "en": "Antigravity is not running", "ja": "Antigravity は未起動です"},
    "hud.waiting_tip": {
        "zh": "等待连接 Antigravity 会话数据…\n右键可切换模式或退出",
        "en": "Waiting for Antigravity session data…\nRight-click to switch mode or hide",
        "ja": "Antigravity セッション接続待ち…\n右クリックでモード切替や非表示",
    },
    "hud.quota_5h_name": {"zh": "5 小时", "en": "5h", "ja": "5時間"},
    "hud.quota_week_name": {"zh": "每周", "en": "Weekly", "ja": "週間"},
    "hud.mode.pinned": {"zh": "[已锁定会话]", "en": "[Pinned]", "ja": "[セッション固定中]"},
    "hud.mode.auto": {"zh": "[自动跟随当前对话]", "en": "[Auto-follow active]", "ja": "[アクティブ自動追従]"},
    "hud.tip.session": {"zh": "会话: {title} {mode}", "en": "Session: {title} {mode}", "ja": "セッション: {title} {mode}"},
    "hud.tip.model": {
        "zh": "当前模型: {selected}   最近一步: {last}",
        "en": "Model: {selected}   Last step: {last}",
        "ja": "モデル: {selected}   直近ステップ: {last}",
    },
    "hud.tip.speed": {
        "zh": "⚡ 生成速率: 最新 {latest} | 会话均值 {avg} | 端到端 {e2e} | TTFT {ttft}",
        "en": "⚡ Speed: Latest {latest} | Avg {avg} | E2E {e2e} | TTFT {ttft}",
        "ja": "⚡ 生成速度: 最新 {latest} | 平均 {avg} | E2E {e2e} | TTFT {ttft}",
    },
    "hud.tip.quota": {"zh": "🔋 限额剩余: {detail}", "en": "🔋 Quota left: {detail}", "ja": "🔋 残クォータ: {detail}"},
    "hud.tip.cache": {"zh": "🎯 缓存命中: 累计 {pct:.1f}%", "en": "🎯 Cache hit: {pct:.1f}%", "ja": "🎯 キャッシュ率: {pct:.1f}%"},
    "hud.tip.context": {
        "zh": "🧠 上下文占用: {used:,} / {limit:,} tokens ({pct:.2f}%)",
        "en": "🧠 Context: {used:,} / {limit:,} tokens ({pct:.2f}%)",
        "ja": "🧠 コンテキスト: {used:,} / {limit:,} tokens ({pct:.2f}%)",
    },
    "hud.tip.total": {
        "zh": "📊 会话累计总消耗: {total} tokens",
        "en": "📊 Session total: {total} tokens",
        "ja": "📊 セッション累計: {total} tokens",
    },
    "hud.tip.source": {"zh": "数据来源: {source}", "en": "Source: {source}", "ja": "データ元: {source}"},
    "hud.tip.footer": {
        "zh": "双击打开 Token Meter · 右键打开设置菜单",
        "en": "Double-click for Token Meter · Right-click for menu",
        "ja": "ダブルクリックで Token Meter · 右クリックで設定",
    },
    "hud.cur_session": {"zh": "当前会话", "en": "Current Session", "ja": "現在のセッション"},
    "hud.running_prefix": {"zh": "生成中 · ", "en": "Running · ", "ja": "生成中 · "},
    "hud.pinned_tag": {"zh": "（已锁定）", "en": "(Pinned)", "ja": "（固定）"},
    "hud.unknown_model": {"zh": "未知模型", "en": "Unknown model", "ja": "不明なモデル"},
    "hud.no_data": {"zh": "暂无数据", "en": "No data", "ja": "データなし"},
    "hud.menu.attached": {"zh": "跟随桌宠", "en": "Attach to Pet", "ja": "ペットに追従"},
    "hud.menu.floating": {
        "zh": "独立悬浮（可拖到输入框旁）",
        "en": "Floating (drag anywhere)",
        "ja": "独立フロート（自由に移動）",
    },
    "hud.menu.hover_only": {
        "zh": "悬停桌宠时显示（平时隐藏）",
        "en": "Show on Pet Hover Only",
        "ja": "ペットにホバー時のみ表示",
    },
    "hud.menu.auto_follow": {
        "zh": "自动跟随最新活跃对话",
        "en": "Auto-follow Active Session",
        "ja": "最新セッションを自動追従",
    },
    "hud.menu.pin_session": {"zh": "指定监控某个会话", "en": "Pin Session", "ja": "監視セッションを指定"},
    "hud.menu.appearance": {"zh": "外观融合模式", "en": "Appearance", "ja": "外観スタイル"},
    "hud.menu.lock_pos": {
        "zh": "锁定当前坐标（防误拖动）",
        "en": "Lock Position",
        "ja": "位置をロック（誤操作防止）",
    },
    "hud.menu.open_meter": {"zh": "打开 Token Meter", "en": "Open Token Meter", "ja": "Token Meter を開く"},
    "hud.menu.refresh": {"zh": "立即刷新数据", "en": "Refresh Now", "ja": "今すぐ更新"},
    "hud.menu.hide": {"zh": "隐藏悬浮条", "en": "Hide HUD Bar", "ja": "HUDバーを隠す"},

    # --- Telemetry countdown ---
    "reset.soon": {"zh": "即将重置", "en": "resets soon", "ja": "まもなくリセット"},
    "reset.hm": {"zh": "{h}h {m}m 后重置 ({clock})", "en": "resets in {h}h {m}m ({clock})", "ja": "{h}時間{m}分後にリセット ({clock})"},
    "reset.m": {"zh": "{m}m 后重置 ({clock})", "en": "resets in {m}m ({clock})", "ja": "{m}分後にリセット ({clock})"},

    # --- Token Meter Window ---
    "meter.win_title": {
        "zh": "Token Meter · Antigravity 监控看板",
        "en": "Token Meter · Antigravity Monitor",
        "ja": "Token Meter · Antigravity モニター",
    },
    "meter.title": {
        "zh": "本机已记录用量 · Token Meter",
        "en": "Local Recorded Usage · Token Meter",
        "ja": "ローカル記録使用量 · Token Meter",
    },
    "meter.connecting": {"zh": "正在连接…", "en": "Connecting…", "ja": "接続中…"},
    "meter.disconnected": {"zh": "未连接 Antigravity", "en": "Antigravity Disconnected", "ja": "Antigravity 未接続"},
    "meter.source.ls": {"zh": "实时 · 本地语言服务", "en": "Live · Language Server", "ja": "ライブ · 言語サーバー"},
    "meter.source.pet_live": {"zh": "实时 · AGY 桌宠插件", "en": "Live · AGY Pet Plugin", "ja": "ライブ · AGY ペット連携"},
    "meter.source.hud_live": {"zh": "实时 · 侧边栏桥接", "en": "Live · Sidecar Bridge", "ja": "ライブ · サイドカー連携"},
    "meter.source.transcript": {
        "zh": "离线 · 本地会话日志（无配额、速率为估算）",
        "en": "Offline · Local Transcripts (no quota, estimated speed)",
        "ja": "オフライン · ローカルログ（枠なし・速度推定）",
    },
    "meter.theme.dark": {"zh": "🌙 深色", "en": "🌙 Dark", "ja": "🌙 ダーク"},
    "meter.theme.light": {"zh": "☀ 浅色", "en": "☀ Light", "ja": "☀ ライト"},
    "meter.refresh": {"zh": "刷新", "en": "Refresh", "ja": "更新"},
    "meter.tab.overview": {"zh": "Token 统计", "en": "Overview", "ja": "Token 統計"},
    "meter.tab.speed": {"zh": "速度对比", "en": "Speed", "ja": "速度比較"},
    "meter.tab.models": {"zh": "按模型 / 费用", "en": "Models & Cost", "ja": "モデル / 費用"},
    "meter.tab.steps": {"zh": "实时请求", "en": "Live Steps", "ja": "リアルタイム"},
    "meter.merge_subagents": {"zh": "合并子代理", "en": "Merge Subagents", "ja": "サブエージェント統合"},
    "meter.set_default": {"zh": "设为默认", "en": "Set Default", "ja": "デフォルトに設定"},
    "meter.is_default": {"zh": "已设为默认", "en": "Default Tab", "ja": "デフォルト済み"},
    "meter.scope.source": {"zh": "来源：", "en": "Source:", "ja": "ソース："},
    "meter.scope.all": {"zh": "全部", "en": "All", "ja": "すべて"},
    "meter.scope.main": {"zh": "主对话", "en": "Main", "ja": "メイン"},
    "meter.scope.subagent": {"zh": "子代理", "en": "Subagent", "ja": "サブ"},
    "meter.scope.ledger": {"zh": "账本范围：", "en": "Ledger:", "ja": "台帳範囲："},
    "meter.account.all": {
        "zh": "全部已记用量（含未归属）",
        "en": "All recorded usage (incl. unattributed)",
        "ja": "全記録（未帰属含む）",
    },
    "meter.account.item": {"zh": "账号 {id}{suffix}", "en": "Account {id}{suffix}", "ja": "アカウント {id}{suffix}"},
    "meter.account.unattr": {
        "zh": "仅未归属历史 ({count} 会话)",
        "en": "Unattributed history ({count} sessions)",
        "ja": "未帰属の履歴のみ ({count}件)",
    },
    "meter.account.meta": {
        "zh": "{attr}{extra} · 共 {total} 条会话",
        "en": "{attr}{extra} · {total} sessions",
        "ja": "{attr}{extra} · 計 {total} セッション",
    },
    "meter.account.attr_some": {"zh": "含 {count} 个已归属账号", "en": "{count} attributed account(s)", "ja": "帰属済み {count} アカウント"},
    "meter.account.attr_none": {"zh": "暂无账号归属", "en": "No account attribution", "ja": "アカウント未帰属"},
    "meter.account.extra_unattr": {"zh": " + 未归属历史", "en": " + unattributed", "ja": " + 未帰属履歴"},
    "meter.col.model": {"zh": "模型", "en": "Model", "ja": "モデル"},
    "meter.col.total_tok": {"zh": "总 Token", "en": "Total Tok", "ja": "合計 Token"},
    "meter.col.share": {"zh": "占比", "en": "Share", "ja": "割合"},
    "meter.col.input": {"zh": "输入", "en": "Input", "ja": "入力"},
    "meter.col.cache_read": {"zh": "缓存读", "en": "Cache Rd", "ja": "キャッシュ読"},
    "meter.col.thinking": {"zh": "思考", "en": "Think", "ja": "思考"},
    "meter.col.response": {"zh": "正文", "en": "Reply", "ja": "本文"},
    "meter.col.cache_hit": {"zh": "缓存命中", "en": "Cache %", "ja": "キャッシュ率"},
    "meter.col.cost": {"zh": "等效费用", "en": "Est. Cost", "ja": "相当費用"},
    "meter.col.decode_tps": {"zh": "流式 tok/s", "en": "Decode tok/s", "ja": "生成 tok/s"},
    "meter.col.peak": {"zh": "峰值", "en": "Peak", "ja": "ピーク"},
    "meter.col.e2e": {"zh": "端到端", "en": "E2E", "ja": "E2E"},
    "meter.col.ttft": {"zh": "TTFT", "en": "TTFT", "ja": "TTFT"},
    "meter.col.steps": {"zh": "步数", "en": "Steps", "ja": "ステップ"},
    "meter.col.time": {"zh": "时间", "en": "Time", "ja": "時刻"},
    "meter.col.output": {"zh": "输出", "en": "Output", "ja": "出力"},
    "meter.col.think_reply": {"zh": "思考/正文", "en": "Think/Reply", "ja": "思考/本文"},
    "meter.col.duration": {"zh": "总耗时", "en": "Duration", "ja": "所要時間"},
    "meter.col.tools": {"zh": "工具调用", "en": "Tools", "ja": "ツール呼出"},
    "meter.conv.waiting": {"zh": "当前会话：等待遥测数据…", "en": "Current session: waiting for telemetry…", "ja": "現在のセッション：データ待機中…"},
    "meter.conv.line": {
        "zh": "当前会话：{title}（{state}） · 选择模型 {selected} · 最近一步 {last}",
        "en": "Session: {title} ({state}) · Selected {selected} · Last step {last}",
        "ja": "現在のセッション：{title}（{state}） · 選択 {selected} · 直近 {last}",
    },
    "meter.state.running": {"zh": "运行中", "en": "Running", "ja": "実行中"},
    "meter.state.idle": {"zh": "空闲", "en": "Idle", "ja": "待機中"},
    "meter.state.ready": {"zh": "就绪", "en": "Ready", "ja": "準備完了"},
    "meter.card.speed": {"zh": "⚡ 生成速率", "en": "⚡ Generation Speed", "ja": "⚡ 生成速度"},
    "meter.card.quota": {"zh": "🔋 限额剩余", "en": "🔋 Quota Remaining", "ja": "🔋 クォータ残量"},
    "meter.card.cache": {"zh": "🎯 缓存命中", "en": "🎯 Cache Hit", "ja": "🎯 キャッシュ率"},
    "meter.card.ctx": {"zh": "🧠 上下文占用", "en": "🧠 Context Usage", "ja": "🧠 コンテキスト"},
    "meter.speed_detail": {
        "zh": "会话均值 {avg} · 端到端 {e2e} · TTFT {ttft}",
        "en": "Avg {avg} · E2E {e2e} · TTFT {ttft}",
        "ja": "平均 {avg} · E2E {e2e} · TTFT {ttft}",
    },
    "meter.quota_week_fmt": {"zh": "周 {val}", "en": "Wk {val}", "ja": "週 {val}"},
    "meter.quota_5h_win": {"zh": "5h 窗口", "en": "5h window", "ja": "5時間枠"},
    "meter.quota_offline": {"zh": "离线模式无法获取配额", "en": "Quota unavailable in offline mode", "ja": "オフライン時は枠取得不可"},
    "meter.cache_detail": {
        "zh": "会话累计 {total} tokens",
        "en": "Session total {total} tokens",
        "ja": "セッション累計 {total} tokens",
    },
    "meter.updated_at": {"zh": "更新于 {time}", "en": "Updated {time}", "ja": "{time} 更新"},
    "meter.footer.init": {"zh": "● 就绪 · 等待数据…", "en": "● Ready · Waiting for data…", "ja": "● 準備完了 · データ待機中…"},
    "meter.footer": {
        "zh": "● {state} · ⏱ 当前会话 {steps} 步 · {speed} · 🗄 账本累计 {total} tok · 综合缓存命中率 {hit:.1f}%",
        "en": "● {state} · ⏱ {steps} steps · {speed} · 🗄 Ledger {total} tok · Cache {hit:.1f}%",
        "ja": "● {state} · ⏱ 現在 {steps} ステップ · {speed} · 🗄 台帳累計 {total} tok · キャッシュ率 {hit:.1f}%",
    },

    # --- Usage Dashboard ---
    "dash.tier.unknown_init": {
        "zh": "💎 订阅档位暂未识别（连接 Antigravity 语言服务后自动同步）",
        "en": "💎 Subscription tier pending (auto-syncs with Antigravity Language Server)",
        "ja": "💎 契約プラン未認識（Antigravity 言語サーバー接続時に自動同期）",
    },
    "dash.tier.pending": {
        "zh": "💎 订阅档位待同步（在 Antigravity 插件页开关一次 AGY 桌宠或重开 IDE 后自动识别）",
        "en": "💎 Tier pending sync (toggle AGY Pet plugin or reopen IDE to auto-detect)",
        "ja": "💎 プラン同期待ち（AGY ペットプラグインの再切替または IDE 再起動で自動認識）",
    },
    "dash.tier.offline": {
        "zh": "💎 {tier} · 历史已记录（当前离线统计）",
        "en": "💎 {tier} · Recorded (offline view)",
        "ja": "💎 {tier} · 履歴記録済み（オフライン集計）",
    },
    "dash.tier.synced": {
        "zh": "💎 {tier} · 已自动识别 · {freshness}",
        "en": "💎 {tier} · Auto-detected · {freshness}",
        "ja": "💎 {tier} · 自動認識済み · {freshness}",
    },
    "dash.fresh.just": {"zh": "刚刚更新", "en": "Just updated", "ja": "たった今更新"},
    "dash.fresh.synced": {"zh": "已同步", "en": "Synced", "ja": "同期済み"},
    "dash.detail.open": {"zh": "详情 ▼", "en": "Details ▼", "ja": "詳細 ▼"},
    "dash.detail.close": {"zh": "收起 ▲", "en": "Hide ▲", "ja": "閉じる ▲"},
    "dash.tier.price": {
        "zh": "${usd:,.2f}/月 (≈ {cny} CNY)",
        "en": "${usd:,.2f}/mo (≈ {cny} CNY)",
        "ja": "${usd:,.2f}/月 (約 {cny} CNY)",
    },
    "dash.tier.roi": {
        "zh": "本月等效 API 消耗 {month_cost}（占订阅月费 {roi:.0f}%），缓存读取累计省下 {saved_cost}。",
        "en": "Monthly equiv. API value: {month_cost} ({roi:.0f}% of plan price); cache saved {saved_cost}.",
        "ja": "今月の API 相当額 {month_cost}（月額の {roi:.0f}%）、キャッシュ節約累計 {saved_cost}。",
    },
    "dash.tier.no_plan": {
        "zh": "本月等效 API 消耗 {month_cost}，缓存省下 {saved_cost}。",
        "en": "Monthly equiv. API value: {month_cost}; cache saved {saved_cost}.",
        "ja": "今月の API 相当額 {month_cost}、キャッシュ節約 {saved_cost}。",
    },
    "dash.tier.offline_detail": {
        "zh": "当前按离线记录统计：本月等效 API 消耗 {month_cost}，缓存读取累计省下 {saved_cost}。",
        "en": "Offline estimate: monthly equiv. API value {month_cost}; cache saved {saved_cost}.",
        "ja": "オフライン記録集計：今月の API 相当額 {month_cost}、キャッシュ節約累計 {saved_cost}。",
    },
    "dash.hero.total": {"zh": "累计处理 Token\n含缓存读取", "en": "Total Tokens\nincl. cache read", "ja": "累計処理 Token\nキャッシュ読込含む"},
    "dash.hero.today": {"zh": "今日使用", "en": "Today", "ja": "今日の使用量"},
    "dash.hero.month": {"zh": "本月使用", "en": "This Month", "ja": "今月の使用量"},
    "dash.hero.year": {"zh": "年度使用", "en": "This Year", "ja": "年間の使用量"},
    "dash.hero.daily_avg": {"zh": "≈ {cost} · 日均 {daily}", "en": "≈ {cost} · {daily}/day", "ja": "≈ {cost} · 日平均 {daily}"},
    "dash.hero.active_convs": {"zh": "{count} 会话活跃", "en": "{count} active sessions", "ja": "{count} セッション稼働"},
    "dash.hero.avg_tok_day": {"zh": "日均约 {tok}", "en": "~{tok} / day", "ja": "日平均 約 {tok}"},
    "dash.hero.active_days": {"zh": "{days} 天活动记录", "en": "{days} active days", "ja": "{days} 日間の活動記録"},
    "dash.cache.split": {
        "zh": "输入(未缓存) {fresh}   缓存读取 {cache}   总输入(输入+缓存) {prompt}   输出 {out}",
        "en": "Uncached In {fresh}   Cache Read {cache}   Total In {prompt}   Output {out}",
        "ja": "新規入力 {fresh}   キャッシュ読 {cache}   総入力 {prompt}   出力 {out}",
    },
    "dash.cache.ratio": {"zh": "缓存读取占比 {pct:.1f}%", "en": "Cache Share {pct:.1f}%", "ja": "キャッシュ読込比 {pct:.1f}%"},
    "dash.cache.note": {
        "zh": "按当前筛选范围总缓存读取 / 总输入（未命中缓存输入 + 缓存读取）加权计算。",
        "en": "Weighted ratio: total cache read / total input (uncached + cache read) for the current filter.",
        "ja": "現在の絞り込み範囲のキャッシュ読込 ÷ 総入力（新規入力＋キャッシュ読込）で加重計算。",
    },
    "dash.win.5h": {"zh": "5 小时窗口", "en": "5-Hour Window", "ja": "5時間ウィンドウ"},
    "dash.win.week": {"zh": "每周额度", "en": "Weekly Quota", "ja": "週間クォータ"},
    "dash.win.left": {"zh": "剩余 {pct:.0f}%{reset}", "en": "{pct:.0f}% left{reset}", "ja": "残り {pct:.0f}%{reset}"},
    "dash.win.none": {"zh": "暂无数据", "en": "No data", "ja": "データなし"},
    "dash.heat.title": {"zh": "Token 活动", "en": "Token Activity", "ja": "Token アクティビティ"},
    "dash.heat.day": {"zh": "每天", "en": "Daily", "ja": "日別"},
    "dash.heat.week": {"zh": "每周", "en": "Weekly", "ja": "週別"},
    "dash.heat.total": {"zh": "累计总量", "en": "Cumulative", "ja": "累計"},
    "dash.heat.month": {"zh": "按月", "en": "Month", "ja": "月間"},
    "dash.heat.year": {"zh": "按年", "en": "Year", "ja": "年間"},
    "dash.heat.all_models": {"zh": "全部模型", "en": "All Models", "ja": "すべてのモデル"},
    "dash.heat.less": {"zh": "少", "en": "Less", "ja": "少"},
    "dash.heat.more": {"zh": "多", "en": "More", "ja": "多"},
    "dash.heat.first_day": {"zh": "首次使用：{day}", "en": "First active: {day}", "ja": "初回利用：{day}"},
    "dash.heat.tip_week": {"zh": "{day} 所在周", "en": "Week of {day}", "ja": "{day} の週"},
    "dash.heat.tip_total": {"zh": "截至 {day} 累计", "en": "Cumulative through {day}", "ja": "{day} までの累計"},
    "dash.heat.steps_unit": {"zh": "{val:,} 步", "en": "{val:,} steps", "ja": "{val:,} ステップ"},
    "dash.metric.total": {"zh": "Token（含缓存读取）", "en": "Tokens (incl. cache)", "ja": "Token（キャッシュ含む）"},
    "dash.metric.fresh": {"zh": "Token（不含缓存）", "en": "Tokens (uncached)", "ja": "Token（キャッシュ除く）"},
    "dash.metric.output": {"zh": "输出 Token", "en": "Output Tokens", "ja": "出力 Token"},
    "dash.metric.steps": {"zh": "步数", "en": "Steps", "ja": "ステップ数"},
    "dash.metric.cost": {"zh": "等效金额（USD）", "en": "Est. Cost (USD)", "ja": "相当金額（USD）"},
    "dash.stat.total": {"zh": "累计 Token", "en": "Total Tokens", "ja": "累計 Token"},
    "dash.stat.peak": {"zh": "单日峰值", "en": "Daily Peak", "ja": "1日ピーク"},
    "dash.stat.task": {"zh": "最长连续工作", "en": "Longest Session", "ja": "最長連続作業"},
    "dash.stat.longest": {"zh": "最长连续天数", "en": "Best Streak", "ja": "最長連続日数"},
    "dash.stat.current": {"zh": "当前连续天数", "en": "Current Streak", "ja": "現在の連続日数"},
    "dash.stat.days": {"zh": "{days} 天", "en": "{days}d", "ja": "{days}日"},
    "dash.cost.title": {"zh": "等效 API 费用明细", "en": "Equivalent API Cost Breakdown", "ja": "API 相当費用明細"},
    "dash.cost.today": {"zh": "今天", "en": "Today", "ja": "今日"},
    "dash.cost.week": {"zh": "近 7 天", "en": "Last 7 Days", "ja": "過去7日"},
    "dash.cost.month": {"zh": "本月", "en": "This Month", "ja": "今月"},
    "dash.cost.saved": {"zh": "缓存省下", "en": "Cache Saved", "ja": "キャッシュ節約"},
    "dash.cost.col_amount": {"zh": "金额", "en": "Cost", "ja": "金額"},
    "dash.cost.unpriced": {"zh": "未定价", "en": "Unpriced", "ja": "価格未設定"},
    "dash.cost.missing": {
        "zh": "读不到价格表 assets/pricing.json：{error}",
        "en": "Unable to read assets/pricing.json: {error}",
        "ja": "価格表 assets/pricing.json を読み込めません：{error}",
    },
    "dash.cost.estimated": {
        "zh": "其中 {usd} 来自离线日志里没记录模型的步骤，按 {model} 的价格估算。",
        "en": "Includes {usd} from offline steps without model metadata, estimated at {model} rates. ",
        "ja": "うち {usd} はモデル記録のないオフライン手順を {model} の単価で推定しています。",
    },
    "dash.cost.note": {
        "zh": "按官方 API 标价折算（汇率按 1 USD = {rate:.2f} CNY 估算），每一步用当天生效价格；输入只算未命中缓存部分，缓存读按缓存价，输出含思考。{estimated}价格表在 assets/pricing.json，可以自己改。",
        "en": "Estimated at official API list prices (1 USD = {rate:.2f} CNY), using each step's effective date. Uncached input, cache reads, and output (incl. thinking) are priced separately. {estimated}Edit rates in assets/pricing.json.",
        "ja": "公式 API 単価換算（1 USD = {rate:.2f} CNY 概算）。新規入力・キャッシュ読込・出力（思考含む）をそれぞれ当時の単価で集計。{estimated}単価表は assets/pricing.json で編集可能です。",
    },
    "dash.note.since": {"zh": "，最早一条在 {day}", "en": " since {day}", "ja": "（最古 {day}）"},
    "dash.note": {
        "zh": "按每一步的时间戳统计 {convs} 个会话、{steps:,} 步{since}。启用本机用量账本后，超出最近 40 条或已删除的历史会话仍会累计保留。",
        "en": "Aggregated from {convs} sessions and {steps:,} steps{since}. With the local usage ledger enabled, older or deleted sessions remain preserved.",
        "ja": "{convs} セッション・{steps:,} ステップを集計{since}。ローカル使用量台帳により、直近40件以降や削除済みセッションも累計保持されます。",
    },

    # --- Speed Comparison Chart ---
    "speed.empty_bar": {
        "zh": "当前筛选范围内暂无可用速度数据",
        "en": "No speed samples in the selected range",
        "ja": "選択範囲に速度データがありません",
    },
    "speed.empty_trend": {
        "zh": "选择上方模型后显示最近请求趋势",
        "en": "Select a model above to view recent request trends",
        "ja": "上のモデルを選ぶと直近の推移を表示します",
    },
    "speed.low_sample": {"zh": "样本少", "en": "Low N", "ja": "少数"},
    "speed.tip_bar": {
        "zh": "{label}\n样本数: {count}{low}\n时间范围: {span}\n输出 tokens 中位数: {out:,}\n输入 tokens 中位数: {inp:,}",
        "en": "{label}\nSamples: {count}{low}\nRange: {span}\nMedian output tokens: {out:,}\nMedian input tokens: {inp:,}",
        "ja": "{label}\nサンプル数: {count}{low}\n期間: {span}\n出力トークン中央値: {out:,}\n入力トークン中央値: {inp:,}",
    },
    "speed.tip_low_suffix": {"zh": "（样本少）", "en": " (low sample)", "ja": "（サンプル少）"},
    "speed.tip_trend": {
        "zh": "{ts}\n{val}\n输出 {out:,} · 输入 {inp:,}",
        "en": "{ts}\n{val}\nOutput {out:,} · Input {inp:,}",
        "ja": "{ts}\n{val}\n出力 {out:,} · 入力 {inp:,}",
    },
    "speed.win.7": {"zh": "近 7 天", "en": "7 Days", "ja": "過去7日"},
    "speed.win.30": {"zh": "近 30 天", "en": "30 Days", "ja": "過去30日"},
    "speed.win.0": {"zh": "全部", "en": "All", "ja": "全期間"},
    "speed.src.all": {"zh": "全部来源", "en": "All Sources", "ja": "全ソース"},
    "speed.src.main": {"zh": "主对话", "en": "Main", "ja": "メイン"},
    "speed.src.subagent": {"zh": "子代理", "en": "Subagent", "ja": "サブ"},
    "speed.metric.speed": {"zh": "输出速度", "en": "Speed", "ja": "出力速度"},
    "speed.metric.ttft": {"zh": "首字延迟", "en": "TTFT", "ja": "初回遅延"},
    "speed.metric.duration": {"zh": "总耗时", "en": "Duration", "ja": "総時間"},
    "speed.title.speed": {"zh": "输出速度对比", "en": "Output Speed Comparison", "ja": "出力速度比較"},
    "speed.title.ttft": {"zh": "首字延迟对比", "en": "Time-to-First-Token (TTFT)", "ja": "初回トークン遅延 (TTFT) 比較"},
    "speed.title.duration": {"zh": "总耗时对比", "en": "Total Duration Comparison", "ja": "総所要時間比較"},
    "speed.note": {
        "zh": "以各模型与档位的中位数统计；不足 3 条标注“样本少”。总耗时受输出长度影响，条件相近时才可比较。",
        "en": "Medians per model/tier; groups with < 3 samples are tagged 'Low N'. Total duration depends on response length.",
        "ja": "モデル・枠ごとの中央値で集計（3件未満は「少数」表示）。総時間は出力長に依存します。",
    },
    "speed.trend_title": {"zh": "单模型速度趋势", "en": "Model Speed Trend", "ja": "単一モデルの推移"},
}
