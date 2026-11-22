/**
 * Token Meter frontend logic.
 * Syncs with host theme tokens, manages accessible tabs (including hidden="until-found"),
 * and polls /api/metrics with ETag deduplication.
 */

(function () {
  const POLL_MS = 2500;

  let paused = false;
  let lastEtag = '';
  let selectedConvId = window.sidecar?.conversationId || '';
  let userOverrodeConv = false;
  let includeSubagents = true;
  let pollTimer = null;

  const $ = (id) => document.getElementById(id);

  // -------------------------------------------------------------------------
  // Theme synchronization with Antigravity host iframe bridge
  // -------------------------------------------------------------------------
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
    const lum = (0.2126 * Number(m[1]) + 0.7152 * Number(m[2]) + 0.0722 * Number(m[3])) / 255;
    document.documentElement.dataset.theme = lum < 0.48 ? 'dark' : 'light';
  }

  window.addEventListener('message', (ev) => {
    if (ev.data?.type === 'theme-change') {
      requestAnimationFrame(syncThemeSchemeFromBg);
    }
  });

  // -------------------------------------------------------------------------
  // Accessible Tabs (selection follows focus + hidden="until-found" support)
  // -------------------------------------------------------------------------
  const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
  const panels = tabs.map((t) => $(t.dataset.panel));

  function activateTab(nextTab, moveFocus = false) {
    for (let i = 0; i < tabs.length; i++) {
      const t = tabs[i];
      const p = panels[i];
      const isSelected = t === nextTab;
      t.setAttribute('aria-selected', String(isSelected));
      t.tabIndex = isSelected ? 0 : -1;
      if (isSelected) {
        p.hidden = false;
      } else {
        p.setAttribute('hidden', 'until-found');
      }
    }
    if (moveFocus) nextTab.focus();
    nextTab.scrollIntoView({ block: 'nearest', inline: 'nearest', container: 'nearest' });
  }

  tabs.forEach((tab, idx) => {
    tab.addEventListener('click', () => activateTab(tab, false));
    tab.addEventListener('keydown', (e) => {
      let targetIdx = -1;
      if (e.key === 'ArrowRight') targetIdx = (idx + 1) % tabs.length;
      else if (e.key === 'ArrowLeft') targetIdx = (idx - 1 + tabs.length) % tabs.length;
      else if (e.key === 'Home') targetIdx = 0;
      else if (e.key === 'End') targetIdx = tabs.length - 1;
      if (targetIdx >= 0) {
        e.preventDefault();
        activateTab(tabs[targetIdx], true);
      }
    });
  });

  panels.forEach((panel, idx) => {
    panel.addEventListener('beforematch', () => activateTab(tabs[idx], false));
  });

  // -------------------------------------------------------------------------
  // Formatting helpers
  // -------------------------------------------------------------------------
  const numFmt = new Intl.NumberFormat('zh-CN');

  function fmtInt(n) {
    return numFmt.format(Math.round(Number(n || 0)));
  }

  function fmtCompact(n) {
    const v = Number(n || 0);
    if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`;
    if (v >= 10_000) return `${(v / 1_000).toFixed(1)}k`;
    return fmtInt(v);
  }

  function fmtRate(r) {
    if (r === null || r === undefined || !Number.isFinite(r) || r <= 0) return '—';
    return `${r.toFixed(1)} tok/s`;
  }

  function fmtPct(p) {
    if (p === null || p === undefined || !Number.isFinite(p)) return '—';
    return `${p.toFixed(1)}%`;
  }

  function fmtMs(ms) {
    if (ms === null || ms === undefined || !Number.isFinite(ms) || ms < 0) return '—';
    if (ms < 1000) return `${Math.round(ms)}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  }

  function fmtClock(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  function esc(str) {
    return String(str ?? '').replace(/[&<>"']/g, (c) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }[c]));
  }

  // -------------------------------------------------------------------------
  // Rendering: Global Models View
  // -------------------------------------------------------------------------
  function renderGlobal(globalData, totalConvs) {
    const t = globalData.totals;
    const models = globalData.models || [];

    $('badge-models').textContent = String(models.length);
    $('g-total-tokens').textContent = fmtCompact(t.totalTokens);
    $('g-total-tokens').title = `${fmtInt(t.totalTokens)} tokens`;
    $('g-token-split').textContent = `输入 ${fmtCompact(t.inputTokens)} · 输出 ${fmtCompact(t.outputTokens)}`;

    $('g-avg-decode').textContent = fmtRate(t.avgDecodeTokPerSec);
    $('g-speed-sub').textContent = `端到端 ${fmtRate(t.avgE2eTokPerSec)} · 峰值 ${fmtRate(t.peakDecodeTokPerSec)}`;

    $('g-cache-rate').textContent = fmtPct(t.cacheHitRate);
    $('g-cache-sub').textContent = `命中读取 ${fmtCompact(t.cacheReadTokens)}`;

    $('g-output-tokens').textContent = fmtCompact(t.outputTokens);
    $('g-output-sub').textContent = `思考 ${fmtCompact(t.thinkingTokens)} · 正文 ${fmtCompact(t.responseTokens)}`;
    $('g-conv-summary').textContent = `${totalConvs} 个会话 · ${fmtInt(t.steps)} 步生成`;

    // Proportion bars
    const barsEl = $('global-model-bars');
    if (models.length === 0) {
      barsEl.innerHTML = '<div class="empty-note">暂无模型 Token 消耗记录</div>';
    } else {
      const maxTotal = Math.max(...models.map((m) => m.totalTokens), 1);
      const rowsHtml = models.map((m) => {
        const scale = (m.totalTokens / maxTotal) * 100;
        const pCache = m.totalTokens > 0 ? (m.cacheReadTokens / m.totalTokens) * scale : 0;
        const pInput = m.totalTokens > 0 ? (m.inputTokens / m.totalTokens) * scale : 0;
        const pThink = m.totalTokens > 0 ? (m.thinkingTokens / m.totalTokens) * scale : 0;
        const pResp = m.totalTokens > 0 ? (m.responseTokens / m.totalTokens) * scale : 0;
        return `
          <div class="mbar-row">
            <div class="mbar-head">
              <span class="mbar-name" title="${esc(m.label)} (${esc(m.modelId)})">${esc(m.label)}</span>
              <span class="mbar-stats"><strong>${fmtRate(m.avgDecodeTokPerSec)}</strong> · ${fmtCompact(m.totalTokens)} (${fmtPct(m.sharePct)})</span>
            </div>
            <div class="mbar-track" title="缓存读取 ${fmtInt(m.cacheReadTokens)} | 输入 ${fmtInt(m.inputTokens)} | 思考 ${fmtInt(m.thinkingTokens)} | 正文 ${fmtInt(m.responseTokens)}">
              <span class="seg-cache" style="width:${pCache.toFixed(2)}%"></span>
              <span class="seg-input" style="width:${pInput.toFixed(2)}%"></span>
              <span class="seg-think" style="width:${pThink.toFixed(2)}%"></span>
              <span class="seg-resp" style="width:${pResp.toFixed(2)}%"></span>
            </div>
          </div>`;
      }).join('');

      barsEl.innerHTML = rowsHtml + `
        <div class="mbar-legend" aria-hidden="true">
          <span><i class="lg-dot seg-cache"></i>缓存读取</span>
          <span><i class="lg-dot seg-input"></i>常规输入</span>
          <span><i class="lg-dot seg-think"></i>思考输出</span>
          <span><i class="lg-dot seg-resp"></i>正文输出</span>
        </div>`;
    }

    // Leaderboard table
    const tbody = $('global-models-tbody');
    if (models.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty-note">暂无可统计的模型数据</td></tr>';
      return;
    }

    tbody.innerHTML = models.map((m) => `
      <tr>
        <th scope="row" title="${esc(m.modelId)}">
          ${esc(m.label)}
          <span class="cell-sub">${m.conversations} 会话 · ${m.steps} 步${m.provider ? ` · ${esc(m.provider)}` : ''}</span>
        </th>
        <td class="num">
          <div><span class="cell-primary">${fmtCompact(m.totalTokens)}</span><span class="cell-sub">占比 ${fmtPct(m.sharePct)}</span></div>
        </td>
        <td class="num">
          <div>${fmtCompact(m.inputTokens)}<span class="cell-sub">缓存 ${fmtCompact(m.cacheReadTokens)} (${fmtPct(m.cacheHitRate)})</span></div>
        </td>
        <td class="num">
          <div>${fmtCompact(m.outputTokens)}<span class="cell-sub">思 ${fmtCompact(m.thinkingTokens)} / 正 ${fmtCompact(m.responseTokens)}</span></div>
        </td>
        <td class="num">
          <div><span class="cell-primary speed">${fmtRate(m.avgDecodeTokPerSec)}</span><span class="cell-sub">峰值 ${fmtRate(m.peakDecodeTokPerSec)}</span></div>
        </td>
        <td class="num">
          <div>${fmtRate(m.avgE2eTokPerSec)}<span class="cell-sub">TTFT ${fmtMs(m.avgTtftMs)}</span></div>
        </td>
      </tr>
    `).join('');
  }

  // -------------------------------------------------------------------------
  // Rendering: Current Conversation Live Telemetry View
  // -------------------------------------------------------------------------
  function renderCurrent(current, conversations, activeId) {
    // Update conversation selector
    const sel = $('conv-select');
    const prevVal = sel.value;
    sel.innerHTML = conversations.map((c) => {
      const prefix = c.isSubagent ? '↳ ' : '';
      const activeMark = c.status === 'CASCADE_RUN_STATUS_RUNNING' ? '● ' : '';
      return `<option value="${esc(c.conversationId)}">${esc(activeMark + prefix + c.title)} (${fmtCompact(c.totalTokens)})</option>`;
    }).join('');
    if (activeId && conversations.some((c) => c.conversationId === activeId)) {
      sel.value = activeId;
    } else if (prevVal) {
      sel.value = prevVal;
    }

    const subBadge = $('subagent-count');
    if (current.subagentCount > 0) {
      subBadge.hidden = false;
      subBadge.textContent = String(current.subagentCount);
    } else {
      subBadge.hidden = true;
    }

    const steps = current.steps || [];
    const t = current.totals;
    $('badge-steps').textContent = String(steps.length);

    const latest = steps[0] || null;
    $('c-latest-speed').textContent = latest ? fmtRate(latest.decodeTokPerSec) : '—';
    $('c-latest-sub').textContent = latest
      ? `端到端 ${fmtRate(latest.e2eTokPerSec)} · TTFT ${fmtMs(latest.ttftMs)}`
      : '等待首次回复…';

    $('c-avg-speed').textContent = fmtRate(t.avgDecodeTokPerSec);
    $('c-avg-speed-sub').textContent = `端到端 ${fmtRate(t.avgE2eTokPerSec)} · TTFT ${fmtMs(t.avgTtftMs)}`;

    $('c-total-tokens').textContent = fmtCompact(t.totalTokens);
    $('c-total-tokens').title = `${fmtInt(t.totalTokens)} tokens`;
    $('c-token-split').textContent = `输入 ${fmtCompact(t.inputTokens)} · 输出 ${fmtCompact(t.outputTokens)}`;

    $('c-cache-rate').textContent = fmtPct(t.cacheHitRate);
    $('c-cache-sub').textContent = `缓存读取 ${fmtCompact(t.cacheReadTokens)}`;

    // Sparkline (chronological last 30 steps)
    const sparkEl = $('speed-sparkline');
    const recentChrono = steps.slice(0, 30).reverse();
    const validRates = recentChrono.map((s) => s.decodeTokPerSec || s.e2eTokPerSec || 0);
    const maxRate = Math.max(...validRates, 1);

    if (recentChrono.length === 0) {
      sparkEl.innerHTML = '<div class="empty-note" style="width:100%">当前会话暂无模型计速步骤</div>';
    } else {
      sparkEl.innerHTML = recentChrono.map((s, idx) => {
        const rate = s.decodeTokPerSec || s.e2eTokPerSec || 0;
        const pct = rate > 0 ? Math.max(10, (rate / maxRate) * 100) : 6;
        const tip = `#${s.stepIndex} ${s.label} | 流式 ${fmtRate(s.decodeTokPerSec)} | 端到端 ${fmtRate(s.e2eTokPerSec)} | TTFT ${fmtMs(s.ttftMs)} | 输出 ${fmtInt(s.outputTokens)} tok`;
        return `<div role="listitem" class="spark-bar${s.isSubagent ? ' subagent' : ''}" style="height:${pct.toFixed(1)}%" title="${esc(tip)}" data-idx="${idx}"></div>`;
      }).join('');
    }

    // Per-model breakdown inside current session (shown when >= 1 model)
    const cmSec = $('current-models-section');
    const cmList = $('current-models-list');
    if ((current.models || []).length > 0) {
      cmSec.hidden = false;
      cmList.innerHTML = current.models.map((m) => `
        <span class="mini-chip">
          <strong>${esc(m.label)}</strong>
          <span>${fmtCompact(m.totalTokens)} tok</span>
          <span>·</span>
          <span>${fmtRate(m.avgDecodeTokPerSec)}</span>
        </span>
      `).join('');
    } else {
      cmSec.hidden = true;
    }

    // Steps table
    const tbody = $('current-steps-tbody');
    if (steps.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty-note">当前会话尚无已完成计费的模型步骤</td></tr>';
      return;
    }

    tbody.innerHTML = steps.map((s) => {
      const toolsLabel = s.toolCalls && s.toolCalls.length > 0
        ? ` · 工具: ${s.toolCalls.slice(0, 3).join(', ')}${s.toolCalls.length > 3 ? '…' : ''}`
        : '';
      const roleBadge = s.isSubagent
        ? `<span class="role-tag">${esc(s.subagentRole || '子代理')}</span>`
        : '';
      return `
        <tr>
          <th scope="row">
            #${s.stepIndex} ${esc(s.label)}${roleBadge}
            <span class="cell-sub">${esc(fmtClock(s.createdAt))}${esc(toolsLabel)}</span>
          </th>
          <td class="num">
            <div><span class="cell-primary speed">${fmtRate(s.decodeTokPerSec)}</span><span class="cell-sub">${s.bufferedDecode ? '单包整块返回' : `解码 ${fmtMs(s.decodeMs)}`}</span></div>
          </td>
          <td class="num">
            <div>${fmtRate(s.e2eTokPerSec)}<span class="cell-sub">总耗时 ${fmtMs(s.e2eMs)}</span></div>
          </td>
          <td class="num">
            <div>${fmtMs(s.ttftMs)}<span class="cell-sub">思考耗时 ${fmtMs(s.thinkingMs)}</span></div>
          </td>
          <td class="num">
            <div>${fmtInt(s.outputTokens)}<span class="cell-sub">思 ${fmtInt(s.thinkingTokens)} / 正 ${fmtInt(s.responseTokens)}</span></div>
          </td>
          <td class="num">
            <div>${fmtCompact(s.inputTokens)}<span class="cell-sub">缓存 ${fmtCompact(s.cacheReadTokens)} (${fmtPct(s.cacheHitRate)})</span></div>
          </td>
        </tr>
      `;
    }).join('');
  }

  // -------------------------------------------------------------------------
  // Polling & Controls
  // -------------------------------------------------------------------------
  async function fetchMetrics(force = false) {
    if (paused && !force) return;
    try {
      const params = new URLSearchParams();
      if (selectedConvId) params.set('conversationId', selectedConvId);
      if (!userOverrodeConv && window.sidecar?.conversationId) {
        params.set('hostConvId', window.sidecar.conversationId);
      }
      params.set('includeSubagents', includeSubagents ? '1' : '0');
      if (!force && lastEtag) params.set('etag', lastEtag);

      const fetcher = window.sidecar?.fetch ? window.sidecar.fetch : window.fetch.bind(window);
      const res = await fetcher(`/api/metrics?${params.toString()}`);
      if (!res.ok) return;
      const data = await res.json();

      const hyd = $('hydrating-badge');
      hyd.hidden = !(data.hydratingCount > 0);
      if (data.hydratingCount > 0) {
        hyd.textContent = `同步历史中 (${data.hydratingCount})…`;
      }

      if (data.unchanged) {
        $('last-updated').textContent = `更新于 ${fmtClock(new Date().toISOString())}`;
        return;
      }

      lastEtag = data.etag || '';
      if (!userOverrodeConv && data.activeConversationId) {
        selectedConvId = data.activeConversationId;
      }

      renderGlobal(data.global, (data.conversations || []).length);
      renderCurrent(data.current, data.conversations || [], data.activeConversationId);
      $('last-updated').textContent = `更新于 ${fmtClock(new Date().toISOString())}`;
    } catch (err) {
      console.error('[token-meter] poll failed:', err);
    }
  }

  $('conv-select').addEventListener('change', (e) => {
    selectedConvId = e.target.value;
    userOverrodeConv = true;
    lastEtag = '';
    fetchMetrics(true);
  });

  $('chk-subagents').addEventListener('change', (e) => {
    includeSubagents = e.target.checked;
    lastEtag = '';
    fetchMetrics(true);
  });

  $('btn-refresh').addEventListener('click', () => {
    lastEtag = '';
    fetchMetrics(true);
  });

  $('btn-pause').addEventListener('click', () => {
    paused = !paused;
    const btn = $('btn-pause');
    btn.setAttribute('aria-pressed', String(paused));
    btn.textContent = paused ? '已暂停' : '实时';
    $('live-dot').classList.toggle('paused', paused);
    if (!paused) fetchMetrics(true);
  });

  syncThemeSchemeFromBg();
  fetchMetrics(true);
  pollTimer = setInterval(() => fetchMetrics(false), POLL_MS);
  window.addEventListener('beforeunload', () => clearInterval(pollTimer));
})();
