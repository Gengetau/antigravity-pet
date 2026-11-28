"""Trilingual (zh / en / ja) interactive lines for reactions, autonomy, clones, scenes, and PetWindow."""

from __future__ import annotations

from typing import Any

from app.i18n import get_language, resolve_language


def _code(lang: str | None = None) -> str:
    return resolve_language(lang) if lang is not None else get_language()


# ---------------------------------------------------------------------------
# PetWindow states, idle playmate activities, and direct bubbles
# ---------------------------------------------------------------------------

PET_STATE_NAMES: dict[str, dict[str, str]] = {
    "zh": {
        "IDLE": "待机", "BLINK": "眨眨眼", "GLANCE": "四处看看", "THINKING": "发呆",
        "WALKING": "散步", "HAPPY": "开心", "HEAD_PAT": "被摸摸", "TALKING": "说话",
        "ANGRY": "生气", "POKE_REACT": "被戳", "TAIL_REACT": "尾巴被碰", "EATING": "吃东西",
        "SWEEPING": "扫地", "SLEEPING": "睡觉", "DRAGGING": "抓取中", "FALLING": "落下",
        "LANDING": "着陆", "DIZZY": "眩晕", "WORKING": "陪你干活", "CELEBRATE": "庆祝",
        "TIRED": "没精神", "STRETCH": "伸懒腰", "TRANSFORM": "变身中", "WAVE": "打招呼",
        "PERCH": "坐在窗口上", "CLIMBING": "爬窗户", "SULK": "闹别扭中", "WAITING_USER": "等你确认啦",
        "JUMP_UP": "起跳", "PET_PURR": "享受摸头", "PERCH_SLEEP": "窗口打盹", "DOCK_SLEEP": "贴边打盹",
        "REFUSE_FOOD": "拒绝投喂",
        "_dock_peek": "探头看你", "_dock_hide": "贴边藏身", "_sulk": "闹别扭中",
        "_cond_tired": "有点困", "_cond_annoyed": "闹脾气", "_cond_restless": "想走走",
        "_cond_cheerful": "心情很好", "_cond_affectionate": "很亲近", "_cond_steady": "待机",
    },
    "en": {
        "IDLE": "Idle", "BLINK": "Blinking", "GLANCE": "Looking around", "THINKING": "Daydreaming",
        "WALKING": "Strolling", "HAPPY": "Happy", "HEAD_PAT": "Head-pat", "TALKING": "Chatting",
        "ANGRY": "Grumpy", "POKE_REACT": "Poked", "TAIL_REACT": "Tail touched", "EATING": "Eating",
        "SWEEPING": "Sweeping", "SLEEPING": "Sleeping", "DRAGGING": "Carried", "FALLING": "Falling",
        "LANDING": "Landing", "DIZZY": "Dizzy", "WORKING": "Coding buddy", "CELEBRATE": "Celebrating",
        "TIRED": "Sleepy", "STRETCH": "Stretching", "TRANSFORM": "Switching", "WAVE": "Waving",
        "PERCH": "Perched", "CLIMBING": "Climbing", "SULK": "Sulking", "WAITING_USER": "Waiting for you",
        "JUMP_UP": "Jumping", "PET_PURR": "Purring", "PERCH_SLEEP": "Window nap", "DOCK_SLEEP": "Edge nap",
        "REFUSE_FOOD": "Refused food",
        "_dock_peek": "Peeking", "_dock_hide": "Edge-docked", "_sulk": "Sulking",
        "_cond_tired": "Sleepy", "_cond_annoyed": "Grumpy", "_cond_restless": "Restless",
        "_cond_cheerful": "Cheerful", "_cond_affectionate": "Affectionate", "_cond_steady": "Idle",
    },
    "ja": {
        "IDLE": "待機中", "BLINK": "まばたき", "GLANCE": "きょろきょろ", "THINKING": "ぼーっと中",
        "WALKING": "お散歩", "HAPPY": "ごきげん", "HEAD_PAT": "なでなで", "TALKING": "おしゃべり",
        "ANGRY": "ぷんぷん", "POKE_REACT": "つんつん", "TAIL_REACT": "しっぽ反応", "EATING": "もぐもぐ",
        "SWEEPING": "お掃除", "SLEEPING": "すやすや", "DRAGGING": "もちあげ中", "FALLING": "落下中",
        "LANDING": "着地", "DIZZY": "くらくら", "WORKING": "作業お供中", "CELEBRATE": "お祝い",
        "TIRED": "ねむそう", "STRETCH": "のび〜", "TRANSFORM": "変身中", "WAVE": "てふり",
        "PERCH": "窓に腰掛け", "CLIMBING": "窓登り中", "SULK": "すね中", "WAITING_USER": "確認待ちだよ",
        "JUMP_UP": "ジャンプ", "PET_PURR": "ごろごろ", "PERCH_SLEEP": "窓辺でお昼寝", "DOCK_SLEEP": "端っこ居眠り",
        "REFUSE_FOOD": "いやいや",
        "_dock_peek": "ひょっこり覗き見", "_dock_hide": "端っこ隠れ中", "_sulk": "すね中",
        "_cond_tired": "ちょっと眠い", "_cond_annoyed": "ご機嫌ななめ", "_cond_restless": "歩きたい",
        "_cond_cheerful": "ごきげん", "_cond_affectionate": "なかよし", "_cond_steady": "待機中",
    },
}

IDLE_PLAY_ACTIVITIES: dict[str, tuple[str, ...]] = {
    "zh": (
        "晒太阳发呆", "玩捉迷藏", "比比谁跳得高", "喝下午茶", "一起数星星",
        "串门聊天", "围观姐姐摸鱼", "分享小鱼干", "叠罗汉比赛", "偷偷讲悄悄话",
    ),
    "en": (
        "sunbathing together", "playing hide-and-seek", "high-jump contest", "afternoon tea", "counting stars",
        "dropping by to chat", "watching Big Sis slack off", "sharing fish snacks", "tower stacking", "whispering secrets",
    ),
    "ja": (
        "ひなたぼっこ", "かくれんぼ", "ジャンプ競争", "アフタヌーンティー", "星かぞえ",
        "おしゃべり訪問", "お姉さまの息抜き見学", "小魚おやつ分けっこ", "組み体操ごっこ", "ひみつのおしゃべり",
    ),
}

