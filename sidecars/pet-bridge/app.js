/**
 * AGY Pet sidecar frontend controller (trilingual: zh / en / ja + auto).
 */

(function () {
  const $ = (id) => document.getElementById(id);
  const fetcher = window.sidecar?.fetch ? window.sidecar.fetch : window.fetch.bind(window);

  const I18N = {
    zh: {
      htmlLang: 'zh-CN',
      timeLocale: 'zh-CN',
      pageTitle: 'AGY 桌宠',
      brandTitle: 'AGY 桌宠',
      statusChecking: '正在检测桌宠状态…',
      statusRunning: '桌宠运行中（配置实时热同步）',
      statusStopped: '桌宠未运行',
      btnUpdateDefault: '↑ 新版更新',
      btnUpdateSha: '↑ 更新 ({sha})',
      btnUpdateVer: '↑ 更新 v{ver}',
      tipUpdateSha: 'GitHub 主分支有新提交 {sha}（本地 {local}），点击安全拉取',
      tipUpdateVer: '发现新版本 v{ver}（当前 v{local}），点击自动更新',
      btnUpdating: '更新中…',
      btnGithubLabel: '打开 GitHub 仓库',
      btnGithubTitle: '打开 GitHub 仓库 (Gengetau/antigravity-pet)',
      btnLaunchDefault: '启动 / 唤醒',
      btnFocusPet: '唤醒窗口',
      btnStartPet: '启动桌宠',
      cardContext: '当前会话上下文',
      waitingSession: '等待会话数据…',
      ctxLabel: '上下文占用（不含思考 token）',
      kpiSpeed: '流式速率',
      kpi5h: '5h 限额',
      kpiWeek: '周限额',
      kpiCache: '缓存命中',
      cardForm: '桌宠形态',
      formGroupLabel: '桌宠形态选择',
      followModel: '跟随模型自动切换',
      cardSettings: 'HUD 悬浮条与联动设置',
      fieldLanguage: '界面语言',
      langAuto: '自动跟随系统 (Auto)',
      fieldPinned: '监控会话',
      autoFollowSession: '自动跟随当前活跃会话',
      fieldAppearance: 'HUD 外观',
      appDialog: '对话框卡片（默认）',
      appCapsule: '暗色胶囊',
      appGlass: '轻透毛玻璃',
      appSeamless: '无边框透明底',
      fieldHudMode: 'HUD 位置',
      modeAttached: '跟随桌宠',
      modeFloating: '独立悬浮（可拖到输入框旁）',
      optHudEnabled: '显示 HUD 悬浮条',
      optHudHover: '悬停桌宠时显示 HUD（平时隐藏）',
      optHudLocked: '锁定悬浮坐标',
      optAutonomy: '自主爬窗与互动',
      optReactions: '对速率/限额做出反应',
      optProgressBubbles: '阶段成果气泡弹窗（播报进展与完成节点）',
      optClones: '显示子代理小分身（复用角色素材）',
      optParticles: '互动与反应粒子特效',
      optEdgeDock: '贴边藏身与鼠标探头',
      optAiComments: 'AI 活台词（走本地最省档额度）',
      aiUsageSuffix: '（今日 {calls}/{max} 次）',
      optAutoLaunch: '插件启动时自动拉起桌宠',
      optCheckUpdates: '自动检查 GitHub 更新（版本与主分支提交）',
      footerDefault: '修改后约 1.5 秒内自动同步到桌面宠物',
      noSessionBadge: '无会话',
      noSessionTitle: '暂无活跃会话',
      modelEmpty: '当前模型：—',
      modelLine: '当前模型：{active}{last}',
      modelLastPart: ' · 最近一步：{last}',
      unknownModel: '未知模型',
      unknownVal: '未知',
      newChat: '新对话',
      runningPrefix: '生成中 · ',
      pinnedBadge: '已锁定会话',
      liveTrackBadge: '实时追踪',
      waitingUserBadge: '等你确认',
      subagentsSuffix: ' · {count} 子代理',
      focus_hook: 'Hook 实时锁定',
      focus_host: '侧边栏会话绑定',
      focus_view: '当前浏览标签',
      focus_input: '最近发送输入',
      focus_running: '正在生成',
      focus_recent: '最近活动会话',
      focus_project_empty: '新项目空白会话',
      msgLoadFailed: '读取侧边栏状态失败',
      msgSaving: '正在同步配置…',
      msgSaveFailed: '保存配置失败',
      msgSaved: '已写入配置，桌宠约 1.5s 内自动应用',
      msgWriteFailed: '写入配置失败',
      msgLaunching: '正在启动或唤醒桌宠…',
      msgLaunchSent: '已发送启动/唤醒请求',
      msgLaunchFailed: '启动失败：{error}',
      msgLaunchError: '启动请求异常',
      msgGithubOpened: '已在默认浏览器打开 GitHub 仓库',
      msgGithubFailed: '打开 GitHub 仓库失败',
      msgUpdating: '正在从 GitHub 拉取更新…',
      msgUpdateOk: '更新成功',
      msgUpdateIncomplete: '更新未完成',
      msgUpdateReqFailed: '更新请求失败',
      launchMissingMain: '未找到桌宠入口文件: {path}',
      launchMissingPython: '未找到可用的 Python 桌宠运行环境（需 Python 3.13+ 与 PySide6）',
      updNotGit: '当前目录非 Git 仓库，已打开 GitHub 页面手动下载',
      updDirty: '本地有未提交改动，为保护代码未覆盖，已打开 GitHub 页面',
      updWrongBranch: '当前处于分支 {branch}，请切回 main 后再一键更新',
      updSuccess: '已拉取 v{version}，重开桌宠并开关一次插件即可生效',
      updFailed: '自动更新失败（{detail}），已打开 GitHub 页面',
    },
    en: {
      htmlLang: 'en',
      timeLocale: 'en-US',
      pageTitle: 'AGY Pet',
      brandTitle: 'AGY Pet',
      statusChecking: 'Checking pet status…',
      statusRunning: 'Pet running (live hot-sync)',
      statusStopped: 'Pet not running',
      btnUpdateDefault: '↑ Update',
      btnUpdateSha: '↑ Update ({sha})',
      btnUpdateVer: '↑ Update v{ver}',
      tipUpdateSha: 'New commit {sha} on main (local {local}). Click to pull safely.',
      tipUpdateVer: 'New release v{ver} available (current v{local}). Click to update.',
      btnUpdating: 'Updating…',
      btnGithubLabel: 'Open GitHub repository',
      btnGithubTitle: 'Open GitHub repository (Gengetau/antigravity-pet)',
      btnLaunchDefault: 'Launch / Focus',
      btnFocusPet: 'Focus Pet',
      btnStartPet: 'Launch Pet',
      cardContext: 'Active Session Context',
      waitingSession: 'Waiting for session data…',
      ctxLabel: 'Context Usage (excl. thinking tokens)',
      kpiSpeed: 'Decode Speed',
      kpi5h: '5h Quota',
      kpiWeek: 'Weekly Quota',
      kpiCache: 'Cache Hit',
      cardForm: 'Pet Form',
      formGroupLabel: 'Select pet form',
      followModel: 'Follow active model',
      cardSettings: 'HUD & Companion Settings',
      fieldLanguage: 'Language',
      langAuto: 'Auto (System)',
      fieldPinned: 'Monitor Session',
      autoFollowSession: 'Auto-follow active session',
      fieldAppearance: 'HUD Style',
      appDialog: 'Speech Card (Default)',
      appCapsule: 'Dark Capsule',
      appGlass: 'Frosted Glass',
      appSeamless: 'Borderless Transparent',
      fieldHudMode: 'HUD Position',
      modeAttached: 'Attach to Pet',
      modeFloating: 'Floating (draggable)',
      optHudEnabled: 'Show HUD Bar',
      optHudHover: 'Show HUD on pet hover only',
      optHudLocked: 'Lock floating HUD position',
      optAutonomy: 'Autonomous climbing & interactions',
      optReactions: 'React to speed & quota changes',
      optProgressBubbles: 'Milestone progress popups (agent reports & steps)',
      optClones: 'Show subagent mini-clones',
      optParticles: 'Interaction & reaction particles',
      optEdgeDock: 'Edge hiding & cursor peeking',
      optAiComments: 'AI Live Quips (uses cheapest local tier)',
      aiUsageSuffix: ' ({calls}/{max} today)',
      optAutoLaunch: 'Auto-launch pet on plugin start',
      optCheckUpdates: 'Auto-check GitHub updates',
      footerDefault: 'Changes hot-sync to the desktop pet within ~1.5s',
      noSessionBadge: 'Idle',
      noSessionTitle: 'No active session',
      modelEmpty: 'Model: —',
      modelLine: 'Model: {active}{last}',
      modelLastPart: ' · Last step: {last}',
      unknownModel: 'Unknown model',
      unknownVal: 'unknown',
      newChat: 'New Chat',
      runningPrefix: 'Running · ',
      pinnedBadge: 'Pinned',
      liveTrackBadge: 'Live Tracking',
      waitingUserBadge: 'Waiting for You',
      subagentsSuffix: ' · {count} subagent(s)',
      focus_hook: 'Hook Live Lock',
      focus_host: 'Sidebar Session',
      focus_view: 'Active Tab',
      focus_input: 'Recent Input',
      focus_running: 'Generating',
      focus_recent: 'Recent Session',
      focus_project_empty: 'Blank Project Chat',
      msgLoadFailed: 'Failed to load sidebar state',
      msgSaving: 'Syncing settings…',
      msgSaveFailed: 'Failed to save settings',
      msgSaved: 'Saved — pet will hot-apply within ~1.5s',
      msgWriteFailed: 'Failed to write settings',
      msgLaunching: 'Launching or focusing pet…',
      msgLaunchSent: 'Launch / focus request sent',
      msgLaunchFailed: 'Launch failed: {error}',
      msgLaunchError: 'Launch request error',
      msgGithubOpened: 'Opened GitHub repository in browser',
      msgGithubFailed: 'Failed to open GitHub repository',
      msgUpdating: 'Pulling update from GitHub…',
      msgUpdateOk: 'Update complete',
      msgUpdateIncomplete: 'Update did not complete',
      msgUpdateReqFailed: 'Update request failed',
      launchMissingMain: 'Pet entrypoint not found: {path}',
      launchMissingPython: 'No usable Python environment found (requires Python 3.13+ & PySide6)',
      updNotGit: 'Not a Git repo — opened GitHub releases to download manually',
      updDirty: 'Uncommitted local changes detected — opened GitHub without overwriting',
      updWrongBranch: 'Currently on branch {branch}; switch to main before updating',
      updSuccess: 'Pulled v{version} — restart pet and toggle plugin once to apply',
      updFailed: 'Auto-update failed ({detail}) — opened GitHub page',
    },
    ja: {
      htmlLang: 'ja',
      timeLocale: 'ja-JP',
      pageTitle: 'AGY ペット',
      brandTitle: 'AGY ペット',
      statusChecking: 'ペット状態を確認中…',
      statusRunning: '稼働中（設定リアルタイム同期）',
      statusStopped: '未起動',
      btnUpdateDefault: '↑ 新規更新',
      btnUpdateSha: '↑ 更新 ({sha})',
      btnUpdateVer: '↑ 更新 v{ver}',
      tipUpdateSha: 'main ブランチに新コミット {sha}（ローカル {local}）。クリックで安全に取得',
      tipUpdateVer: '新バージョン v{ver} あり（現在 v{local}）。クリックで自動更新',
      btnUpdating: '更新中…',
      btnGithubLabel: 'GitHub リポジトリを開く',
      btnGithubTitle: 'GitHub リポジトリを開く (Gengetau/antigravity-pet)',
      btnLaunchDefault: '起動 / 表示',
      btnFocusPet: '前面に表示',
      btnStartPet: 'ペット起動',
      cardContext: '現在のセッション・コンテキスト',
      waitingSession: 'セッションデータ待機中…',
      ctxLabel: 'コンテキスト使用量（思考トークン除く）',
      kpiSpeed: '生成速度',
      kpi5h: '5時間枠',
      kpiWeek: '週間枠',
      kpiCache: 'キャッシュ率',
      cardForm: 'ペットのフォーム',
      formGroupLabel: 'ペットのフォーム選択',
      followModel: 'モデルに合わせて自動切替',
      cardSettings: 'HUD バー＆連携設定',
      fieldLanguage: '表示言語',
      langAuto: '自動（システム設定）',
      fieldPinned: '監視セッション',
      autoFollowSession: 'アクティブなセッションに自動追従',
      fieldAppearance: 'HUD 外観',
      appDialog: '吹き出しカード（標準）',
      appCapsule: 'ダークカプセル',
      appGlass: 'すりガラス風',
      appSeamless: '枠なし透過',
      fieldHudMode: 'HUD 配置',
      modeAttached: 'ペットに追従',
      modeFloating: '独立フロート（移動可）',
      optHudEnabled: 'HUD バーを表示',
      optHudHover: 'ペットにホバー時のみ HUD 表示',
      optHudLocked: 'フロート位置をロック',
      optAutonomy: '自律的な窓登り・アクション',
      optReactions: '速度やクォータ変化に反応',
      optProgressBubbles: '進捗マイルストーン吹き出し（中間報告・完了ノード）',
      optClones: 'サブエージェント分身を表示',
      optParticles: 'リアクション演出パーティクル',
      optEdgeDock: '画面端に隠れてひょっこり覗き見',
      optAiComments: 'AI ライブ一言（最安ローカル枠を使用）',
      aiUsageSuffix: '（本日 {calls}/{max} 回）',
      optAutoLaunch: 'プラグイン起動時にペットを自動起動',
      optCheckUpdates: 'GitHub の更新を自動確認',
      footerDefault: '変更は約 1.5 秒以内にデスクトップペットへ自動反映されます',
      noSessionBadge: '待機中',
      noSessionTitle: 'アクティブなセッションなし',
      modelEmpty: '使用モデル：—',
      modelLine: '使用モデル：{active}{last}',
      modelLastPart: ' · 直近ステップ：{last}',
      unknownModel: '不明なモデル',
      unknownVal: '不明',
      newChat: '新規チャット',
      runningPrefix: '生成中 · ',
      pinnedBadge: '固定セッション',
      liveTrackBadge: 'ライブ追跡',
      waitingUserBadge: '確認待ち',
      subagentsSuffix: ' · 分身 {count} 体',
      focus_hook: 'Hook ライブ固定',
      focus_host: 'サイドバー連携',
      focus_view: '表示中のタブ',
      focus_input: '直近の入力',
      focus_running: '生成中',
      focus_recent: '最近のセッション',
      focus_project_empty: '新規プロジェクト',
      msgLoadFailed: 'サイドバー状態の取得に失敗しました',
      msgSaving: '設定を同期中…',
      msgSaveFailed: '設定の保存に失敗しました',
      msgSaved: '保存完了（約 1.5 秒でペットに反映）',
      msgWriteFailed: '設定の書き込みに失敗しました',
      msgLaunching: 'ペットを起動または前面表示中…',
      msgLaunchSent: '起動／前面表示リクエストを送信しました',
      msgLaunchFailed: '起動失敗：{error}',
      msgLaunchError: '起動リクエストエラー',
      msgGithubOpened: 'ブラウザで GitHub リポジトリを開きました',
      msgGithubFailed: 'GitHub リポジトリを開けませんでした',
      msgUpdating: 'GitHub から更新を取得中…',
      msgUpdateOk: '更新が完了しました',
      msgUpdateIncomplete: '更新が完了しませんでした',
      msgUpdateReqFailed: '更新リクエストに失敗しました',
      launchMissingMain: 'エントリファイルが見つかりません: {path}',
      launchMissingPython: '利用可能な Python 環境が見つかりません（Python 3.13+ と PySide6 が必要）',
      updNotGit: 'Git リポジトリではないため、手動ダウンロード用に GitHub を開きました',
      updDirty: '未コミットの変更があるため上書きせず GitHub を開きました',
      updWrongBranch: '現在のブランチは {branch} です。main に切り替えてから更新してください',
      updSuccess: 'v{version} を取得しました。ペット再起動とプラグイン再切替で反映されます',
      updFailed: '自動更新に失敗しました（{detail}）。GitHub ページを開きました',
    },
  };

  function detectBrowserLang() {
    const raw = (navigator.languages && navigator.languages[0]) || navigator.language || '';
    const low = String(raw).toLowerCase().replace(/_/g, '-');
    if (!low) return 'zh';
    if (low.startsWith('ja') || low.startsWith('jp')) return 'ja';
    if (low.startsWith('zh')) return 'zh';
    return 'en';
  }

  function resolveUiLang(setting) {
    const raw = String(setting || 'auto').toLowerCase().replace(/_/g, '-');
    if (raw === 'zh' || raw === 'en' || raw === 'ja') return raw;
    if (raw.startsWith('ja')) return 'ja';
    if (raw.startsWith('en')) return 'en';
    if (raw.startsWith('zh')) return 'zh';
    return detectBrowserLang();
  }

  let activeLang = detectBrowserLang();
  let customStatusMsg = false;

  function t(key, vars) {
    const table = I18N[activeLang] || I18N.zh;
    let text = table[key] ?? I18N.zh[key] ?? key;
    if (vars && typeof vars === 'object') {
      for (const [k, v] of Object.entries(vars)) {
        text = text.replaceAll(`{${k}}`, String(v ?? ''));
      }
    }
    return text;
  }

  function applyStaticTranslations(lang) {
    activeLang = lang;
    const table = I18N[lang] || I18N.zh;
    document.documentElement.lang = table.htmlLang;
    document.title = table.pageTitle;
    document.querySelectorAll('[data-i18n]').forEach((el) => {
      const key = el.getAttribute('data-i18n');
      if (!key) return;
      if (el.id === 'status-msg' && customStatusMsg) return;
      el.textContent = t(key);
    });
    const ghBtn = $('btn-github');
    if (ghBtn) {
      ghBtn.setAttribute('aria-label', t('btnGithubLabel'));
      ghBtn.title = t('btnGithubTitle');
    }
    const formGrid = $('form-grid');
    if (formGrid) {
      formGrid.setAttribute('aria-label', t('formGroupLabel'));
    }
  }

  function setStatus(text, isCustom = true) {
    customStatusMsg = isCustom;
    $('status-msg').textContent = text;
  }

  function syncThemeSchemeFromBg() {
    const bg = getComputedStyle(document.documentElement).getPropertyValue('--background').trim();
    if (!bg) return;
    const probe = document.createElement('span');
    probe.style.color = bg;
    probe.style.display = 'none';
    document.body.appendChild(probe);
    const rgb = getComputedStyle(probe).color;
    probe.remove();
    const m = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(rgb);
    if (!m) return;
    const realLum = (0.2126 * Number(m[1]) + 0.7152 * Number(m[2]) + 0.0722 * Number(m[3])) / 255;
    document.documentElement.dataset.theme = realLum < 0.48 ? 'dark' : 'light';
  }

  window.addEventListener('message', (ev) => {
    if (ev.data?.type === 'theme-change') {
      requestAnimationFrame(syncThemeSchemeFromBg);
    }
  });

  function fmtTokens(n) {
    const v = Number(n || 0);
    if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`;
    if (v >= 1_000) return `${(v / 1_000).toFixed(1)}k`;
    return `${Math.round(v)}`;
  }

  function classifyWindow(bucket) {
    const text = `${bucket?.window || ''} ${bucket?.name || ''} ${bucket?.description || ''}`;
    if (/(?<!\d)5\s*h(?:ours?|rs?)?(?![a-z])|(?<!\d)5[-_ ]?hours?|five[-_ ]?hours?|PT5H|(?<!\d)18000s?(?!\d)|(?<!\d)5\s*小时|5\s*時間/i.test(text)) {
      return '5h';
    }
    if (/week|(?<!\d)7\s*d(?:ays?)?(?![a-z])|(?<!\d)7[-_ ]?days?|seven[-_ ]?days?|P7D|P1W|(?<!\d)604800s?(?!\d)|周|週|(?<!\d)7\s*天|七天/i.test(text)) {
      return 'week';
    }
    return '';
  }

  function pickQuota(buckets, modelLabel, kind, fallbackPct, fallbackReset) {
    const thirdParty = /(claude|gpt|oss|opus|sonnet)/i.test(modelLabel || '');
    const valid = (buckets || []).filter((b) => !b.disabled && typeof b.remainingPct === 'number' && classifyWindow(b) === kind);
    const groupMatched = valid.filter((b) => {
      const g = (b.group || '').toLowerCase();
      if (!g) return false;
      return thirdParty ? /(claude|gpt)/.test(g) : g.includes('gemini');
    });
    const pool = groupMatched.length ? groupMatched : valid;
    if (pool.length) {
      return pool.reduce((min, cur) => (cur.remainingPct < min.remainingPct ? cur : min)).remainingPct;
    }
    if (kind === '5h' && typeof fallbackPct === 'number') {
      const target = fallbackReset ? Date.parse(fallbackReset) : 0;
      const hours = target ? (target - Date.now()) / 3_600_000 : 0;
      if (hours <= 5.2) return fallbackPct;
    }
    if (kind === 'week' && typeof fallbackPct === 'number') {
      const target = fallbackReset ? Date.parse(fallbackReset) : 0;
      const hours = target ? (target - Date.now()) / 3_600_000 : 0;
      if (hours > 5.2) return fallbackPct;
    }
    return null;
  }

  let currentState = null;

  function renderForms(forms, agyConfig) {
    const grid = $('form-grid');
    const buttons = [];
    for (const f of forms || []) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = `form-btn${agyConfig.form === f.id ? ' active' : ''}`;
      const swatch = document.createElement('span');
      swatch.className = 'form-swatch';
      swatch.style.background = f.accent;
      const nameSpan = document.createElement('span');
      nameSpan.textContent = f.name;
      btn.append(swatch, nameSpan);
      btn.addEventListener('click', () => saveConfig({ form: f.id, follow_model: false }));
      buttons.push(btn);
    }
    grid.replaceChildren(...buttons);
  }

  function render(state) {
    currentState = state;
    const agy = state.agyConfig || {};
    const langSetting = agy.language || 'auto';
    applyStaticTranslations(resolveUiLang(langSetting));

    const selLang = $('sel-language');
    if (selLang) {
      selLang.value = ['auto', 'zh', 'en', 'ja'].includes(langSetting) ? langSetting : 'auto';
    }

    const dot = $('pet-dot');
    dot.classList.toggle('online', Boolean(state.petRunning));
    if (state.version) {
      $('ver-text').textContent = `v${state.version}`;
    }
    $('pet-status-text').textContent = state.petRunning ? t('statusRunning') : t('statusStopped');
    $('btn-launch').textContent = state.petRunning ? t('btnFocusPet') : t('btnStartPet');

    const updateBtn = $('btn-update');
    const upd = state.updateStatus || {};
    const showUpdate = Boolean(
      state.bridgeSettings?.checkUpdates !== false &&
        upd.hasUpdate &&
        (upd.latestVersion || upd.latestSha)
    );
    updateBtn.hidden = !showUpdate;
    if (showUpdate && !updateBtn.disabled) {
      const sameVer = Boolean(upd.latestVersion && upd.latestVersion === (upd.localVersion || state.version));
      const useSha = (!upd.latestVersion || sameVer) && Boolean(upd.latestSha);
      updateBtn.textContent = useSha
        ? t('btnUpdateSha', { sha: upd.latestSha })
        : t('btnUpdateVer', { ver: upd.latestVersion });
      updateBtn.title = useSha
        ? t('tipUpdateSha', { sha: upd.latestSha, local: upd.localSha || t('unknownVal') })
        : t('tipUpdateVer', { ver: upd.latestVersion, local: upd.localVersion || state.version || '0.2.0' });
    }

    renderForms(state.forms || [], agy);

    $('chk-follow-model').checked = Boolean(agy.follow_model);
    $('chk-hud-enabled').checked = Boolean(agy.hud_enabled);
    const hoverOnlyEl = $('chk-hud-hover-only');
    if (hoverOnlyEl) hoverOnlyEl.checked = Boolean(agy.hud_hover_only);
    $('chk-hud-locked').checked = Boolean(agy.hud_locked);
    $('chk-autonomy').checked = Boolean(agy.autonomy);
    $('chk-reactions').checked = Boolean(agy.reactions);
    const progEl = $('chk-progress-bubbles');
    if (progEl) progEl.checked = agy.progress_bubbles !== false;
    $('chk-subagent-clones').checked = agy.subagent_clones !== false;
    $('chk-particles').checked = agy.particles !== false;
    $('chk-edge-dock').checked = agy.edge_dock !== false;
    $('chk-ai-comments').checked = Boolean(state.bridgeSettings?.aiComments);
    const aiUsage = state.aiBudgetUsage;
    const aiLabel = $('lbl-ai-comments');
    if (aiLabel) {
      const suffix = aiUsage && aiUsage.calls > 0
        ? t('aiUsageSuffix', { calls: aiUsage.calls, max: aiUsage.maxPerDay })
        : '';
      aiLabel.textContent = `${t('optAiComments')}${suffix}`;
    }
    $('chk-auto-launch').checked = Boolean(state.bridgeSettings?.autoLaunchPet);
    $('chk-check-updates').checked = state.bridgeSettings?.checkUpdates !== false;
    $('sel-appearance').value = agy.hud_appearance || 'dialog';
    $('sel-hud-mode').value = agy.hud_mode || 'attached';

    const live = state.live || {};
    const tierEl = $('tier-badge');
    if (tierEl) {
      const tierName = String(live.userTierName || '').trim();
      tierEl.hidden = !tierName;
      if (tierName) tierEl.textContent = `💎 ${tierName}`;
    }
    const convs = Array.isArray(live.conversations) ? live.conversations : [];
    const pinned = agy.pinned_conversation || '';
    const sel = $('sel-pinned');
    const options = [];
    const autoOpt = document.createElement('option');
    autoOpt.value = '';
    autoOpt.textContent = t('autoFollowSession');
    options.push(autoOpt);
    for (const c of convs) {
      const opt = document.createElement('option');
      opt.value = c.conversationId;
      opt.textContent = c.title || c.conversationId.slice(0, 8);
      options.push(opt);
    }
    sel.replaceChildren(...options);
    sel.value = convs.some((c) => c.conversationId === pinned) ? pinned : '';

    const shown =
      (pinned ? convs.find((c) => c.conversationId === pinned) : null) || live.active || null;
    if (!shown) {
      $('focus-badge').textContent = t('noSessionBadge');
      $('conv-title').textContent = t('noSessionTitle');
      $('conv-model').textContent = t('modelEmpty');
      $('ctx-text').textContent = '—';
      $('ctx-bar').style.width = '0%';
      $('kpi-speed').textContent = '—';
      $('kpi-5h').textContent = '—';
      $('kpi-week').textContent = '—';
      $('kpi-cache').textContent = '—';
    } else {
      const running = shown.status === 'CASCADE_RUN_STATUS_RUNNING';
      const activeModel = running && shown.lastStepModelLabel ? shown.lastStepModelLabel : shown.selectedModelLabel;
      const subCount = Array.isArray(live.activeSubagents) ? live.activeSubagents.length : 0;
      const isPinnedShown = Boolean(pinned && shown.conversationId === pinned);
      const focusKey = `focus_${shown.focusSource || live.focusSource || ''}`;
      const focusBase = isPinnedShown
        ? t('pinnedBadge')
        : (I18N[activeLang]?.[focusKey] ? t(focusKey) : t('liveTrackBadge'));
      $('focus-badge').textContent = shown.waitingForUser
        ? t('waitingUserBadge')
        : subCount > 0
          ? `${focusBase}${t('subagentsSuffix', { count: subCount })}`
          : focusBase;
      $('conv-title').textContent = `${running ? t('runningPrefix') : ''}${shown.title || t('newChat')}`;
      const lastPart = shown.lastStepModelLabel ? t('modelLastPart', { last: shown.lastStepModelLabel }) : '';
      $('conv-model').textContent = t('modelLine', { active: activeModel || t('unknownModel'), last: lastPart });

      const used = Number(shown.contextUsedTokens || 0);
      const limit = Number(shown.contextLimitTokens || 524288);
      const pct = limit > 0 ? (used / limit) * 100 : 0;
      $('ctx-text').textContent = `${fmtTokens(used)} / ${fmtTokens(limit)} · ${pct.toFixed(1)}%`;
      const bar = $('ctx-bar');
      bar.style.width = `${Math.min(100, Math.max(0, pct)).toFixed(1)}%`;
      bar.classList.toggle('danger', pct >= 80);
      bar.classList.toggle('warn', pct >= 55 && pct < 80);

      const rate = shown.latestDecodeTokPerSec || shown.avgDecodeTokPerSec;
      $('kpi-speed').textContent = rate ? `${rate.toFixed(1)} tok/s` : '—';
      const q5 = pickQuota(live.quotaBuckets, activeModel, '5h', shown.quotaRemainingPct, shown.quotaResetTime);
      const qw = pickQuota(live.quotaBuckets, activeModel, 'week', shown.quotaRemainingPct, shown.quotaResetTime);
      $('kpi-5h').textContent = q5 !== null ? `${q5.toFixed(0)}%` : '—';
      $('kpi-week').textContent = qw !== null ? `${qw.toFixed(0)}%` : '—';
      $('kpi-cache').textContent = `${Number(shown.cacheHitRatePct || 0).toFixed(1)}%`;
    }

    $('last-sync').textContent = new Date().toLocaleTimeString(I18N[activeLang]?.timeLocale || 'zh-CN', { hour12: false });
  }

  async function loadState() {
    try {
      const res = await fetcher('/api/state');
      if (!res.ok) return;
      const state = await res.json();
      render(state);
    } catch {
      setStatus(t('msgLoadFailed'));
    }
  }

  async function saveConfig(patch) {
    try {
      setStatus(t('msgSaving'));
      const res = await fetcher('/api/pet/config', {
        method: 'POST',
        body: JSON.stringify(patch),
      });
      if (!res.ok) {
        setStatus(t('msgSaveFailed'));
        return;
      }
      const result = await res.json();
      if (currentState) {
        currentState.agyConfig = result.agyConfig;
        currentState.bridgeSettings = result.bridgeSettings;
        render(currentState);
      }
      setStatus(t('msgSaved'));
    } catch {
      setStatus(t('msgWriteFailed'));
    }
  }

  async function reportInitialHostFocus() {
    const cid = window.sidecar?.conversationId;
    if (!cid) return;
    let uris = [];
    try {
      if (window.sidecar?.getWorkspaceUris) {
        uris = await window.sidecar.getWorkspaceUris();
      }
    } catch {
      uris = [];
    }
    try {
      await fetcher('/api/host-focus', {
        method: 'POST',
        body: JSON.stringify({ conversationId: cid, workspaceUris: uris, initial: true }),
      });
    } catch {
      // Non-fatal.
    }
  }

  $('btn-launch').addEventListener('click', async () => {
    setStatus(t('msgLaunching'));
    try {
      const res = await fetcher('/api/pet/launch', { method: 'POST', body: '{}' });
      const body = await res.json();
      if (body.ok) {
        setStatus(t('msgLaunchSent'));
      } else {
        const errText = body.errorKey ? t(body.errorKey, body.errorParams) : (body.error || t('unknownVal'));
        setStatus(t('msgLaunchFailed', { error: errText }));
      }
      setTimeout(loadState, 800);
    } catch {
      setStatus(t('msgLaunchError'));
    }
  });

  $('btn-github').addEventListener('click', async () => {
    try {
      await fetcher('/api/open-github', { method: 'POST', body: '{}' });
      setStatus(t('msgGithubOpened'));
    } catch {
      setStatus(t('msgGithubFailed'));
    }
  });

  $('btn-update').addEventListener('click', async () => {
    const btn = $('btn-update');
    btn.disabled = true;
    btn.textContent = t('btnUpdating');
    setStatus(t('msgUpdating'));
    try {
      const res = await fetcher('/api/pet/update', { method: 'POST', body: '{}' });
      const body = await res.json();
      const msg = body.messageKey
        ? t(body.messageKey, body.messageParams)
        : (body.message || (body.ok ? t('msgUpdateOk') : t('msgUpdateIncomplete')));
      setStatus(msg);
      setTimeout(loadState, 600);
    } catch {
      setStatus(t('msgUpdateReqFailed'));
      setTimeout(loadState, 600);
    } finally {
      btn.disabled = false;
    }
  });

  const selLang = $('sel-language');
  if (selLang) {
    selLang.addEventListener('change', (e) => {
      customStatusMsg = false;
      saveConfig({ language: e.target.value });
    });
  }
  $('chk-follow-model').addEventListener('change', (e) => saveConfig({ follow_model: e.target.checked }));
  $('chk-hud-enabled').addEventListener('change', (e) => saveConfig({ hud_enabled: e.target.checked }));
  const hoverOnlyChk = $('chk-hud-hover-only');
  if (hoverOnlyChk) {
    hoverOnlyChk.addEventListener('change', (e) => saveConfig({ hud_hover_only: e.target.checked }));
  }
  $('chk-hud-locked').addEventListener('change', (e) => saveConfig({ hud_locked: e.target.checked }));
  $('chk-autonomy').addEventListener('change', (e) => saveConfig({ autonomy: e.target.checked }));
  $('chk-reactions').addEventListener('change', (e) => saveConfig({ reactions: e.target.checked }));
  const progChk = $('chk-progress-bubbles');
  if (progChk) {
    progChk.addEventListener('change', (e) => saveConfig({ progress_bubbles: e.target.checked }));
  }
  $('chk-subagent-clones').addEventListener('change', (e) => saveConfig({ subagent_clones: e.target.checked }));
  $('chk-particles').addEventListener('change', (e) => saveConfig({ particles: e.target.checked }));
  $('chk-edge-dock').addEventListener('change', (e) => saveConfig({ edge_dock: e.target.checked }));
  $('chk-ai-comments').addEventListener('change', (e) => saveConfig({ aiComments: e.target.checked }));
  $('chk-auto-launch').addEventListener('change', (e) => saveConfig({ autoLaunchPet: e.target.checked }));
  $('chk-check-updates').addEventListener('change', (e) => saveConfig({ checkUpdates: e.target.checked }));
  $('sel-appearance').addEventListener('change', (e) => saveConfig({ hud_appearance: e.target.value }));
  $('sel-hud-mode').addEventListener('change', (e) => saveConfig({ hud_mode: e.target.value }));
  $('sel-pinned').addEventListener('change', (e) => saveConfig({ pinned_conversation: e.target.value }));

  applyStaticTranslations(activeLang);
  syncThemeSchemeFromBg();
  reportInitialHostFocus().finally(loadState);
  const timer = setInterval(loadState, 2500);
  window.addEventListener('beforeunload', () => clearInterval(timer));
})();
