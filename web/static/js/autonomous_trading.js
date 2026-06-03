/* Autonomous Trading dashboard — frontend logic.
 *
 * Drives the supervised control-tower UI by calling the /api/autonomous/*
 * endpoints. CSRF tokens for state-changing requests are injected
 * automatically by web/static/js/main.js. This script intentionally
 * never exposes a live-execution path.
 */

(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);

  const state = {
    status: null,
    lastProposal: null,
    paperAdapterConfigured: false,
  };

  /* ------------------------- formatting helpers ------------------------- */

  function fmtMoney(value) {
    if (value === null || value === undefined || value === '') return '—';
    const num = Number(value);
    if (!Number.isFinite(num)) return '—';
    return num.toLocaleString(undefined, {
      style: 'currency', currency: 'USD', maximumFractionDigits: 2,
    });
  }

  function fmtNumber(value, digits) {
    if (value === null || value === undefined || value === '') return '—';
    const num = Number(value);
    if (!Number.isFinite(num)) return '—';
    return num.toLocaleString(undefined, {
      maximumFractionDigits: digits == null ? 2 : digits,
    });
  }

  function fmtTimestamp(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString();
  }

  function setFeedback(message, kind) {
    const el = $('actionFeedback');
    if (!el) return;
    el.textContent = message || '';
    el.classList.remove('is-error', 'is-success');
    if (kind === 'error')   el.classList.add('is-error');
    if (kind === 'success') el.classList.add('is-success');
  }

  async function postJson(url, body) {
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    });
    let data = {};
    try { data = await resp.json(); } catch (_) { /* keep empty */ }
    if (!resp.ok) {
      const msg = (data && data.error) || ('HTTP ' + resp.status);
      throw new Error(msg);
    }
    return data;
  }

  async function getJson(url) {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    return resp.json();
  }

  /* ------------------------- status panel ------------------------- */

  function renderStatus(payload) {
    state.status = payload;
    const cfg = (payload && payload.config) || {};
    const halted = !!payload.emergency_stop_file_exists;
    state.paperAdapterConfigured = !!payload.paper_adapter_configured;

    const badges = [];
    const mode = cfg.mode || 'recommend_only';
    if (mode === 'recommend_only') {
      badges.push(['RECOMMEND ONLY', 'badge-safe']);
    } else if (mode === 'paper_execute') {
      badges.push(['PAPER EXECUTE', 'badge-warn']);
    } else if (mode === 'assisted_live') {
      badges.push(['ASSISTED LIVE', 'badge-danger']);
    } else {
      badges.push([mode.toUpperCase(), 'badge-info']);
    }

    if (cfg.allow_live_execution) {
      badges.push(['LIVE ALLOWED', 'badge-danger']);
    } else {
      badges.push(['LIVE DISABLED', 'badge-info']);
    }

    if (halted) {
      badges.push(['EMERGENCY STOP', 'badge-danger']);
    }

    if (!state.paperAdapterConfigured) {
      badges.push(['NO PAPER ADAPTER', 'badge-warn']);
    } else {
      badges.push(['PAPER ADAPTER READY', 'badge-safe']);
    }

    // Signal provider readiness. Prefer the explicit boolean from the
    // status payload; fall back to "warning present" for old responses.
    const providerReady = payload.signal_provider_ready === true;
    if (providerReady) {
      badges.push(['SIGNAL PROVIDER READY', 'badge-safe']);
    } else if (payload.warning || payload.signal_provider_ready === false) {
      badges.push(['STATIC PROVIDER', 'badge-warn']);
    }

    const badgeRow = $('statusBadges');
    badgeRow.innerHTML = '';
    badges.forEach(([label, cls]) => {
      const span = document.createElement('span');
      span.className = 'badge ' + cls;
      span.textContent = label;
      badgeRow.appendChild(span);
    });

    const grid = $('statusGrid');
    grid.innerHTML = '';
    const rows = [
      ['Mode', cfg.mode || '—'],
      ['Live execution allowed', cfg.allow_live_execution ? 'yes' : 'no'],
      ['Require user confirmation', cfg.require_user_confirmation ? 'yes' : 'no'],
      ['Max trades per day', fmtNumber(cfg.max_trades_per_day, 0)],
      ['Min signal strength', fmtNumber(cfg.min_signal_strength, 0)],
      ['Required signal label', cfg.required_signal_label || '—'],
      ['Min deployable cash', fmtMoney(cfg.min_deployable_cash)],
      ['Emergency stop file', payload.emergency_stop_file || '—'],
      ['Emergency stop active', halted ? 'YES' : 'no'],
      ['Paper adapter configured', state.paperAdapterConfigured ? 'yes' : 'no'],
      ['Paper adapter reason', payload.paper_adapter_reason || '—'],
      ['Signal provider', payload.signal_provider || '—'],
      ['Signal provider ready', payload.signal_provider_ready ? 'yes' : 'no'],
      ['Connection environment', payload.connection_env || '—'],
    ];
    for (const [label, value] of rows) {
      const dt = document.createElement('dt');
      dt.textContent = label;
      const dd = document.createElement('dd');
      dd.textContent = value;
      grid.appendChild(dt);
      grid.appendChild(dd);
    }

    const warnEl = $('providerWarning');
    if (payload.warning) {
      warnEl.textContent = '⚠️ ' + payload.warning;
      warnEl.style.display = '';
    } else {
      warnEl.textContent = '';
      warnEl.style.display = 'none';
    }

    const btnExec = $('btnExecutePaper');
    if (btnExec) {
      const disable = !state.paperAdapterConfigured || halted;
      btnExec.disabled = disable;
      if (!state.paperAdapterConfigured) {
        btnExec.title = payload.paper_adapter_reason ||
          'Disabled: no paper trading adapter is configured.';
      } else if (halted) {
        btnExec.title = 'Disabled: emergency stop is active.';
      } else {
        btnExec.title = 'Run /api/autonomous/execute-paper after confirmation.';
      }
    }
  }

  async function refreshStatus() {
    try {
      const data = await getJson('/api/autonomous/status');
      renderStatus(data);
      if (data.cash_snapshot) renderCashSnapshot(data.cash_snapshot);
      setFeedback('Status refreshed.', 'success');
    } catch (err) {
      setFeedback('Failed to refresh status: ' + err.message, 'error');
    }
  }

  /* ------------------------- cash panel ------------------------- */

  function renderCashSnapshot(snapshot) {
    snapshot = snapshot || {};
    const map = {
      cashBalance:         snapshot.cash_balance,
      cashReservedTotal:   snapshot.reserved_cash_total,
      cashReservedPuts:    snapshot.reserved_cash_short_puts,
      cashReservedSpreads: snapshot.reserved_cash_defined_risk_spreads,
      cashReservedOrders:  snapshot.reserved_for_pending_orders,
      cashManualBuffer:    snapshot.manual_cash_buffer,
      cashMarginBuffer:    snapshot.margin_safety_buffer,
      cashDeployable:      snapshot.deployable_cash,
    };
    for (const [id, value] of Object.entries(map)) {
      const el = $(id);
      if (el) el.textContent = fmtMoney(value);
    }

    const list = $('cashWarnings');
    list.innerHTML = '';
    const warnings = snapshot.warnings || snapshot.cash_warnings || [];
    if (Array.isArray(warnings)) {
      warnings.forEach((w) => {
        const li = document.createElement('li');
        li.textContent = typeof w === 'string' ? w : JSON.stringify(w);
        list.appendChild(li);
      });
    }
  }

  /* ------------------------- shortlist / rejected ------------------------- */

  function renderShortlist(rows) {
    const body = $('shortlistBody');
    body.innerHTML = '';
    if (!rows || !rows.length) {
      body.innerHTML = '<tr><td colspan="11" class="empty">No candidates after the latest scan.</td></tr>';
      return;
    }
    rows.forEach((row, idx) => {
      const tr = document.createElement('tr');
      // RankedCandidate.to_dict() nests the CandidateSignal under
      // `candidate`; fall back to the row itself so flat fixtures and
      // older payloads keep working.
      const candidate = (row && row.candidate) || row || {};
      const reasons = row.reasons || row.ranking_reasons || [];
      const cells = [
        row.rank != null ? row.rank : (idx + 1),
        candidate.symbol || row.symbol || '—',
        candidate.company_name || candidate.company || candidate.security ||
          row.company || row.security || '—',
        candidate.sector || row.sector || '—',
        fmtNumber(candidate.strength_score ?? row.strength_score, 0),
        candidate.signal_label || row.signal_label || '—',
        fmtNumber(candidate.last_price ?? row.last_price),
        fmtNumber(
          candidate.support_price ?? candidate.support ??
            row.support_price ?? row.support
        ),
        fmtNumber(
          candidate.resistance_price ?? candidate.resistance ??
            row.resistance_price ?? row.resistance
        ),
        fmtNumber(row.score ?? row.ranking_score),
        Array.isArray(reasons) ? reasons.join('; ') : String(reasons || ''),
      ];
      cells.forEach((c) => {
        const td = document.createElement('td');
        td.textContent = c == null ? '—' : String(c);
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
  }

  function renderRejected(rows) {
    const body = $('rejectedBody');
    const count = $('rejectedCount');
    body.innerHTML = '';
    rows = rows || [];
    count.textContent = String(rows.length);
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="2" class="empty">No rejections recorded.</td></tr>';
      return;
    }
    rows.forEach((row) => {
      const tr = document.createElement('tr');
      const tdSym = document.createElement('td');
      tdSym.textContent = row.symbol || '—';
      const tdReason = document.createElement('td');
      tdReason.textContent = row.reason || row.rejection_reason || '—';
      tr.appendChild(tdSym);
      tr.appendChild(tdReason);
      body.appendChild(tr);
    });
  }

  /* ------------------------- proposal card ------------------------- */

  function renderProposal(decision) {
    const card = $('proposalCard');
    card.classList.remove('proposal-empty');
    card.innerHTML = '';

    if (!decision) {
      card.classList.add('proposal-empty');
      card.innerHTML = '<p>No proposal generated yet.</p>';
      return;
    }

    const plan = decision.trade_plan || {};
    const selected = decision.selected || {};
    const risk = decision.risk_check || {};

    const header = document.createElement('p');
    header.textContent =
      'Status: ' + (decision.status || '—') +
      ' | Mode: ' + (decision.mode || '—');
    card.appendChild(header);

    if (decision.rejection_reason) {
      const rej = document.createElement('p');
      rej.textContent = 'Rejection reason: ' + decision.rejection_reason;
      card.appendChild(rej);
    }

    const grid = document.createElement('dl');
    grid.className = 'proposal-grid';
    const rows = [
      ['Trade type', plan.trade_type || '—'],
      ['Action', plan.action || '—'],
      ['Symbol', plan.symbol || selected.symbol || '—'],
      ['Quantity / contracts', plan.quantity != null ? plan.quantity : (plan.contracts || '—')],
      ['Limit price', fmtMoney(plan.limit_price)],
      ['Target price', fmtMoney(plan.target_price)],
      ['Stop price', fmtMoney(plan.stop_price)],
      ['Strike', plan.strike != null ? fmtMoney(plan.strike) : '—'],
      ['Expiry', plan.expiry || '—'],
      ['Required cash', fmtMoney(plan.required_cash)],
      ['Expected premium', plan.expected_premium != null ? fmtMoney(plan.expected_premium) : '—'],
      ['Order ID', decision.order_id != null ? decision.order_id : '—'],
    ];
    rows.forEach(([k, v]) => {
      const dt = document.createElement('dt');
      dt.textContent = k;
      const dd = document.createElement('dd');
      dd.textContent = v == null ? '—' : String(v);
      grid.appendChild(dt);
      grid.appendChild(dd);
    });
    card.appendChild(grid);

    // ---- Trade Rationale: why this stock, why this many shares ----
    const cand = (selected && selected.candidate) || selected || {};
    const extras = cand.extras || {};
    const rationaleItems = [];

    if (cand.signal_label || cand.strength_score != null) {
      const company = cand.company_name ? ' \u2014 ' + cand.company_name : '';
      rationaleItems.push(
        'Signal: ' + (cand.signal_label || '\u2014') +
        (cand.strength_score != null ? ' (strength ' + cand.strength_score + ')' : '') +
        company
      );
    }
    if (extras.rsi_14 != null) {
      const rsiDesc = {
        rsi_oversold:   'oversold, below 30',
        rsi_overbought: 'overbought, above 70',
      }[extras.rsi_status] || (extras.rsi_status || '');
      rationaleItems.push(
        'RSI(14): ' + extras.rsi_14 + (rsiDesc ? ' \u2014 ' + rsiDesc : '')
      );
    }
    if (extras.bollinger_status) {
      const bollDesc = {
        near_lower_band: 'near lower Bollinger band (price at downside extreme)',
        near_upper_band: 'near upper Bollinger band',
        inside_bands:    'inside Bollinger bands',
      }[extras.bollinger_status] || extras.bollinger_status;
      rationaleItems.push('Bollinger: ' + bollDesc);
    }
    if (extras.momentum_confirmation) {
      const momDesc = {
        confirmed_rebound: '2+ consecutive higher closes after oversold low',
        no_rebound:        'no rebound confirmed yet',
      }[extras.momentum_confirmation] || extras.momentum_confirmation;
      rationaleItems.push('Momentum: ' + momDesc);
    }
    if (extras.quality_label) {
      rationaleItems.push(
        'Fundamentals: ' + extras.quality_label +
        (extras.quality_score != null ? ' (score ' + extras.quality_score + ')' : '')
      );
    }
    if (plan.quantity != null && plan.limit_price != null && decision.deployable_cash != null) {
      const maxPct = (state.status && state.status.config &&
        state.status.config.max_new_position_pct) || 0.10;
      rationaleItems.push(
        'Sizing: ' + plan.quantity + ' share' + (plan.quantity !== 1 ? 's' : '') +
        ' \u00d7 ' + fmtMoney(plan.limit_price) + ' = ' + fmtMoney(plan.required_cash) +
        ' (cap: ' + (maxPct * 100).toFixed(0) + '% equity;' +
        ' ' + fmtMoney(decision.deployable_cash) + ' deployable)'
      );
    }
    if (rationaleItems.length) {
      const rh = document.createElement('p');
      rh.className = 'proposal-section-title';
      rh.textContent = 'Trade Rationale';
      const rbox = document.createElement('div');
      rbox.className = 'rationale-box';
      const rul = document.createElement('ul');
      rul.className = 'proposal-list';
      rationaleItems.forEach((item) => {
        const li = document.createElement('li');
        li.textContent = item;
        rul.appendChild(li);
      });
      rbox.appendChild(rul);
      card.appendChild(rh);
      card.appendChild(rbox);
    }

    if (plan.reason) {
      const h = document.createElement('p');
      h.className = 'proposal-section-title';
      h.textContent = 'Reason';
      const body = document.createElement('p');
      body.textContent = plan.reason;
      card.appendChild(h);
      card.appendChild(body);
    }

    const riskNotes = plan.risk_notes || (risk && risk.notes) || [];
    if (Array.isArray(riskNotes) && riskNotes.length) {
      const h = document.createElement('p');
      h.className = 'proposal-section-title';
      h.textContent = 'Risk notes';
      const ul = document.createElement('ul');
      ul.className = 'proposal-list';
      riskNotes.forEach((n) => {
        const li = document.createElement('li');
        li.textContent = n;
        ul.appendChild(li);
      });
      card.appendChild(h);
      card.appendChild(ul);
    }

    const exitPlan = plan.exit_plan;
    if (exitPlan) {
      const h = document.createElement('p');
      h.className = 'proposal-section-title';
      h.textContent = 'Exit plan';
      if (Array.isArray(exitPlan)) {
        const ul = document.createElement('ul');
        ul.className = 'proposal-list';
        exitPlan.forEach((n) => {
          const li = document.createElement('li');
          li.textContent = typeof n === 'string' ? n : JSON.stringify(n);
          ul.appendChild(li);
        });
        card.appendChild(h);
        card.appendChild(ul);
      } else {
        const p = document.createElement('p');
        p.textContent = typeof exitPlan === 'string' ? exitPlan : JSON.stringify(exitPlan);
        card.appendChild(h);
        card.appendChild(p);
      }
    }

    if (Array.isArray(decision.notes) && decision.notes.length) {
      const h = document.createElement('p');
      h.className = 'proposal-section-title';
      h.textContent = 'Notes';
      const ul = document.createElement('ul');
      ul.className = 'proposal-list';
      decision.notes.forEach((n) => {
        const li = document.createElement('li');
        li.textContent = n;
        ul.appendChild(li);
      });
      card.appendChild(h);
      card.appendChild(ul);
    }
  }

  /* ------------------------- audit timeline ------------------------- */

  async function refreshAudit() {
    const body = $('auditBody');
    try {
      const data = await getJson('/api/autonomous/audit?limit=20');
      body.innerHTML = '';
      const entries = (data && data.entries) || [];
      if (!entries.length) {
        body.innerHTML = '<tr><td colspan="7" class="empty">No audit entries yet.</td></tr>';
        return;
      }
      entries.forEach((e) => {
        const tr = document.createElement('tr');
        const cells = [
          fmtTimestamp(e.timestamp),
          e.mode || '—',
          e.status || '—',
          e.selected_symbol || '—',
          e.trade_type || '—',
          e.order_id != null ? e.order_id : '—',
          e.rejection_reason || '',
        ];
        cells.forEach((c) => {
          const td = document.createElement('td');
          td.textContent = String(c);
          tr.appendChild(td);
        });
        body.appendChild(tr);
      });
    } catch (err) {
      body.innerHTML = '';
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 7;
      td.className = 'empty';
      td.textContent = 'Failed to load audit log: ' + ((err && err.message) || String(err));
      tr.appendChild(td);
      body.appendChild(tr);
    }
  }

  /* ------------------------- actions ------------------------- */

  async function runScan() {
    setFeedback('Scanning…');
    try {
      const data = await postJson('/api/autonomous/scan', {});
      renderShortlist(data.shortlist || []);
      renderRejected(data.rejected_candidates || []);
      if (data.deployable_cash != null) {
        $('cashDeployable').textContent = fmtMoney(data.deployable_cash);
      }
      let msg = 'Scan complete: ' +
        (data.shortlist ? data.shortlist.length : 0) + ' candidate(s).';
      if (data.rejection_reason) msg += ' Reason: ' + data.rejection_reason;
      setFeedback(msg, 'success');
    } catch (err) {
      setFeedback('Scan failed: ' + err.message, 'error');
    }
  }

  async function runPropose() {
    setFeedback('Generating proposal…');
    try {
      const decision = await postJson('/api/autonomous/propose', {});
      state.lastProposal = decision;
      renderProposal(decision);
      if (decision.cash_snapshot) renderCashSnapshot(decision.cash_snapshot);
      if (decision.shortlist) renderShortlist(decision.shortlist);
      if (decision.rejected_candidates) renderRejected(decision.rejected_candidates);
      setFeedback('Proposal generated (' + (decision.status || 'unknown') + ').', 'success');
      refreshAudit();
    } catch (err) {
      setFeedback('Propose failed: ' + err.message, 'error');
    }
  }

  /* ---- paper-execute confirmation modal ---- */

  function openPaperConfirm() {
    if (!state.paperAdapterConfigured) {
      setFeedback('Cannot execute: no paper adapter configured.', 'error');
      return;
    }
    const overlay = $('paperConfirmOverlay');
    const planEl = $('paperConfirmPlan');
    planEl.innerHTML = '';
    if (state.lastProposal && state.lastProposal.trade_plan) {
      // Re-render the most recent proposal inside the confirmation card
      // so the user reviews the same plan they're about to execute.
      const original = $('proposalCard');
      planEl.innerHTML = original.innerHTML;
    } else {
      planEl.innerHTML =
        '<p>No proposal has been generated yet. The engine will recompute ' +
        'the current best-effort recommendation before placing the paper order.</p>';
    }
    overlay.style.display = 'flex';
  }

  function closePaperConfirm() {
    $('paperConfirmOverlay').style.display = 'none';
  }

  async function confirmPaperExecute() {
    closePaperConfirm();
    setFeedback('Executing paper trade…');
    try {
      const decision = await postJson('/api/autonomous/execute-paper', { confirm: true });
      renderProposal(decision);
      const status = decision.status || 'unknown';
      const kind = status === 'paper_executed' ? 'success' : 'error';
      setFeedback('Paper execution result: ' + status +
        (decision.rejection_reason ? ' — ' + decision.rejection_reason : ''),
        kind);
      refreshAudit();
    } catch (err) {
      setFeedback('Paper execute failed: ' + err.message, 'error');
    }
  }

  async function triggerEmergencyStop() {
    if (!window.confirm(
      '🚨 EMERGENCY STOP\n\nThis will create the EMERGENCY_STOP file and ' +
      'block all subsequent autonomous trading runs.\n\nProceed?')) {
      return;
    }
    setFeedback('Triggering emergency stop…');
    try {
      await postJson('/api/autonomous/emergency-stop',
        { reason: 'Manual halt from autonomous trading dashboard' });
      setFeedback('Emergency stop activated.', 'success');
      refreshStatus();
      refreshAudit();
    } catch (err) {
      setFeedback('Emergency stop failed: ' + err.message, 'error');
    }
  }

  /* ------------------------- paper robot runner ------------------------- */

  function setRunnerFeedback(message, kind) {
    const el = $('runnerFeedback');
    if (!el) return;
    el.textContent = message || '';
    el.dataset.kind = kind || '';
  }

  function renderRunnerGates(payload) {
    const badges = $('runnerGates');
    const reasonsEl = $('runnerReasons');
    const btn = $('btnRunPaperRobot');
    if (!badges) return;
    badges.innerHTML = '';
    const gates = payload && payload.gates ? payload.gates : null;
    if (!gates) {
      badges.innerHTML = '<span class="badge badge-muted">Runner status unavailable</span>';
      if (btn) btn.disabled = true;
      return;
    }
    const items = [
      ['Connected', gates.connected],
      ['Paper mode', gates.paper_mode],
      ['Paper adapter', gates.paper_adapter_ready],
      ['Signal provider', gates.signal_provider_ready],
      ['Runner enabled', gates.runner_enabled],
      ['No emergency stop', !gates.emergency_stop_active],
    ];
    items.forEach(([label, ok]) => {
      const b = document.createElement('span');
      b.className = 'badge ' + (ok ? 'badge-success' : 'badge-warning');
      b.textContent = label + ': ' + (ok ? 'OK' : 'NO');
      b.setAttribute('aria-label', label + ' ' + (ok ? 'OK' : 'not ready'));
      badges.appendChild(b);
    });
    const occ = document.createElement('span');
    occ.className = 'badge badge-muted';
    occ.textContent = 'Open: ' + gates.open_autonomous_trades + '/' +
      gates.max_open_autonomous_trades;
    badges.appendChild(occ);

    if (reasonsEl) {
      reasonsEl.innerHTML = '';
      (gates.reasons || []).forEach((r) => {
        const li = document.createElement('li');
        li.textContent = r;
        reasonsEl.appendChild(li);
      });
    }
    if (btn) {
      btn.disabled = !gates.ready;
      btn.title = gates.ready ? 'Run one paper-only autonomous cycle.'
        : 'Disabled: ' + (gates.reasons || []).join('; ');
    }
  }

  function renderAutonomousTrades(payload) {
    const openBody = $('openTradesBody');
    const closedBody = $('closedTradesBody');
    if (openBody) {
      openBody.innerHTML = '';
      const open = (payload && payload.open) || [];
      if (!open.length) {
        openBody.innerHTML = '<tr><td colspan="9" class="empty">No open autonomous trades.</td></tr>';
      } else {
        open.forEach((t) => {
          const tr = document.createElement('tr');
          [
            t.autonomous_trade_id || '',
            t.symbol || '',
            t.quantity != null ? t.quantity : '',
            fmtMoney(t.entry_limit_price),
            fmtMoney(t.target_price),
            fmtMoney(t.stop_price),
            t.status || '',
            t.entry_order_id != null ? t.entry_order_id : '',
          ].forEach((c) => {
            const td = document.createElement('td');
            td.textContent = String(c);
            tr.appendChild(td);
          });

          const tdAction = document.createElement('td');
          const btnCancel = document.createElement('button');
          btnCancel.className = 'btn-sm btn-danger';
          btnCancel.type = 'button';
          btnCancel.textContent = 'Cancel Entry';
          btnCancel.disabled = !t.entry_order_id;
          btnCancel.title = t.entry_order_id
            ? 'Cancel unfilled entry order at broker and close autonomous lifecycle record.'
            : 'No entry order id available for cancel.';
          btnCancel.addEventListener('click', () => {
            cancelAutonomousEntry(t.autonomous_trade_id, t.symbol, t.entry_order_id);
          });
          tdAction.appendChild(btnCancel);
          tr.appendChild(tdAction);

          openBody.appendChild(tr);
        });
      }
    }
    if (closedBody) {
      closedBody.innerHTML = '';
      const combined = []
        .concat((payload && payload.exit_pending) || [])
        .concat((payload && payload.closed) || []);
      if (!combined.length) {
        closedBody.innerHTML = '<tr><td colspan="7" class="empty">No closed autonomous trades yet.</td></tr>';
      } else {
        combined.forEach((t) => {
          const tr = document.createElement('tr');
          [
            t.autonomous_trade_id || '',
            t.symbol || '',
            t.quantity != null ? t.quantity : '',
            t.status || '',
            t.exit_reason || '',
            fmtMoney(t.exit_price),
            fmtMoney(t.realised_pnl),
          ].forEach((c) => {
            const td = document.createElement('td');
            td.textContent = String(c);
            tr.appendChild(td);
          });
          closedBody.appendChild(tr);
        });
      }
    }
  }

  function renderExitDecisions(decisions) {
    const body = $('exitDecisionsBody');
    if (!body) return;
    body.innerHTML = '';
    if (!decisions || !decisions.length) {
      body.innerHTML = '<tr><td colspan="5" class="empty">No exit evaluation run yet.</td></tr>';
      return;
    }
    decisions.forEach((d) => {
      const tr = document.createElement('tr');
      [
        d.symbol || '',
        d.decision || '',
        d.reason || '',
        fmtMoney(d.price),
        d.exit_order_id != null ? d.exit_order_id : '',
      ].forEach((c) => {
        const td = document.createElement('td');
        td.textContent = String(c);
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
  }

  async function refreshRunnerStatus() {
    try {
      const body = await getJson('/api/autonomous/runner/status');
      renderRunnerGates(body);
    } catch (err) {
      setRunnerFeedback('Failed to load runner status: ' + err.message, 'error');
    }
  }

  async function refreshAutonomousTrades() {
    try {
      const body = await getJson('/api/autonomous/runner/trades');
      renderAutonomousTrades(body);
    } catch (err) {
      setRunnerFeedback('Failed to load autonomous trades: ' + err.message, 'error');
    }
  }

  async function runPaperRobotOnce() {
    setRunnerFeedback('Running paper robot once…');
    try {
      const body = await postJson('/api/autonomous/runner/run-once-paper', {});
      const status = body.status || 'unknown';
      const msg = status === 'executed'
        ? 'Paper trade executed and recorded.'
        : 'Runner: ' + status + (body.rejection_reason ? ' — ' + body.rejection_reason : '');
      setRunnerFeedback(msg, status === 'executed' ? 'success' : 'warning');
      refreshRunnerStatus();
      refreshAutonomousTrades();
      refreshAudit();
    } catch (err) {
      setRunnerFeedback('Run-once failed: ' + err.message, 'error');
    }
  }

  async function evaluateExitsNow() {
    setRunnerFeedback('Evaluating exits…');
    try {
      const body = await postJson('/api/autonomous/runner/evaluate-exits', {});
      renderExitDecisions(body.decisions || []);
      setRunnerFeedback('Evaluated ' + (body.count || 0) + ' open trade(s).', 'success');
      refreshAutonomousTrades();
    } catch (err) {
      setRunnerFeedback('Evaluate exits failed: ' + err.message, 'error');
    }
  }

  async function cancelAutonomousEntry(tradeId, symbol, orderId) {
    if (!tradeId) return;
    const label = symbol || tradeId;
    const idPart = orderId != null ? (' (order ' + orderId + ')') : '';
    if (!window.confirm('Cancel entry for ' + label + idPart + '?')) return;

    setRunnerFeedback('Cancelling autonomous entry…');
    try {
      const body = await postJson('/api/autonomous/runner/cancel-entry', {
        autonomous_trade_id: tradeId,
      });
      const status = body.status || 'unknown';
      const msg = (status === 'cancel_requested')
        ? ('Cancel requested for ' + label + idPart + '.')
        : ('Cancel result: ' + status + (body.warning ? ' — ' + body.warning : ''));
      setRunnerFeedback(msg, status === 'cancel_requested' ? 'success' : 'warning');
      refreshRunnerStatus();
      refreshAutonomousTrades();
    } catch (err) {
      setRunnerFeedback('Cancel entry failed: ' + err.message, 'error');
    }
  }

  /* ------------------------- wire up ------------------------- */

  document.addEventListener('DOMContentLoaded', () => {
    $('btnRefreshStatus').addEventListener('click', refreshStatus);
    $('btnScan').addEventListener('click', runScan);
    $('btnPropose').addEventListener('click', runPropose);
    $('btnExecutePaper').addEventListener('click', openPaperConfirm);
    $('btnEmergencyStop').addEventListener('click', triggerEmergencyStop);
    $('paperConfirmCancel').addEventListener('click', closePaperConfirm);
    $('paperConfirmGo').addEventListener('click', confirmPaperExecute);

    const btnRunRobot = $('btnRunPaperRobot');
    if (btnRunRobot) btnRunRobot.addEventListener('click', runPaperRobotOnce);
    const btnExits = $('btnEvaluateExits');
    if (btnExits) btnExits.addEventListener('click', evaluateExitsNow);
    const btnRefreshTrades = $('btnRefreshAutonomousTrades');
    if (btnRefreshTrades) btnRefreshTrades.addEventListener('click', refreshAutonomousTrades);

    refreshStatus();
    refreshAudit();
    refreshRunnerStatus();
    refreshAutonomousTrades();
  });
})();