WINDOW_MESSAGES: dict[str, dict[str, str]] = {
    "zh": {
        "dizzy_shake": "呜哇别晃了，转圈圈头好晕……",
        "forgive_pat_1": "哼……摸头就算原谅你啦～",
        "forgive_pat_2": "哼……好吧，看在摸头的份上原谅你啦～",
        "still_sulking": "哼，还在生闷气呢……摸摸头再哄我嘛。",
        "sulk_start": "气鼓鼓！不理你了，要摸头才原谅！",
        "forgive_gentle": "唔……摸这么温柔，那就原谅你吧～",
        "awareness_on": "本地环境感知已开启。",
        "awareness_off": "本地环境感知已暂停。",
        "recall_done": "我回来主屏幕啦～",
        "dock_hide": "先躲到屏幕边上探头看你，鼠标过来我再出来～",
        "passthrough_on": "我隐身了！右键托盘图标可以解除。",
        "autostart_on": "已设置开机自启，明天见。",
        "autostart_off": "已取消开机自启。",
        "follow_model_on": "我会跟着 Antigravity 当前的模型换形态。",
        "need_surfaces": "先在「更多设置」打开「窗口落脚」就能爬窗啦",
        "no_climb_win": "这里没有能爬的窗口呀",
        "form_announce_fallback": "{name} 形态！{tagline}。",
        "playmate_model": "闲时随机玩伴",
        "playmate_twin": "双胞胎 {name}",
        "playmate_triplet": "三胞胎 {name}",
        "playmate_multi": "{n} 只 {name}",
        "playmate_join": "、",
        "playmate_more": "{first}、{second} 等 {total} 位",
        "tray_awareness": "暂停/启用环境感知",
        "privacy_title": "本地隐私规则",
        "privacy_body": (
            "环境感知只在本机读取前台进程名、窗口标题、空闲时长和全屏状态。\n\n"
            "开启“窗口落脚”时，只额外读取前台窗口句柄和外框位置，用来判断顶部落点与随动；不会读取窗口内容。\n\n"
            "密码管理器、支付/银行、远程桌面、聊天和邮件应用，以及无痕窗口默认不保留标题，也不会触发台词。"
            "\n\n不会截图、不会读取浏览历史、不会把感知数据发送到网络。"
        ),
    },
    "en": {
        "dizzy_shake": "Whoa, stop shaking me! Everything's spinning…",
        "forgive_pat_1": "Hmph… head pats mean you're forgiven~",
        "forgive_pat_2": "Hmph… okay, I'll forgive you for that head pat~",
        "still_sulking": "Hmph, still pouting… pat my head to make up!",
        "sulk_start": "Puff! Not talking to you until you pat my head!",
        "forgive_gentle": "Mmh… since you patted so gently, I forgive you~",
        "awareness_on": "Local context awareness enabled.",
        "awareness_off": "Local context awareness paused.",
        "recall_done": "Back on the main display~",
        "dock_hide": "Tucking into the screen edge—hover over me whenever you want!",
        "passthrough_on": "Click-through enabled! Right-click the tray icon to undo.",
        "autostart_on": "Autostart enabled—see you next boot!",
        "autostart_off": "Autostart disabled.",
        "follow_model_on": "I'll switch forms automatically to match Antigravity's model!",
        "need_surfaces": "Turn on 'Win Perch' in More Settings first to climb windows~",
        "no_climb_win": "No climbable window within reach right now~",
        "form_announce_fallback": "{name} form! {tagline}.",
        "playmate_model": "Idle Playmate",
        "playmate_twin": "{name} twins",
        "playmate_triplet": "{name} triplets",
        "playmate_multi": "{n}× {name}",
        "playmate_join": ", ",
        "playmate_more": "{first}, {second} & {total} total",
        "tray_awareness": "Toggle Local Awareness",
        "privacy_title": "Local Privacy Rules",
        "privacy_body": (
            "Context awareness reads only the foreground process name, window title, idle time, and fullscreen state locally.\n\n"
            "When 'Win Perch' is enabled, it reads window bounds solely for landing & following—never window contents.\n\n"
            "Password managers, banking, remote desktop, chat/mail, and incognito windows never keep titles or trigger lines.\n\n"
            "No screenshots, no browsing history, and zero network uploads."
        ),
    },
    "ja": {
        "dizzy_shake": "うわっ揺らさないで、目が回っちゃう……",
        "forgive_pat_1": "ふんっ……頭なでてくれたから許してあげる〜",
        "forgive_pat_2": "ふんっ……まあ、なでてくれたし許してあげよっかな〜",
        "still_sulking": "ぷん、まだすねてるもん……頭なでて機嫌とって？",
        "sulk_start": "ぷんぷん！もう知らないっ、なでなでするまで許さない！",
        "forgive_gentle": "んぅ……そんな優しくなでられたら許しちゃうよ〜",
        "awareness_on": "ローカル画面認識をオンにしました。",
        "awareness_off": "ローカル画面認識を一時停止しました。",
        "recall_done": "メイン画面に戻ってきたよ〜",
        "dock_hide": "画面の端に隠れて覗いてるね、カーソルを近づけてね〜",
        "passthrough_on": "クリック透過オン！トレイアイコンの右クリックで解除できます。",
        "autostart_on": "自動起動をオンにしたよ、また明日ね！",
        "autostart_off": "自動起動をオフにしました。",
        "follow_model_on": "Antigravity のモデルに合わせて自動で変身するね！",
        "need_surfaces": "「詳細設定」で「窓上着地」をオンにすると登れるよ〜",
        "no_climb_win": "近くに登れるウィンドウがないみたい…",
        "form_announce_fallback": "{name} フォーム！{tagline}。",
        "playmate_model": "おひまな遊び仲間",
        "playmate_twin": "双子の {name}",
        "playmate_triplet": "三つ子の {name}",
        "playmate_multi": "{name}×{n}",
        "playmate_join": "・",
        "playmate_more": "{first}・{second} ほか計 {total} 人",
        "tray_awareness": "画面認識の一時停止／再開",
        "privacy_title": "ローカルプライバシールール",
        "privacy_body": (
            "画面認識はローカルのみで前面プロセス名・ウィンドウ名・放置時間・全画面状態を読み取ります。\n\n"
            "「窓上着地」有効時は着地と追従のためウィンドウ枠座標のみ参照し、中身は一切読み取りません。\n\n"
            "パスワード管理・金融・リモートデスクトップ・チャット/メール・シークレットウィンドウではタイトルを保持せずセリフも発火しません。\n\n"
            "スクリーンショット・閲覧履歴の収集や外部送信は一切行いません。"
        ),
    },
}


def win_msg(key: str, *, lang: str | None = None, **kwargs: Any) -> str:
    code = _code(lang)
    text = WINDOW_MESSAGES.get(code, WINDOW_MESSAGES["zh"]).get(key) or WINDOW_MESSAGES["zh"].get(key, key)
    return text.format(**kwargs) if kwargs else text


def pet_state_name(key: str, *, lang: str | None = None) -> str:
    code = _code(lang)
    table = PET_STATE_NAMES.get(code, PET_STATE_NAMES["zh"])
    return table.get(key) or PET_STATE_NAMES["zh"].get(key, key)


def idle_play_activities(*, lang: str | None = None) -> tuple[str, ...]:
    return IDLE_PLAY_ACTIVITIES.get(_code(lang), IDLE_PLAY_ACTIVITIES["zh"])


# ---------------------------------------------------------------------------
# Reactions (TOOL_STATUS_NAMES, LINES, festivals & time-of-day greetings)
# ---------------------------------------------------------------------------

REACTION_TOOL_STATUS: dict[str, dict[str, str]] = {
    "en": {
        "reading": "Reading code",
        "writing": "Writing code",
        "running": "Watching terminal",
        "searching": "Searching docs",
        "drawing": "Watching design",
        "delegating": "Leading subagents",
        "asking": "Waiting for you",
    },
    "ja": {
        "reading": "コード読解中",
        "writing": "コーディング並走",
        "running": "コマンド監視中",
        "searching": "一緒にリサーチ",
        "drawing": "お絵かき見学中",
        "delegating": "分身を指揮中",
        "asking": "確認待ちだよ",
    },
}

REACTION_LINES: dict[str, dict[str, tuple[str, ...]]] = {
    "en": {
        "started": ("Antigravity started running—I'll keep an eye on tokens!", "New inference turn taking off!", "Model is thinking; I'm counting tok/s for you."),
        "finished": ("Turn complete! {total} tokens this turn.", "Reply wrapped up~ {total} tokens this turn.", "Touchdown! {total} tokens this turn, avg {rate} tok/s."),
        "turn_error": ("Oops, that turn hit an error—let's debug it together.", "Bumped into an error… don't worry, I've got your back!"),
        "waiting": ("Psst! Antigravity is waiting for your confirmation!", "There's a prompt waiting for your reply over there~"),
        "subagent_start": ("Summoned a mini-clone to help out!", "Subagent clone reporting for duty!"),
        "subagent_many": ("Whoa, {count} mini-clones working in parallel!", "{count} subagent clones on deck—turbo productivity!"),
        "subagent_done": ("Great job {name}, I'll take it from here~", "{name} delivered the goods! Smooth teamwork~", "Awesome work, {name} wrapped up cleanly!"),
        "subagent_cheer": ("Hey, don't forget to pat me after cheering {name}~", "Thanks for cheering {name} on!", "{name} is super motivated now~"),
        "subagent_report": ("Got {name}'s report: {title}!", "Copy that {name}, I'll pick up {title}~"),
        "subagent_high_five": ("High-five with {name}! Unstoppable duo~", "Snuggle high-five! {name} and I are in sync~", "Yay! Teaming up with {name} feels awesome!"),
        "subagent_group_cheer": ("Full squad energy—let's go!!", "Me and the mini-clones dancing in sync!"),
        "subagent_relay": ("Caught the clue from {name}~", "Nice find {name}, merging it in!", "Signal synced—moving forward~"),
        "subagent_pet_rub": ("Aww, {name} is purring up a storm~", "Save some head rubs for me after {name}~"),
        "subagent_trick": ("Bravo! {name}'s little trick is 10/10~", "Whoa! {name}'s spin is adorable~"),
        "subagent_gift_share": ("Ooh, thanks for the little gift, {name}!", "Got {name}'s fish snack—energy restored~"),
        "subagent_clone_buddy": ("Haha, {name} and friends are totally in sync~", "Squad high-fives all around!"),
        "subagent_clone_chat": ("Ooh, what secrets is {name} whispering about~", "Hearing you all cheer each other on pumps me up too!"),
        "subagent_host_pat": ("There, there {name}—good job today~", "Pat pat, {name} nailed it~", "Head pats from Big Sis—fish snacks after work!"),
        "subagent_clone_train": ("Choo-choo! Big Sis is the engine—line up behind me!", "All aboard! Follow me on the cutest desktop parade~"),
        "subagent_clone_wave": ("Big Sis takes the baton—the wave relay was a hit!", "Whoa! What a crisp Mexican wave from everyone~"),
        "subagent_snack_party": ("Fish snack rain! Come grab a bite, everyone~", "My treat! Gather round for a quick snack break~"),
        "subagent_group_huddle": ("Whoa!! Group hug from all the mini-clones—so warm~", "Everyone's snuggled right in, instant full recharge!"),
        "subagent_twin_mirror": ("Whoa! Twin {name} mirror dance—100% sync~", "Double {name}, double charm and efficiency!"),
        "subagent_mini_me_mimic": ("Eek! Mini {name} copying my pose is way too cute~", "Big & Mini {name} side by side—maximum morale!"),
        "subagent_tea_party": ("Break time! Desktop afternoon tea is served~", "Ding~ Cream table's ready—have some strawberry cake!"),
        "subagent_tea_party_interact": ("One more cup of warm fruit tea—plenty of pastries~", "Fresh strawberry cake slices for everyone!"),
        "subagent_campfire_night": ("Cozy campfire lit—let's roast marshmallows on this late shift~", "Warm firelight and stories—never coding alone tonight!"),
        "subagent_campfire_night_interact": ("Flames are crackling brighter—watch those marshmallows~", "Tossed in another log, the whole desk feels toasty!"),
        "subagent_art_studio": ("Mini art studio open! Are you painting my portrait~", "Alright, I'll hold a sparkly pose—paint me cute!"),
        "subagent_art_studio_interact": ("Whoa, it looks just like me! Framing this one~", "Amazing! Every new canvas is cuter than the last!"),
        "subagent_cloud_nap": ("Fluffy cloud nest ready—let's all take a quick power nap~", "Starry blanket tucked in—recharge and wake up fresh!"),
        "subagent_cloud_nap_interact": ("Tucking the starry blanket snugly around everyone—sweet dreams~", "Fluffed up the cloud cushion—so cozy~"),
        "subagent_cloud_nap_wake": ("Phew—power nap complete! Back at 100% energy!", "Big stretch! Feeling twice as sharp after that nap~"),
        "playmate_summon": ("Nothing urgent—called {names} over to hang out~", "Ding! Summoned {names} to visit the desk~", "Break time! Hanging out with {names}~"),
        "playmate_add": ("The merrier the better! Welcome {names} to the party~", "Ding! {names} just joined the fun~"),
        "playmate_done": ("Bye-bye {name}, let's play again next break~", "Had a blast with {name}, see ya!", "{name} hopped back to rest—catch you soon~"),
        "playmate_cheer": ("Hey, pat me too after petting {name}~", "Haha, {name} is beaming with joy!"),
        "playmate_report": ("Ooh yes! Let's enjoy {title} with {name}!", "Hehe, I love {title} with {name}~"),
        "playmate_high_five": ("High-five with {name}! Top-tier break buddy~", "Yay! Having so much fun with {name}~"),
        "playmate_group_cheer": ("Mini desktop party! Everybody bounce~", "Party time with the random mini-clones!"),
        "playmate_relay": ("Caught it, {name}! Sending a sparkle back~", "Haha {name}, you're so playful—again!"),
        "playmate_pet_rub": ("Aww, {name}'s eyes are squinting with bliss~", "No fair! Rub my head too after {name}~"),
        "playmate_trick": ("Clap clap! {name}'s twirl is adorable~", "Whoa, {name} has moves! Encore!"),
        "playmate_gift_share": ("Ooh, thanks for the surprise treat, {name}!", "Got {name}'s fish snack—snuggles~"),
        "playmate_clone_buddy": ("Haha, {name} and friends are having a blast~", "Looks so fun—count me in too!"),
        "playmate_clone_chat": ("Wait, did I hear {name} complimenting me~", "What are you two whispering about? Tell me too!"),
        "playmate_host_pat": ("Pat pat {name}'s tiny head—good kitty~", "Head rubs for {name}, stay happy today~", "Come here, Big Sis has head pats for you~"),
        "playmate_clone_train": ("Choo-choo! Big Sis is leading the train—stay right behind me~", "All aboard the desktop parade—follow Big Sis!"),
        "playmate_clone_wave": ("Big Sis finishes the wave—10/10 relay!", "Whoa! Such a smooth wave from everyone—yay!"),
        "playmate_snack_party": ("Fish snack time! Line up and dig in~", "My treat! Plenty of dried fish for everyone~"),
        "playmate_group_huddle": ("Whoa!! Surrounded by mini-clone hugs~", "So warm and cozy—best group cuddle ever~"),
        "playmate_twin_mirror": ("Whoa! Twin {name} mirror dance—I'm seeing double~", "100% sync! Wait, which one is the real {name}~", "Identical {name}s—double cuteness overload!"),
        "playmate_mini_me_mimic": ("Eek! Mini-me is ridiculously adorable~", "Big & Mini {name} together—I wanna squish those cheeks~", "Hey, you nailed my pose way too well!"),
        "playmate_tea_party": ("Ding~ Tea party's open, gather round the table!", "Black tea & strawberry cake—sweetest break with everyone~"),
        "playmate_tea_party_interact": ("Another cup of warm fruit tea—help yourselves~", "Thanks for refilling! The whole desk smells like tea~"),
        "playmate_campfire_night": ("Campfire's glowing—marshmallow & story time!", "Stargazing by the fire makes the night feel so cozy~"),
        "playmate_campfire_night_interact": ("Crackling flames—don't scorch those marshmallows~", "Added a fresh log—golden crispy marshmallows incoming!"),
        "playmate_art_studio": ("Ooh, painting my portrait? Let me strike a pose!", "Desktop studio open—make sure to draw Big Sis extra cute!"),
        "playmate_art_studio_interact": ("Whoa, spot-on portrait! Hanging this front and center~", "Ta-da! Another masterpiece—you're all little geniuses!"),
        "playmate_cloud_nap": ("Fluffy cloud nest is set—nap huddle time~", "Soft cloud cushion and starry blanket—so peaceful~"),
        "playmate_cloud_nap_interact": ("Tucked the starry blanket tight—sweet dreams~", "Cloud's extra fluffy now—makes me sleepy too~"),
        "playmate_cloud_nap_wake": ("Phew—best nap ever! Big stretch and full power~", "Wakey wakey! That cloud nest was heavenly!"),
        "fast": ("Whoa, {rate} tok/s! Antigravity warp speed!", "{rate} tok/s—faster than the wind!"),
        "quota_low": ("Only {quota}% quota left—pace it gently~", "Heads up: {quota}% model quota remaining."),
        "quota_critical": ("Quota almost empty ({quota}%) — {reset}.", "Only {quota}% quota left! {reset}"),
        "quota_reset_soon": ("Snack restock incoming! Quota {reset}~", "Hang tight—quota {reset}, almost back to full!"),
        "quota_refilled": ("Quota refilled ({quota}%)! Full energy restored~", "Yay! Quota is back up to {quota}%!"),
        "context_high": ("Context is at {ctx}%—might be time for a fresh chat.", "Context window hit {ctx}%; getting a little cramped in here!"),
        "form": ("Detected {model}—switching to {form} form!", "{model} online—{form} form ready!"),
        "offline": ("Looks like Antigravity isn't open—I'll chill on my own for now.",),
        "update": ("New version v{version} is out on GitHub—one-click update in the sidebar~",),
        "update_commit": ("New commit ({sha}) on GitHub main—pull it anytime from the sidebar~",),
    },
    "ja": {
        "started": ("Antigravity 動き出したね！横でトークン見守ってるよ。", "新しい推論ターン、離陸〜！", "モデル思考中、tok/s を数えておくね。"),
        "finished": ("ターン完了！今回 {total} tokens だよ。", "おつかれさま〜このターン {total} tokens。", "着地成功！今回 {total} tokens、平均 {rate} tok/s だよ。"),
        "turn_error": ("あわわ、今エラーで止まっちゃった…一緒にログ見よう。", "ちょっと転んじゃったみたい…大丈夫、一緒に直そっ！"),
        "waiting": ("ねえねえ、Antigravity が確認待ちで止まってるよ！", "あっちで確認ポップアップか質問が待ってるみたい〜"),
        "subagent_start": ("お手伝い分身を召喚したよ！", "サブエージェント分身、出動〜！"),
        "subagent_many": ("わぁ、{count} 体の分身が一斉に稼働中！すごい迫力〜", "{count} 体の分身が並列作業中、効率爆上がり！"),
        "subagent_done": ("おつかれさま {name}、成果しっかり受け取ったよ〜", "{name} 完了報告バッチリ！連携満点〜", "すごいすごい、{name} きれいにやり遂げたね！"),
        "subagent_cheer": ("もう、{name} をなでたら私のこともなでてよね〜", "{name} にエールありがとう！", "{name} が褒められてやる気2倍になったよ〜"),
        "subagent_report": ("{name} から報告受信：{title}！", "了解 {name}、{title} は私が引き継ぐね〜"),
        "subagent_high_five": ("{name} とハイタッチ成功！息ぴったり〜", "ぎゅっ！{name} と相性バツグン〜", "やった！{name} との共同作業さいこう！"),
        "subagent_group_cheer": ("全員やる気マックス、いっくよー！", "分身たちとシンクロダンス、無敵だよ！"),
        "subagent_relay": ("{name} からの手がかりキャッチ〜", "ナイス {name}、すぐ統合するね！", "シグナル同期完了、このまま進もう〜"),
        "subagent_pet_rub": ("わぁ、{name} がごろごろとろけてる〜", "{name} の次は私の頭もなでてよね〜"),
        "subagent_trick": ("パチパチ！{name} のくるりん演技、満点〜", "わぁ！{name} のターンかわいい〜"),
        "subagent_gift_share": ("わぁ、{name} からミニプレゼントありがとう！", "{name} の小魚おやつゲット、元気満タン〜"),
        "subagent_clone_buddy": ("あはは、{name} たち息ぴったりだね〜", "みんなでハイタッチ、チームワーク最高！"),
        "subagent_clone_chat": ("あれ、{name} たち何のヒミツ話してるの〜？", "励まし合う声を聞くと私もやる気出るよ！"),
        "subagent_host_pat": ("よしよし {name}、今日もよく頑張ったね〜", "なでなで、{name} 満点だよ〜", "お姉さまのなでなで〜終わったら小魚食べよ！"),
        "subagent_clone_train": ("しゅっぽっぽ！お姉さまが先頭だよ、みんなついてきて〜", "分身ミニ列車、出発進行！きれいに並んでね〜"),
        "subagent_clone_wave": ("トリはお姉さま！全員ウェーブ大成功〜", "わぁ！息ぴったりのウェーブ、士気満タン！"),
        "subagent_snack_party": ("小魚おやつタイムだよー！みんな集まれ〜", "お姉さまのおごり！並んでひと休みしよ〜"),
        "subagent_group_huddle": ("わわっ！分身たちにぎゅーっと囲まれた、あったかい〜", "みんなにくっつかれて一気に全回復したよ！"),
        "subagent_twin_mirror": ("わぁ！双子 {name} のミラーダンス、シンクロ率100%〜", "そっくり {name} コンビ、可愛さも効率も2倍！"),
        "subagent_mini_me_mimic": ("きゃっ！ミニ {name} が同じポーズしてる、かわいすぎ〜", "大小 {name} ツーショットでやる気満タン！"),
        "subagent_tea_party": ("休憩タイム！デスクトップお茶会はじめるよ〜", "ちーん♪ クリームテーブル準備完了、苺ケーキどうぞ！"),
        "subagent_tea_party_interact": ("あたたかいフルーツティーおかわり〜お菓子もたっぷり！", "切りたて苺ケーキ、みんなでめしあがれ〜"),
        "subagent_campfire_night": ("あったか焚き火をつけたよ〜夜更かしのお供にマシュマロ焼こ！", "火を囲んでおしゃべり、深夜でもひとりじゃないよ！"),
        "subagent_campfire_night_interact": ("火が強くなったよ〜マシュマロ焦がさないでね！", "薪をくべてデスク全体がぽかぽか〜"),
        "subagent_art_studio": ("ミニ画室オープン！お姉さまの肖像画を描いてくれるの〜？", "よし、ポーズ決めたよ！キラキラ可愛く描いてね！"),
        "subagent_art_studio_interact": ("わぁ、そっくり！お姉さまの宝物にするね〜", "すごい！描き替えるたびにもっと可愛くなってる！"),
        "subagent_cloud_nap": ("ふわふわ雲ベッド広げたよ〜みんなでちょっとひと休みしよ！", "星柄毛布をかけて、すやすや充電タイム〜"),
        "subagent_cloud_nap_interact": ("みんなに星柄毛布をそっと掛けたよ〜いい夢見てね！", "雲クッションぽんぽん、ふかふかで気持ちいい〜"),
        "subagent_cloud_nap_wake": ("ふぅ〜お昼寝で元気フル充電！また一緒に進もうね！", "うーんっと伸び〜！リフレッシュ完了だよ！"),
        "playmate_summon": ("ひまだし {names} を呼んで遊ぼうっと〜", "ちーん♪ {names} が遊びに来てくれたよ〜", "息抜きタイム！{names} と一緒に遊ぼ〜"),
        "playmate_add": ("にぎやかなほど楽しいね！{names} ようこそ〜", "ちーん♪ {names} もパーティー参加〜"),
        "playmate_done": ("ばいばい {name}、また休憩のとき遊ぼうね〜", "{name} と遊べて楽しかった、またね！", "{name} はお休みタイム〜また今度ね！"),
        "playmate_cheer": ("もう、{name} の次は私もなでてよね〜", "あはは、{name} すっごく嬉しそう！"),
        "playmate_report": ("いいねいいね！{name} と一緒に{title}しよっ！", "うんうん、{name} と{title}するの好き〜"),
        "playmate_high_five": ("{name} とハイタッチ！最高の息抜き相棒〜", "やった！{name} と遊ぶの超たのしい〜"),
        "playmate_group_cheer": ("息抜きミニパーティー！みんなでジャンプ〜", "ランダム分身たちとパーティー開始！"),
        "playmate_relay": ("キャッチしたよ {name}！お返しのスター光線〜", "あはは {name} やんちゃだな〜もう一回！"),
        "playmate_pet_rub": ("わぁ、{name} 気持ちよさそうに目を細めてる〜", "ずるいっ！{name} の次は私もなでて〜"),
        "playmate_trick": ("パチパチ！{name} のくるりん超かわいい〜", "わぁ {name} 芸達者だね！アンコール！"),
        "playmate_gift_share": ("わぁ、{name} プチギフトありがとう！", "{name} の小魚もらっちゃった、ぎゅっ〜"),
        "playmate_clone_buddy": ("あはは、{name} たち仲良しで楽しそう〜", "にぎやかだね、私も混ぜて〜！"),
        "playmate_clone_chat": ("あれっ、今 {name} が私を褒めてたような〜", "何のヒミツ話してるの？私にも教えて！"),
        "playmate_host_pat": ("なでなで {name}、いい子いい子〜", "よしよし {name}、今日も楽しくね〜", "おいで、お姉さまがなでてあげる〜"),
        "playmate_clone_train": ("しゅっぽっぽ！お姉さまが先頭列車だよ、みんな続いて〜", "ちび列車出発進行！お姉さまの後ろに並んでね〜"),
        "playmate_clone_wave": ("トリはお姉さま！ウェーブ大成功〜", "わぁ！みんな揃ってキレイなウェーブ、イェーイ！"),
        "playmate_snack_party": ("小魚タイムだよー！みんな並んで食べよ〜", "お姉さまのおごり！ゆっくり食べてね〜"),
        "playmate_group_huddle": ("わわっ！分身たちにぎゅーっと囲まれた〜", "ぽかぽかで幸せいっぱい〜"),
        "playmate_twin_mirror": ("わぁ！双子 {name} のミラーダンス、目が回りそう〜", "シンクロ率満点！本物の {name} はどっち〜？", "そっくり {name} たち、可愛さ2倍アタック！"),
        "playmate_mini_me_mimic": ("きゃっ！ミニ版の私、かわいすぎない！？", "大小 {name} ツーショット！ほっぺぷにぷにしたい〜", "ちょっと、ポーズの真似うますぎるよっ！"),
        "playmate_tea_party": ("ちーん♪ お茶会オープン、みんなでテーブル囲もう！", "紅茶と苺ケーキ、みんなと一緒がいちばん甘いね〜"),
        "playmate_tea_party_interact": ("あたたかいフルーツティーおかわり〜お菓子もどうぞ！", "おかわりありがとう！デスクがいい香り〜"),
        "playmate_campfire_night": ("あったか焚き火タイム〜マシュマロ焼きながら語ろ！", "火を囲んで星空を見るの、なんだか落ち着くね〜"),
        "playmate_campfire_night_interact": ("火が大きくなったよ〜マシュマロ焦がさないでね！", "パチッと薪追加！外カリ中トロのマシュマロ完成〜"),
        "playmate_art_studio": ("えっ、私の肖像画を描いてくれるの？ポーズ決めるね！", "ミニ画室オープン〜お姉さまを可愛く描いてね！"),
        "playmate_art_studio_interact": ("わぁそっくり！一番目立つところに飾っちゃお〜", "じゃじゃーん！また新作、みんな天才画伯だね！"),
        "playmate_cloud_nap": ("ふわふわ雲のお昼寝ベッドだよ〜みんなでひと休み！", "雲クッションと星柄毛布、ぽかぽか安心〜"),
        "playmate_cloud_nap_interact": ("星柄毛布しっかり掛けたよ〜いい夢みてね！", "雲をぽんぽんしてふっくら〜私も眠くなっちゃった〜"),
        "playmate_cloud_nap_wake": ("ふぅ〜ぐっすり眠れた！伸びして元気満タン〜", "おはよ〜雲のお昼寝ベッド最高すぎたね！"),
        "fast": ("はやっ！{rate} tok/s、反重力ブースト中〜", "{rate} tok/s、風より速いよ！"),
        "quota_low": ("クォータ残り {quota}% だよ、大事に使おうね。", "お知らせ：現在のモデル残量は {quota}% です。"),
        "quota_critical": ("クォータ残りわずか（{quota}%）、{reset}。", "残量あと {quota}%！{reset}"),
        "quota_reset_soon": ("もうすぐ回復！クォータ {reset}〜", "あと少し、{reset} で全回復だよ！"),
        "quota_refilled": ("クォータ満タン回復（{quota}%）！元気全開〜", "やった！残量 {quota}% まで戻ったよ！"),
        "context_high": ("コンテキスト {ctx}% 到達、新しいチャットにしてもいいかも。", "コンテキスト窓 {ctx}% だよ、ちょっとぎゅうぎゅうかも。"),
        "form": ("{model} を検知、{form} フォームへチェンジ！", "{model} 稼働中、{form} フォーム出番だよ。"),
        "offline": ("Antigravity まだ開いてないみたい、ちょっと一人で遊んでるね。",),
        "update": ("GitHub に新バージョン v{version} が届いてるよ、サイドバーから更新できるよ〜",),
        "update_commit": ("GitHub main に新コミット（{sha}）あり！サイドバーからワンクリック更新できるよ〜",),
    },
}

GREETING_LINES: dict[str, dict[str, str]] = {
    "en": {
        "fest_newyear": "Happy New Year! Fresh code and zero bugs ahead~",
        "fest_national": "Happy holiday! Don't forget to take a real break too~",
        "fest_halloween": "Trick or fish snacks! Happy Halloween~",
        "fest_christmas": "Merry Christmas! Here's a warm festive gift for you~",
        "fest_spring": "Happy Lunar New Year! Wishing you clean builds and green tests~",
        "fest_lantern": "Happy Lantern Festival! Enjoy a sweet treat before coding~",
        "fest_dragonboat": "Happy Dragon Boat Festival! Take a breather and enjoy~",
        "fest_midautumn": "Happy Mid-Autumn Festival! Look at the bright moon and rest early~",
        "late_night": "It's past midnight—get some sleep and pick up fresh tomorrow~",
        "morning": "Good morning! Ready to crush today's tasks together~",
        "noon": "Good noon! Remember to grab lunch and recharge!",
        "afternoon": "Good afternoon~ Brew some tea or coffee and stay in flow!",
        "evening": "Good evening! Great work today—I'll keep you company tonight too.",
        "night": "Getting late—rest your eyes and wrap up soon, okay?",
    },
    "ja": {
        "fest_newyear": "あけましておめでとう！新年もバグゼロでいこうね〜",
        "fest_national": "祝日おめでとう！お休みもしっかりリフレッシュしてね〜",
        "fest_halloween": "小魚くれなきゃいたずらするよっ！ハッピーハロウィン〜",
        "fest_christmas": "メリークリスマス！あったかいプレゼントをどうぞ〜",
        "fest_spring": "春節おめでとう！今年も一発ビルド成功しますように〜",
        "fest_lantern": "元宵節おめでとう！甘いお団子食べてからコード書こっ〜",
        "fest_dragonboat": "端午節おめでとう！ちまき食べてパワーチャージしよ〜",
        "fest_midautumn": "中秋の名月だね！今夜は月が丸いから早めに休もうね〜",
        "late_night": "もう深夜だよ〜そろそろ寝て、明日また続きをやろうね！",
        "morning": "おはよう！今日も一緒にタスクをサクサク片付けよ〜",
        "noon": "こんにちは！お昼ごはんちゃんと食べてね！",
        "afternoon": "お疲れさま〜お茶かコーヒー淹れて集中モードいこっ！",
        "evening": "こんばんは！今日も一日おつかれさま、夜もそばにいるよ。",
        "night": "夜更けだね、目を労わってキリのいいところで休もうね。",
    },
}

AUTONOMY_LINES: dict[str, dict[str, tuple[str, ...]]] = {
    "en": {
        "hop": ("Hopping onto the Antigravity window to watch!", "Jumping up top to cheer the model on~"),
        "wake": ("Hmm? Work time? I'm awake!", "Antigravity's moving—I'm up too!"),
        "nap": ("Antigravity's been quiet for a while… time for a catnap.", "Nobody's coding… guess I'll curl up for a nap."),
        "tired": ("Quota's down to {quota}%, feeling a bit sleepy……", "Yawn—{quota}% quota left, let's save energy."),
        "recharged": ("Quota's back to full—full power ahead!", "Full recharge! Quota just reset!"),
        "stretch": ("You've been at it for {minutes} minutes—stand up and stretch~", "{minutes} minutes straight! Grab a sip of water?"),
        "greet": ("Antigravity's online! What are we building today?", "Spotted Antigravity—ready to code alongside you!"),
    },
    "ja": {
        "hop": ("Antigravity ウィンドウの上から見守るね！", "よいしょっ、上から応援してるよ〜"),
        "wake": ("んっ？作業開始？起きたよ！", "Antigravity が動いたね、私も起きる〜"),
        "nap": ("しばらく静かだし、ちょっとお昼寝しちゃお…", "誰もコード書いてないみたい……すやすや。"),
        "tired": ("クォータあと {quota}% かぁ、ちょっと眠いかも……", "ふぁあ……残量 {quota}%、節約していこ。"),
        "recharged": ("クォータ満タン回復！思いっきり使えるよ〜", "全回復っ！クォータがリセットされたよ！"),
        "stretch": ("もう {minutes} 分ぶっ通しだよ、立ち上がって伸びしよ〜", "{minutes} 分連続作業中！お水一口飲んで休もう？"),
        "greet": ("Antigravity 起動したね！今日は何を作るの？", "Antigravity 発見！いつでも並走準備OKだよ〜"),
    },
}


# ---------------------------------------------------------------------------
# Desktop Scene Props (4 scenes)
# ---------------------------------------------------------------------------

SCENE_PROP_TEXT: dict[str, dict[str, dict[str, Any]]] = {
    "en": {
        "tea_party": {
            "label": "Tea Party",
            "tooltip": "🫖 Afternoon Tea Party · Left-click to refill/slice cake · Right-click to dismiss",
            "click_lines": ("Ding~ Fresh fruit tea refill!", "Strawberry cake sliced~", "Warm scones served!", "Another cup of black tea~"),
        },
        "campfire_night": {
            "label": "Campfire",
            "tooltip": "🏕️ Starry Campfire Night · Left-click to stoke/roast · Right-click to put out",
            "click_lines": ("Crackle~ Added a warm log!", "Golden toasted marshmallow~", "Flames dancing warmly!", "One more sweet skewer~"),
        },
        "art_studio": {
            "label": "Art Studio",
            "tooltip": "🎨 Mini Art Studio · Left-click for a new portrait · Right-click to close",
            "click_lines": ("New portrait finished!", "Fresh canvas ready~", "Added sparkly star trim!", "Big Sis looks so cute here~"),
        },
        "cloud_nap": {
            "label": "Cloud Nap",
            "tooltip": "☁️ Cloud Nap Nest · Left-click to tuck blanket/fluff cloud · Right-click to wake",
            "click_lines": ("Starry blanket tucked~", "Fluffed the cloud cushion!", "Warm and cozy, sweet dreams~", "Tucked the corner snug~"),
        },
    },
    "ja": {
        "tea_party": {
            "label": "お茶会",
            "tooltip": "🫖 アフタヌーンティー会 · 左クリックでおかわり／ケーキ · 右クリックで片付け",
            "click_lines": ("ちーん♪ フルーツティーおかわり！", "苺ケーキ切り分けたよ〜", "焼きたてスコーンどうぞ！", "あたたかい紅茶もう一杯〜"),
        },
        "campfire_night": {
            "label": "焚き火",
            "tooltip": "🏕️ 星空の焚き火ナイト · 左クリックで薪追加／焼きマシュマロ · 右クリックで消火",
            "click_lines": ("パチッ♪ あったか薪を追加！", "マシュマロこんがり焼けたよ〜", "炎がぽかぽか揺れてる！", "もう1本マシュマロ焼こっ〜"),
        },
        "art_studio": {
            "label": "ミニ画室",
            "tooltip": "🎨 ミニアトリエ · 左クリックで新作ポートレート · 右クリックで片付け",
            "click_lines": ("新作ポートレート完成！", "新しいキャンバスに描くよ〜", "キラキラ星枠をプラス！", "このお姉さま超かわいい〜"),
        },
        "cloud_nap": {
            "label": "雲お昼寝",
            "tooltip": "☁️ ふわふわ雲のお昼寝 · 左クリックで星柄毛布／雲ぽんぽん · 右クリックで起床",
            "click_lines": ("星柄毛布をそっと掛けたよ〜", "雲クッションふかふか！", "ぽかぽか、いい夢みてね〜", "毛布の端をトントン〜"),
        },
    },
}


def scene_prop_text(kind: str, *, lang: str | None = None) -> dict[str, Any] | None:
    code = _code(lang)
    if code == "zh":
        return None
    return SCENE_PROP_TEXT.get(code, {}).get(kind)


# ---------------------------------------------------------------------------
# Subagent Clones localized chatter, tooltips, and host call name
# ---------------------------------------------------------------------------

CLONE_HOST_CALL: dict[str, str] = {"zh": "姐姐", "en": "Big Sis", "ja": "お姉さま"}

CLONE_POOLS: dict[str, dict[str, Any]] = {
    "en": {
        "summon": ("Copy that! On it~", "Checking right away!", "Leave it to me!", "Mini-clone ready~"),
        "click": ("Thanks! Full energy!", "Head-pat boost ×2!", "Hehe, keeping at it!", "Got your cheer, go!"),
        "relay": ("Found a clue!", "Syncing to {host}~", "Got this part covered!", "Results packed up!"),
        "handoff": ("All done! Handing in~", "Report complete, signing off!", "Over to {host}~"),
        "high_five": ("High-five! Dream team~", "Snuggle high-five!", "Yay! Best partners~"),
        "group_cheer": ("Full squad takeoff!", "Team energy maxed~", "Let's go together!"),
        "play_summon": ("Hey! Came to play with {host}~", "Break time—let's play!", "Random clone dropping in~", "Free time—hi there!"),
        "play_click": ("Hehe, that tickles~", "Pat me once more!", "Spinning with joy~", "Snuggles! Best day ever"),
        "play_relay": ("Catch this star orb~", "Let's see who jumps higher!", "Sunbathing feels great~", "Launching a heart orb!"),
        "play_handoff": ("So fun—see you next time~", "Hopping back to rest, bye!", "Call me next break~"),
        "play_high_five": ("High-five! Best playmate", "Snuggles! 10/10 buddy~", "Yay! Having a blast~"),
        "play_group_cheer": ("Break party starts now~", "Bounce bounce together!", "Chill squad forever~"),
        "pet_rub": ("Aww… feels so nice~", "Purr purr, don't stop!", "Melting from head rubs~", "Head rubs are the best!"),
        "trick": ("Watch my little spin~", "Ta-da! Fancy move!", "Look at this, {host}!", "Tap-tap, dance time!"),
        "gift_share": ("Little gift for {host}!", "Saved fish snacks for {host}", "Sneaking you a star candy~", "Great work {host}, take this!"),
        "clone_buddy": ("Snuggles! Best duo~", "Hehe, crisp high-five!", "Double sync, double speed!", "Let's play with {host}~"),
        "host_pat_clone": ("{host} patted my head~", "Hehe, {host}'s hand is warm", "Purr purr, love {host}!", "So comfy, more pats {host}~"),
        "train_leader": ("Choo-choo! Mini train go~", "Follow me, parade time!", "All aboard the train~"),
        "train_follower": ("Lined up right behind!", "Choo-choo, rolling out~", "Coming! Don't leave me!"),
        "wave_chant": ("One!", "Two!", "Three!", "Lift-off!", "Relay!", "Yay—!"),
        "wave_baton": "Over to {host}!",
        "snack_rush": ("Ooh! Fish snacks!", "Coming, {host}!", "Save one for me~"),
        "snack_eat": ("Nom nom, so good!", "Thanks for treats, {host}~", "Fish snacks rule!"),
        "huddle_call": ("{host} cuddle time!", "Group hug for {host}~", "Surround {host}!"),
        "huddle_purr": ("Love you best, {host}~", "So soft and warm!", "Best cuddles with {host}"),
        "twin_mirror_pairs": (
            ("Wait—is that me in a mirror?", "Hehe, I'm your twin!"),
            ("Guess who's the real me?", "Can {host} tell us apart?"),
            ("Left-right mirror sync!", "100% synchronization~"),
            ("Twin telepathy!", "Identical & twice as cute~"),
        ),
        "triplet_chorus": ("Triplets debut on stage!", "100% in sync~", "Guess which one is real?"),
        "mini_me": ("Look! I'm mini {host}!", "Big & Mini {host} together~", "Matching {host} head to toe!", "Copying {host}'s pose!"),
        "tea_party": ("Tea & strawberries rule!", "Try this cake, {host}!", "Tea time is pure bliss~", "This fruit tea smells amazing!"),
        "tea_click": ("Thanks for the refill!", "Ooh, fresh pastries!", "Strawberry cake is so sweet~"),
        "campfire": ("Campfire's super cozy~", "Marshmallow's gooey now!", "Stars are bright tonight~", "Story time with {host}~"),
        "campfire_click": ("So toasty! Brighter flames!", "Golden brown marshmallow~", "Warm & peaceful by the fire!"),
        "art_studio": ("Painting {host}'s portrait!", "Making the eyes sparkle~", "Adding starry highlights!", "Hold still {host}, almost done!"),
        "art_click": ("Ta-da! New piece ready~", "{host} looks adorable here!", "Let's paint another one!"),
        "cloud_nap": ("Cloud's so fluffy… zzz", "Napping with {host}~", "Blanket tucked, Zzz", "Soft & dreamy cloud~"),
        "cloud_click": ("Warm blanket, purr~", "Thanks for tucking us in~", "So soft… five more mins"),
        "clone_chat_pairs": (
            ("Secretly praising {host}~", "{host} is the coolest!"),
            ("Splitting my fish snack~", "Ooh thanks, yummy!"),
            ("High-jump challenge!", "Bet I jump higher~"),
            ("Let's make {host} smile!", "Yes! Let's go!"),
            ("Quick stretch break~", "Phew—recharged!"),
        ),
        "work_chat_pairs": (
            ("Almost done checking this~", "Nice! I'll pick up next~"),
            ("Synced clues over to you!", "Got it, verifying now~"),
            ("Got {host}'s back together!", "Yep, 10/10 teamwork~"),
        ),
        "mood_HEAD_PAT": ("Pat me too~", "{host} got praised~", "So jelly, me next!"),
        "mood_PET_PURR": ("{host} looks so happy~", "I want snuggles too!"),
        "mood_EATING": ("Smells yummy! Save a bite~", "I want snacks after work!", "Share fish with me, {host}!"),
        "mood_CELEBRATE": ("Yay! Celebrate together~", "Way to go, {host}!"),
        "mood_HAPPY": ("When {host} smiles, I smile!",),
        "mood_SULK": ("Don't sulk, {host}…", "Working faster to cheer you up!"),
        "mood_ANGRY": ("Eek! {host} is mad…", "Being extra good right now!"),
        "mood_WAITING_USER": ("{host} is waiting on you!", "Check the prompt dialog~"),
        "mood_DRAGGING": ("Whoa, careful with {host}!", "Wheee—flying!"),
        "mood_SLEEPING": ("Shhh… {host} is napping", "Sweet dreams, {host}~"),
        "mood_PERCH_SLEEP": ("Shhh… {host} is dozing", "Quietly keeping watch~"),
        "mood_DIZZY": ("Whoa, {host} looks dizzy!", "Catching my breath too…"),
        "tip_farewell_play": "Playmate farewell · {title}",
        "tip_farewell_work": "Subagent handoff · {title}",
        "default_title_play": "Idle Playmate",
        "default_title_work": "Subagent #{idx}",
        "tip_head_play": "Random Playmate · {title}",
        "tip_head_work": "Subagent Clone · {title}{model}",
        "tip_body_play": "Click: pat · Rub: purr · Wheel: trick · Mid-click: gift\nDouble-click: play · Drag to {host}/friend · Right-click: party",
        "tip_body_work": "Click: cheer · Rub: purr · Wheel: trick · Mid-click: gift\nDouble-click: report · Drag to {host}/friend · Right-click: party",
    },
    "ja": {
        "summon": ("了解！すぐ取りかかるね〜", "さっそく調べてくる！", "まかせて！", "ちび分身、準備OK〜"),
        "click": ("ありがとう！やる気満タン", "なでなで効率2倍！", "えへへ、頑張るね！", "応援キャッチ、いくよ！"),
        "relay": ("手がかり発見！", "{host} へ同期するよ〜", "ここは私にまかせて！", "結果まとめたよ！"),
        "handoff": ("完了！提出するね〜", "報告おわり、おつかれ！", "{host} にバトンタッチ〜"),
        "high_five": ("ハイタッチ！息ぴったり〜", "ぎゅっ！連携満点！", "やった！最高の相棒〜"),
        "group_cheer": ("全員出撃、テイクオフ！", "チームやる気MAX〜", "みんなでいくよー！"),
        "play_summon": ("やっほ！{host} と遊びにきた〜", "休憩タイム、遊ぼっ！", "ランダム分身おじゃましまーす", "ひまだし集合っ！"),
        "play_click": ("えへへ、くすぐったいよ〜", "もう一回なでてっ！", "嬉しくてくるくる〜", "ぎゅっ！今日サイコー"),
        "play_relay": ("いくよ！スターボール〜", "ジャンプ競争しよっ！", "ひなたぼっこ気持ちいい〜", "ハート球発射っ！"),
        "play_handoff": ("楽しかった、また今度ね〜", "ポケットに戻るね、ばいばい！", "ひまな時また呼んでね〜"),
        "play_high_five": ("ハイタッチ！遊び仲間サイコー", "ぎゅっ！相性バツグン〜", "やった！超たのしい〜"),
        "play_group_cheer": ("息抜きパーティー開幕〜", "みんなでぴょんぴょん！", "まったり隊ばんざい〜"),
        "pet_rub": ("うわぁ…気持ちいいよ〜", "ごろごろ、止めないでっ", "なでなででとろけちゃう〜", "頭なでなで大好き！"),
        "trick": ("くるりんターン見て〜", "じゃじゃーん！決めポーズ", "{host} これ見て見て！", "とんとんっ、ダンスタイム"),
        "gift_share": ("{host} にミニギフト！", "{host} に取っておいた小魚", "こっそり星キャンディ〜", "{host} おつかれさま、どうぞ"),
        "clone_buddy": ("ぎゅっ！最強コンビ〜", "えへへ、ハイタッチ成功！", "息ぴったりで効率2倍！", "一緒に {host} と遊ぼ〜"),
        "host_pat_clone": ("{host} になでられた〜", "えへへ、{host} の手あったかい", "ごろごろ、{host} だーいすき", "気持ちいい、もっとなでて {host}"),
        "train_leader": ("しゅっぽっぽ！列車出発〜", "ついてきて、パレードだよ！", "ちび列車、発車しまーす"),
        "train_follower": ("きれいに並んでついてくよ！", "しゅっぽっぽ、出発〜", "待って待って、はぐれないよ！"),
        "wave_chant": ("いち！", "にっ！", "さん！", "テイクオフ！", "リレー！", "イェーイ！"),
        "wave_baton": "{host} にバトンタッチ！",
        "snack_rush": ("わぁ！小魚だー！", "今いくよ {host}！", "私の分も残して〜"),
        "snack_eat": ("もぐもぐ、おいしっ！", "{host} ごちそうさま〜", "小魚さいこう！"),
        "huddle_call": ("{host} ぎゅーっ！", "{host} をハグしにきた〜", "{host} を囲めー！"),
        "huddle_purr": ("{host} いちばん好き〜", "ふわふわあったかい！", "{host} とくっつくの幸せ"),
        "twin_mirror_pairs": (
            ("あれ？鏡の中に私がいる！？", "えへへ、双子だよっ！"),
            ("本物の私はどっちでしょう？", "{host} 見分けられるかな〜"),
            ("左右対称、完璧シンクロ！", "シンクロ率 100%〜"),
            ("双子のテレパシー！", "そっくりで可愛さ2倍〜"),
        ),
        "triplet_chorus": ("多つ子ユニットデビュー！", "シンクロ率 100%〜", "本物はどーれだ？"),
        "mini_me": ("見て！ミニ {host} だよ！", "大小 {host} 共演〜", "{host} とおそろいだよっ", "{host} のポーズ真似っこ！"),
        "tea_party": ("紅茶と苺ケーキ最高！", "{host} このケーキ食べて〜", "お茶会いちばん幸せ〜", "フルーツティーいい香り！"),
        "tea_click": ("おかわりありがとう〜", "わぁ！お菓子増えたっ", "苺ケーキあま〜い♪"),
        "campfire": ("焚き火ぽかぽか〜", "マシュマロとろけてきた！", "今夜は星がきれいだよ", "{host} のお話ききたい〜"),
        "campfire_click": ("あったかい！火が元気〜", "マシュマロこんがり♪", "ぽかぽかで安心する〜"),
        "art_studio": ("{host} の肖像画を描くよ！", "お目々キラキラに〜", "星の光カラーをぬりぬり！", "{host} じっとしててね！"),
        "art_click": ("じゃじゃーん！新作完成〜", "この {host} 超かわいい！", "もう1枚描いちゃおう！"),
        "cloud_nap": ("雲ふわふわ…すやぁ", "{host} と一緒にお昼寝", "毛布ぽかぽか Zzz", "もふもふ気持ちいい〜"),
        "cloud_click": ("毛布あったかい、ごろごろ", "掛けてくれてありがとう〜", "ふわふわ…あと5分だけ"),
        "clone_chat_pairs": (
            ("こっそり {host} を褒めよ〜", "{host} ほんとすごいよね！"),
            ("小魚半分あげる〜", "わぁありがとう、おいしっ！"),
            ("ジャンプ高さ勝負っ！", "絶対私が勝つもんね〜"),
            ("一緒に {host} を笑顔にしよ！", "うんうん、いっくよー！"),
            ("ちょっと背伸び休憩〜", "ふぅ〜元気回復！"),
        ),
        "work_chat_pairs": (
            ("こっちもうすぐ調査完了〜", "ナイス！次ひきつぐね〜"),
            ("手がかり送ったよ！", "了解、すぐ確認するね〜"),
            ("一緒に {host} を支えよ！", "うん、連携ばっちり〜"),
        ),
        "mood_HEAD_PAT": ("私もなでて〜", "{host} 褒められてる〜", "いいなぁ、私も！"),
        "mood_PET_PURR": ("{host} すっごく幸せそう〜", "私もすりすりしたい！"),
        "mood_EATING": ("いい匂い！一口ちょうだい〜", "作業おわったら私も食べたい！", "{host} 小魚わけて〜"),
        "mood_CELEBRATE": ("やった！一緒にお祝い〜", "さすが {host}！"),
        "mood_HAPPY": ("{host} が笑顔だと私も嬉しい",),
        "mood_SULK": ("怒らないで {host}…", "急いで進めてご機嫌とるね！"),
        "mood_ANGRY": ("ひゃっ！{host} おこってる…", "おりこうに作業しよっ！"),
        "mood_WAITING_USER": ("{host} が確認待ってるよ！", "ポップアップ見てみて〜"),
        "mood_DRAGGING": ("わわっ {host} 気をつけて！", "ひゅー、空とんでる！"),
        "mood_SLEEPING": ("しーっ…{host} お昼寝中", "いい夢みてね {host}〜"),
        "mood_PERCH_SLEEP": ("しーっ…{host} うとうと中", "静かに見守ってるね〜"),
        "mood_DIZZY": ("うわ、{host} 目が回ってる！", "こっちまでくらくら…"),
        "tip_farewell_play": "遊び仲間お見送り · {title}",
        "tip_farewell_work": "分身バトンタッチ · {title}",
        "default_title_play": "おひまな遊び仲間",
        "default_title_work": "サブエージェント #{idx}",
        "tip_head_play": "ランダム遊び仲間 · {title}",
        "tip_head_work": "サブエージェント分身 · {title}{model}",
        "tip_body_play": "クリック: なでる · こする: ごろごろ · ホイール: 芸 · 中クリック: 贈り物\nダブルクリック: 遊ぶ · {host}/仲間へドラッグ · 右クリック: パーティー",
        "tip_body_work": "クリック: 応援 · こする: ごろごろ · ホイール: 芸 · 中クリック: 贈り物\nダブルクリック: 報告 · {host}/仲間へドラッグ · 右クリック: パーティー",
    },
}


def clone_host_call(*, lang: str | None = None) -> str:
    return CLONE_HOST_CALL.get(_code(lang), "姐姐")


def clone_pool(key: str, default: Any, *, lang: str | None = None) -> Any:
    code = _code(lang)
    if code == "zh":
        return default
    return CLONE_POOLS.get(code, {}).get(key, default)
