/* Autonomous Trading dashboard — frontend logic.
 *
 * Drives the supervised control-tower UI by calling the /api/autonomous/*
 * endpoints. CSRF tokens for state-changing requests are injected
 * automatically by web/static/js/main.js. The dashboard routes Paper or
 * Live actions from the detected TWS account context.
 */

(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);

  const state = {
    status: null,
    modePayload: null,
    accountMode: 'unknown',
    detectedAccountType: 'unknown',
    activeEndpoints: null,
    activeRunnerStatus: null,
    lastProposal: null,
    paperAdapterConfigured: false,
    autonomousModeOn: false,
    liveAccountId: '',
  };

  const ENDPOINTS = {
    paper: {
      status: '/api/autonomous/runner/status',
      activate: '/api/autonomous/mode/activate',
      halt: '/api/autonomous/mode/halt',
      runOnce: '/api/autonomous/runner/run-once-paper',
      evaluateExits: '/api/autonomous/runner/evaluate-exits',
      trades: '/api/autonomous/runner/trades',
    },
    live: {
      status: '/api/autonomous/live/status',
      activate: '/api/autonomous/live/activate',
      halt: '/api/autonomous/live/halt',
      runOnce: '/api/autonomous/live/run-once',
      evaluateExits: '/api/autonomous/live/evaluate-exits',
      trades: '/api/autonomous/live/trades',
    },
  };

  const ACTUAL_LIVE_CONFIRMATION_PHRASE = 'ENABLE ACTUAL LIVE TRADING';

  function normaliseAccountType(value) {
    const text = String(value || '').toLowerCase();
    if (text === 'paper' || text === 'live') return text;
    return 'unknown';
  }

  function selectedConnectionIsVerified(connection) {
    return connection && connection.paper_live_match_status === 'Verified';
  }

  function accountContextFromConnection(connection) {
    const detected = normaliseAccountType(connection && connection.running_account_type);
    const verified = selectedConnectionIsVerified(connection);
    return {
      detected: detected,
      mode: verified && detected !== 'unknown' ? detected : 'blocked',
      label: verified && detected === 'live' ? 'Live'
        : (verified && detected === 'paper' ? 'Paper' : 'Blocked'),
      verified: verified,
      accountId: (connection && connection.running_account_id) || '',
    };
  }

  /* ----------------------- activity log ----------------------- */

  const ACTIVITY_LOG_MAX = 50;
  const activityLog = [];

  function logActivity(level, message, details) {
    const validLevels = ['info', 'success', 'warning', 'error'];
    const safeLevel = validLevels.indexOf(level) !== -1 ? level : 'info';
    const safeMessage = (message || '').slice(0, 500);
    const entry = {
      timestamp: new Date().toLocaleTimeString(),
      level: safeLevel,
      message: safeMessage,
      details: details || null,
    };
    activityLog.unshift(entry);
    if (activityLog.length > ACTIVITY_LOG_MAX) activityLog.length = ACTIVITY_LOG_MAX;
    renderActivityLog();
  }

  const SEVERITY_META = {
    info:    { icon: '\u2139\uFE0F',  label: 'Info' },
    success: { icon: '\u2705', label: 'Success' },
    warning: { icon: '\u26A0\uFE0F',  label: 'Warning' },
    error:   { icon: '\u{1F6D1}', label: 'Error' },
  };

  function renderActivityLog() {
    const list = $('activityLogList');
    if (!list) return;
    list.innerHTML = '';
    activityLog.forEach(function (entry) {
      const meta = SEVERITY_META[entry.level] || SEVERITY_META.info;
      const li = document.createElement('li');
      li.className = 'activity-entry activity-' + entry.level;
      li.setAttribute('aria-label', meta.label + ': ' + entry.timestamp + ' — ' + entry.message);
      const badge = document.createElement('span');
      badge.className = 'activity-severity';
      badge.setAttribute('aria-hidden', 'true');
      badge.textContent = meta.icon + ' ' + meta.label;
      const time = document.createElement('span');
      time.className = 'activity-time';
      time.textContent = entry.timestamp;
      const msg = document.createElement('span');
      msg.className = 'activity-msg';
      msg.textContent = ' — ' + entry.message;
      li.appendChild(badge);
      li.appendChild(time);
      li.appendChild(msg);
      list.appendChild(li);
    });
  }

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

  function currentEndpoint(name) {
    return state.activeEndpoints && state.activeEndpoints[name];
  }

  function normaliseLiveModePayload(modeData, liveData, liveError) {
    const connection = (modeData && modeData.connection) || {};
    const context = accountContextFromConnection(connection);
    // Keep the last known live mode state when /live/status is unavailable
    // so operators can still turn mode OFF during transient API failures.
    const cachedMode = (state.modePayload && state.modePayload.mode) || {};
    const liveMode = (liveData && liveData.autonomous_live_mode) || cachedMode;
    const liveGates = (liveData && liveData.gates) || {};
    const continuousSelected = selectedTradingCycle() === 'continuous';
    const reasons = liveError
      ? [liveError.message || String(liveError)]
      : [...(liveGates.reasons || [])];
    const halted = !!liveGates.emergency_stop_active;
    const continuousReady = !continuousSelected || !!liveGates.live_continuous_enabled;
    const gatesReady = !!liveGates.ready && continuousReady;
    const ready = gatesReady && context.verified;
    if (continuousSelected && !liveGates.live_continuous_enabled && !liveError) {
      reasons.push(
        'Live continuous mode is disabled. Set AUTONOMOUS_LIVE_CONTINUOUS_ENABLED=true in .env to enable.'
      );
    }
    const readinessStatus = halted ? 'Halted' : (ready ? 'Ready' : 'Not Ready');
    return {
      account_context: context,
      mode: liveMode,
      connection: connection,
      readiness: {
        status: readinessStatus,
        message: liveMode.message || reasons.join('; ') || '',
        gates: {
          ...liveGates,
          ready: gatesReady,
          reasons: reasons,
        },
      },
    };
  }

  function normalisePaperModePayload(modeData) {
    const connection = (modeData && modeData.connection) || {};
    return {
      ...(modeData || {}),
      account_context: accountContextFromConnection(connection),
    };
  }

  /* ------------------------- status panel ------------------------- */

  // renderStatus accepts an optional modePayload from /api/autonomous/mode/status.
  // When supplied it is used for the Autonomous Mode panel instead of the nested
  // autonomous_mode field from /api/autonomous/status, ensuring the panel always
  // reads from the correct source of truth and cannot diverge.
  function renderStatus(payload, modePayload) {
    state.status = payload;
    state.modePayload = modePayload;
    const cfg = (payload && payload.config) || {};
    const auto = modePayload || (payload && payload.autonomous_mode) || {};
    const accountContext = auto.account_context || accountContextFromConnection(auto.connection || {});
    const modeState = auto.mode || {};
    const connection = auto.connection || {};
    const readiness = auto.readiness || {};
    const gates = readiness.gates || {};
    // Derive halted from the mode payload's emergency_stop gate (authoritative
    // source when modePayload is present). Falls back to the top-level flag
    // when the /mode/status fetch failed and only the outer payload is available.
    const halted = modePayload ? !!gates.emergency_stop_active
      : !!payload.emergency_stop_file_exists;
    state.paperAdapterConfigured = !!payload.paper_adapter_configured;
    const previousAutonomousModeOn = state.autonomousModeOn;
    state.autonomousModeOn = modeState.operating_state === 'ON';
    state.detectedAccountType = accountContext.detected;
    state.accountMode = accountContext.mode;
    state.activeEndpoints = ENDPOINTS[state.accountMode] || null;
    state.liveAccountId = accountContext.accountId || '';

    // Emit a clear ON/OFF transition entry in the activity log whenever the
    // operating state flips.  This covers every path (operator clicks,
    // lifecycle worker auto-off, SPY gate halts, single-trade no-trade auto-off),
    // not just UI-initiated activations.
    if (typeof previousAutonomousModeOn === 'boolean'
        && previousAutonomousModeOn !== state.autonomousModeOn) {
      if (state.autonomousModeOn) {
        logActivity('success', '=== AUTONOMOUS TRADING ON ===');
      } else {
        logActivity('info', '=== AUTONOMOUS TRADING OFF ===');
      }
    } else if (typeof previousAutonomousModeOn !== 'boolean') {
      // First status render after page load — emit a baseline so the operator
      // sees the current state in the log even without a transition.
      if (state.autonomousModeOn) {
        logActivity('success', '=== AUTONOMOUS TRADING ON (current state) ===');
      } else {
        logActivity('info', '=== AUTONOMOUS TRADING OFF (current state) ===');
      }
    }

    const matchStatus = connection.paper_live_match_status || 'Unknown';

    // --- Mode state chip (non-interactive status indicator) ---
    const modeChip = $('modeStateChip');
    const modeDescEl = $('modeStateDesc');
    if (modeChip) {
      let chipClass, descText;
      if (halted) {
        modeChip.textContent = 'AUTONOMOUS BLOCKED';
        chipClass = 'mode-chip-blocked';
        descText = 'Emergency stop is active. Autonomous mode cannot be activated.';
      } else if (state.autonomousModeOn) {
        const modeLabel = accountContext.label || 'Autonomous';
        const dryRunActive = (modeState.dry_run === true);
        if (accountContext.mode === 'live' && !dryRunActive) {
          const activeCycle = modeState.trading_cycle || 'single_trade';
          modeChip.textContent = activeCycle === 'continuous'
            ? 'LIVE CONTINUOUS AUTONOMOUS ON'
            : 'LIVE SINGLE AUTONOMOUS ON';
          chipClass = 'mode-chip-on';
          descText = activeCycle === 'continuous'
            ? 'Actual live continuous trading is active — real orders may be submitted on each cycle.'
            : 'Actual live trading is active — real orders may be submitted.';
        } else if (accountContext.mode === 'live' && dryRunActive) {
          modeChip.textContent = 'LIVE DRY-RUN ON';
          chipClass = 'mode-chip-on';
          descText = 'Live dry-run is active — no real orders are submitted.';
        } else {
          modeChip.textContent = modeLabel.toUpperCase() + ' AUTONOMOUS ON';
          chipClass = 'mode-chip-on';
          descText = 'Paper autonomous lifecycle is active.';
        }
      } else if (readiness.status === 'Not Ready') {
        modeChip.textContent = 'AUTONOMOUS OFF';
        chipClass = 'mode-chip-not-ready';
        descText = 'One or more readiness gates are failing. Activation is blocked.';
      } else {
        modeChip.textContent = 'AUTONOMOUS OFF';
        chipClass = 'mode-chip-off';
        descText = 'Robot is not currently allowed to open autonomous trades.';
      }
      modeChip.className = 'mode-state-chip ' + chipClass;
      if (modeDescEl) modeDescEl.textContent = descText;
    }

    // --- Readiness checks (passive indicators, not buttons) ---
    const readinessList = $('readinessList');
    if (readinessList) {
      readinessList.innerHTML = '';
      const matchLabel = 'MATCH ' + matchStatus.toUpperCase();
      const matchOk = matchStatus === 'Verified';
      const matchCls = matchOk ? 'pass' : (matchStatus === 'Mismatch' ? 'fail' : 'warn');
      const providerReady = payload.signal_provider_ready === true;
      const readinessChecks = [
        { label: 'TWS connected', ok: connection.status === 'Connected', cls: null },
        { label: matchLabel, ok: matchOk, cls: matchCls },
      ];
      if (accountContext.mode === 'live') {
        readinessChecks.push(
          { label: 'LIVE MODE CONFIRMED', ok: !!gates.live_mode, cls: null },
          { label: 'LIVE AUTONOMOUS ENABLED', ok: !!gates.live_enabled, cls: null },
          { label: 'ACCOUNT ID VERIFIED', ok: !!gates.account_id_verified, cls: null },
          { label: 'SIGNAL PROVIDER READY', ok: !!gates.signal_provider_ready, cls: null },
          { label: 'EMERGENCY STOP INACTIVE', ok: !gates.emergency_stop_active, cls: null }
        );
        if (selectedTradingCycle() === 'continuous') {
          readinessChecks.push({
            label: 'LIVE CONTINUOUS ENABLED',
            ok: !!gates.live_continuous_enabled,
            cls: null,
          });
        }
      }
      if (providerReady && accountContext.mode !== 'live') {
        readinessChecks.push({ label: 'SIGNAL PROVIDER READY', ok: true, cls: null });
      } else if (accountContext.mode !== 'live' && (payload.warning || payload.signal_provider_ready === false)) {
        readinessChecks.push({ label: 'STATIC PROVIDER', ok: false, cls: 'warn' });
      }
      readinessChecks.forEach(function (chk) {
        const item = document.createElement('span');
        item.className = 'readiness-item readiness-' + (chk.cls || (chk.ok ? 'pass' : 'fail'));
        item.textContent = (chk.ok ? '\u2713 ' : '\u2717 ') + chk.label;
        readinessList.appendChild(item);
      });
    }

    const grid = $('statusGrid');
    grid.innerHTML = '';
    const rows = [
      ['Autonomous Mode status', modeState.operating_state || 'OFF'],
      ['TWS connection status', connection.status || (payload.connected ? 'Connected' : 'Disconnected')],
      ['Selected connection type', connection.selected_connection_type || '—'],
      ['Verified running TWS session/account type', connection.running_account_type || '—'],
      ['Detected account ID', connection.running_account_id || '—'],
      ['Paper/Live match status', matchStatus],
      ['Dashboard account context', accountContext.label || 'Blocked'],
      ['Latest autonomous readiness status', readiness.status || 'Not Ready'],
      ['Latest warning/error message', readiness.message || payload.paper_adapter_reason || payload.warning || '—'],
      ['Last status refresh timestamp', fmtTimestamp(modeState.last_status_refresh)],
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

    const modeBtn = $('btnAutonomousModeToggle');
    const actualLiveBtn = $('btnActualLiveTrading');
    const modeGateReasons = $('modeGateReasons');
    if (modeBtn) {
      modeBtn.textContent = state.autonomousModeOn
        ? 'Turn Autonomous Mode OFF'
        : (accountContext.mode === 'live' ? 'Activate Live Dry-Run' : 'Activate Autonomous Mode');
      const ready = readiness.status === 'Ready' && matchStatus === 'Verified' && !halted;
      modeBtn.disabled = !state.autonomousModeOn && !ready;
      modeBtn.title = state.autonomousModeOn
        ? 'Halt autonomous trading. Filled positions are not liquidated.'
        : (ready ? 'Turn Autonomous Mode ON.' :
          'Disabled: ' + ((gates.reasons || []).join('; ') || readiness.message || 'not ready'));

      // Show or hide the Actual Live Trading button.
      // Visible for live accounts when mode is OFF and readiness gates pass.
      // Continuous cycle additionally requires the live_continuous_enabled gate.
      if (actualLiveBtn) {
        const cycle = selectedTradingCycle();
        const continuousGateOk = cycle !== 'continuous' || !!gates.live_continuous_enabled;
        const showActualLive = accountContext.mode === 'live' && !state.autonomousModeOn
          && ready && continuousGateOk;
        actualLiveBtn.style.display = showActualLive ? '' : 'none';
        actualLiveBtn.disabled = !showActualLive;
      }

      // Show gate reasons visibly in the panel when the button is disabled.
      if (modeGateReasons) {
        if (!state.autonomousModeOn && !ready) {
          let reasonText;
          if (gates.ready && !ready) {
            // Backend gates pass but mode-level check is still blocking.
            let extra = '';
            if (halted) {
              extra = 'Emergency stop is active.';
            } else if (matchStatus !== 'Verified') {
              extra = `Connection not verified (${matchStatus}).`;
            }
            reasonText = 'UI readiness mismatch: backend gates are ready but activation is blocked.'
              + (extra ? ' ' + extra : '');
          } else {
            const reasons = gates.reasons || [];
            reasonText = reasons.length
              ? reasons.join(' · ')
              : (readiness.message || 'Not ready — check connection and readiness gates.');
          }
          modeGateReasons.textContent = reasonText;
          modeGateReasons.hidden = false;
        } else {
          modeGateReasons.textContent = '';
          modeGateReasons.hidden = true;
        }
      }
    }
  }

  async function refreshStatus() {
    try {
      // Fetch general status and Paper/Live verification first. When the
      // detected account is Live, switch the mode panel to the live runner
      // status so paper-only gate failures are not shown to live operators.
      const [data, modeData] = await Promise.all([
        getJson('/api/autonomous/status'),
        getJson('/api/autonomous/mode/status'),
      ]);
      const connection = (modeData && modeData.connection) || {};
      const context = accountContextFromConnection(connection);
      let displayModeData = normalisePaperModePayload(modeData);
      if (context.detected === 'live') {
        let liveData = null;
        let liveError = null;
        try {
          liveData = await getJson('/api/autonomous/live/status');
        } catch (err) {
          liveError = err;
        }
        displayModeData = normaliseLiveModePayload(modeData, liveData, liveError);
        state.activeRunnerStatus = liveData;
      } else {
        state.activeRunnerStatus = null;
      }
      renderStatus(data, displayModeData);
      if (data.cash_snapshot) renderCashSnapshot(data.cash_snapshot);
      setFeedback('Status refreshed.', 'success');
      refreshRunnerStatus();
      refreshAutonomousTrades();
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

  /* ---- autonomous activation confirmation modal ---- */

  function setLiveConfirmVisible(visible) {
    const block = $('liveConfirmFields');
    const input = $('liveExpectedAccountId');
    if (block) block.hidden = !visible;
    if (input) {
      input.value = '';
      input.required = !!visible;
    }
  }

  function openAutonomousConfirm() {
    if (state.autonomousModeOn) {
      logActivity('info', 'Operator clicked Turn Autonomous Mode OFF');
      haltAutonomousMode();
      return;
    }
    logActivity('info', 'Operator clicked Activate Autonomous Mode');
    const overlay = $('paperConfirmOverlay');
    const planEl = $('paperConfirmPlan');
    const titleEl = $('paperConfirmTitle');
    const confirmText = $('autonomousConfirmText');
    const confirmButton = $('paperConfirmGo');
    const accountIdEl = $('liveDetectedAccountId');
    const expectedInput = $('liveExpectedAccountId');
    const conn = (state.modePayload && state.modePayload.connection) || {};
    const accountType = (conn.running_account_type || 'unknown').toUpperCase();
    const accountId = conn.running_account_id || state.liveAccountId || '';
    const cycle = selectedTradingCycle();
    const cycleLabel = cycle === 'continuous' ? 'Continuous Trading' : 'Single Trade';
    const isLive = state.accountMode === 'live';
    setLiveConfirmVisible(isLive);
    if (accountIdEl) accountIdEl.textContent = accountId || 'unavailable';
    if (expectedInput) expectedInput.placeholder = accountId || 'Detected account ID';
    if (titleEl) {
      titleEl.textContent = isLive
        ? 'Turn Autonomous Mode ON for LIVE account?'
        : 'Turn Autonomous Mode ON?';
    }
    if (confirmText) {
      if (isLive) {
        confirmText.textContent =
          'Detected account type: LIVE. Account ID: ' + (accountId || 'unavailable') + '. ' +
          'Trading Cycle: ' + cycleLabel + '. Live dry-run is the dashboard default; ' +
          'no real orders will be submitted unless backend live flags and adapters permit it.';
      } else {
        confirmText.textContent =
          'Turn Autonomous Mode ON for ' + accountType + ' account? ' +
          'TWS Robot will begin autonomous paper trading using this account context. ' +
          'Only paper (simulated) orders are supported. No real orders will be placed. ' +
          'Trading Cycle: ' + cycleLabel + '.';
      }
    }
    if (confirmButton) {
      confirmButton.textContent = isLive ? 'Turn ON (Live Dry-Run)' : 'Turn ON (Paper Mode)';
    }
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

  function hidePaperConfirm() {
    $('paperConfirmOverlay').style.display = 'none';
  }

  function cancelPaperConfirm() {
    logActivity('info', 'Activation modal cancelled by operator');
    hidePaperConfirm();
  }

  async function confirmAutonomousActivation() {
    const cycle = selectedTradingCycle();
    const cycleLabel = cycle === 'continuous' ? 'Continuous Trading' : 'Single Trade';
    const isLive = state.accountMode === 'live';
    const accountModeLabel = isLive ? 'Live account' : 'Paper account';
    const endpoint = currentEndpoint('activate');
    if (!endpoint) {
      const reason = 'Activation blocked: account type is unknown or mismatched.';
      logActivity('warning', reason);
      setFeedback(reason, 'error');
      return;
    }
    const expectedAccountId = String(state.liveAccountId || '').trim();
    if (isLive) {
      const typed = String(($('liveExpectedAccountId') || {}).value || '').trim();
      if (!expectedAccountId || typed.toUpperCase() !== expectedAccountId.toUpperCase()) {
        const reason = 'Live activation blocked: type the detected account ID exactly.';
        logActivity('warning', reason);
        setFeedback(reason, 'error');
        return;
      }
    }
    hidePaperConfirm();
    logActivity('info', 'Activation confirmed: ' + cycleLabel + ' / ' + accountModeLabel);
    setFeedback('Activating Autonomous Mode…');
    try {
      const requestBody = isLive
        ? {
          trading_cycle: cycle,
          confirm: true,
          account_mode: 'live',
          expected_account_id: expectedAccountId,
          confirmed_by: 'dashboard',
          dry_run: true,
        }
        : { trading_cycle: cycle, confirm: true };
      const body = await postJson(endpoint, requestBody);
      const decision = body.run?.decision;
      if (decision) renderProposal(decision);
      const status = body.status || 'unknown';
      const runStatus = body.run?.status;
      const reason = body.run?.rejection_reason || decision?.rejection_reason || '';
      let kind = 'error';
      if (status === 'activated') {
        kind = 'success';
      } else if (status === 'no_trade' || runStatus === 'no_trade') {
        kind = 'info';
      } else if (decision?.status === 'market_not_suitable') {
        kind = 'warning';
      }

      // Log detailed activity entries based on the response
      const marketGate = decision?.market_gate;
      if (marketGate && (marketGate.open != null || marketGate.current != null)) {
        const openStr = Number.isFinite(marketGate.open) ? marketGate.open.toFixed(2) : '?';
        const currStr = Number.isFinite(marketGate.current) ? marketGate.current.toFixed(2) : '?';
        const priceInfo = `SPY open=${openStr}, current=${currStr} (source: yfinance, ~15 min delayed)`;
        if (marketGate.bullish === true) {
          logActivity('success', `SPY gate passed: current price above opening price — ${priceInfo}`);
        } else if (marketGate.bullish === false) {
          logActivity('warning', `SPY gate failed: current price <= opening price — ${priceInfo}`);
        }
      } else if (marketGate && marketGate.bullish === true) {
        logActivity('success', 'SPY gate passed: current price above opening price');
      } else if (marketGate && marketGate.bullish === false) {
        logActivity('warning', 'SPY gate failed: current price <= opening price');
      }

      if (status === 'activated' && !reason) {
        logActivity('success', '=== AUTONOMOUS TRADING ON ===');
        logActivity('success', 'Autonomous Mode activated successfully');
      } else if (status === 'no_trade' || runStatus === 'no_trade') {
        logActivity('info', 'No Trade: ' + (reason || 'no qualifying candidates found'));
        logActivity('info', cycleLabel + ' ended with NO TRADE; Autonomous Mode turned OFF');
        logActivity('info', '=== AUTONOMOUS TRADING OFF ===');
      } else if (reason) {
        logActivity('warning', 'Autonomous Mode result: ' + status + ' — ' + reason);
        if (body.run?.mode_turned_off) {
          logActivity('info', 'Autonomous Mode turned OFF');
          logActivity('info', '=== AUTONOMOUS TRADING OFF ===');
        }
      } else {
        logActivity(kind, 'Autonomous Mode result: ' + status);
      }

      setFeedback('Autonomous Mode result: ' + status + (reason ? ' — ' + reason : ''),
        kind);
      refreshStatus();
      refreshAudit();
    } catch (err) {
      const errMsg = (err && err.message) || String(err);
      logActivity('error', 'Autonomous Mode activation failed: ' + errMsg);
      setFeedback('Autonomous Mode activation failed: ' + errMsg, 'error');
    }
  }

  function selectedTradingCycle() {
    const selected = document.querySelector('input[name="tradingCycle"]:checked');
    return selected ? selected.value : 'single_trade';
  }

  async function haltAutonomousMode() {
    logActivity('info', 'Operator requested Autonomous Mode OFF');
    setFeedback('Turning Autonomous Mode OFF…');
    try {
      const payload = {
        reason: 'Operator turned Autonomous Mode OFF from dashboard',
      };
      if (state.accountMode === 'live') {
        await postJson(ENDPOINTS.live.halt, payload);
      } else if (state.accountMode === 'paper') {
        await postJson(ENDPOINTS.paper.halt, payload);
      } else if (state.autonomousModeOn) {
        // Safety-first: if mode appears ON but account context is blocked,
        // attempt both halt endpoints so we do not leave live mode running.
        logActivity(
          'warning',
          'Ambiguous account context while mode is ON; attempting both live and paper halt endpoints.'
        );
        const errors = [];
        let halted = false;
        for (const endpoint of [ENDPOINTS.live.halt, ENDPOINTS.paper.halt]) {
          try {
            await postJson(endpoint, payload);
            halted = true;
          } catch (err) {
            errors.push((err && err.message) || String(err));
          }
        }
        if (!halted) {
          throw new Error(errors.join(' | ') || 'No halt endpoint accepted the request');
        }
      } else {
        await postJson(ENDPOINTS.paper.halt, payload);
      }
      logActivity('success', 'Autonomous Mode turned OFF. Filled positions were not liquidated.');
      logActivity('info', '=== AUTONOMOUS TRADING OFF ===');
      setFeedback('Autonomous Mode is OFF.', 'success');
      refreshStatus();
      refreshAudit();
    } catch (err) {
      const errMsg = (err && err.message) || String(err);
      logActivity('error', 'Failed to halt Autonomous Mode: ' + errMsg);
      setFeedback('Failed to halt Autonomous Mode: ' + errMsg, 'error');
    }
  }

  async function triggerEmergencyStop() {
    if (!window.confirm(
      '🚨 EMERGENCY STOP\n\nThis will create the EMERGENCY_STOP file and ' +
      'block all subsequent autonomous trading runs.\n\nProceed?')) {
      return;
    }
    logActivity('warning', 'Emergency stop clicked by operator');
    setFeedback('Triggering emergency stop…');
    try {
      await postJson('/api/autonomous/emergency-stop',
        { reason: 'Manual halt from autonomous trading dashboard' });
      logActivity('error', 'Emergency stop activated. All autonomous trading blocked.');
      setFeedback('Emergency stop activated.', 'success');
      refreshStatus();
      refreshAudit();
    } catch (err) {
      const errMsg = (err && err.message) || String(err);
      logActivity('error', 'Emergency stop failed: ' + errMsg);
      setFeedback('Emergency stop failed: ' + errMsg, 'error');
    }
  }

  /* ------------------------- autonomous lifecycle runner ------------------------- */

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
    const mode = (payload && payload.account_mode) || state.accountMode;
    if (!gates) {
      const msg = state.activeEndpoints
        ? 'Runner status unavailable'
        : 'Activation blocked until account type is verified';
      badges.innerHTML = '<span class="badge badge-muted">' + msg + '</span>';
      if (btn) btn.disabled = true;
      return;
    }
    const items = mode === 'live'
      ? [
        ['TWS connected', gates.connected],
        ['Live account mode confirmed', gates.live_mode],
        ['Live autonomous enabled', gates.live_enabled],
        ['Account ID verified', gates.account_id_verified],
        ['Signal provider ready', gates.signal_provider_ready],
        ['Emergency stop inactive', !gates.emergency_stop_active],
        ['Open live trades below limit',
          gates.open_live_trades < gates.max_open_live_trades],
        ['Daily live trade limit not reached',
          gates.live_trades_today < gates.max_live_trades_per_day],
        ['Deployable cash above minimum',
          Number(gates.deployable_cash || 0) >= Number(gates.min_deployable_cash || 0)],
      ]
      : [
        ['Connected', gates.connected],
        ['Paper mode', gates.paper_mode],
        ['Paper adapter', gates.paper_adapter_ready],
        ['Signal provider', gates.signal_provider_ready],
        ['Runner enabled', gates.runner_enabled],
        ['No emergency stop', !gates.emergency_stop_active],
      ];
    if (mode === 'live' && selectedTradingCycle() === 'continuous') {
      items.splice(3, 0, ['Live continuous enabled', gates.live_continuous_enabled]);
    }
    items.forEach(([label, ok]) => {
      const b = document.createElement('span');
      b.className = 'badge ' + (ok ? 'badge-success' : 'badge-warning');
      b.textContent = label + ': ' + (ok ? 'OK' : 'NO');
      b.setAttribute('aria-label', label + ' ' + (ok ? 'OK' : 'not ready'));
      badges.appendChild(b);
    });
    const occ = document.createElement('span');
    occ.className = 'badge badge-muted';
    occ.textContent = mode === 'live'
      ? ('Open live: ' + gates.open_live_trades + '/' + gates.max_open_live_trades)
      : ('Open: ' + gates.open_autonomous_trades + '/' +
        gates.max_open_autonomous_trades);
    badges.appendChild(occ);
    if (mode === 'live') {
      const cash = document.createElement('span');
      cash.className = 'badge badge-muted';
      cash.textContent = 'Deployable: ' + fmtMoney(gates.deployable_cash);
      badges.appendChild(cash);
    }

    if (reasonsEl) {
      reasonsEl.innerHTML = '';
      (gates.reasons || []).forEach((r) => {
        const li = document.createElement('li');
        li.textContent = r;
        reasonsEl.appendChild(li);
      });
    }
    if (btn) {
      const effectiveReady = mode === 'live' && selectedTradingCycle() === 'continuous'
        ? (gates.ready && gates.live_continuous_enabled)
        : gates.ready;
      btn.disabled = !effectiveReady;
      btn.title = effectiveReady ? 'Run one ' + mode + ' autonomous cycle.'
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
      const endpoint = currentEndpoint('status');
      if (!endpoint) {
        renderRunnerGates(null);
        return;
      }
      const body = await getJson(endpoint);
      const payload = state.accountMode === 'live'
        ? {
          account_mode: 'live',
          runner_config: body.live_runner_config,
          gates: body.gates,
        }
        : { ...body, account_mode: 'paper' };
      state.activeRunnerStatus = body;
      renderRunnerGates(payload);
    } catch (err) {
      setRunnerFeedback('Failed to load runner status: ' + err.message, 'error');
    }
  }

  async function refreshAutonomousTrades() {
    try {
      const endpoint = currentEndpoint('trades');
      if (!endpoint) {
        renderAutonomousTrades({});
        return;
      }
      const body = await getJson(endpoint);
      renderAutonomousTrades(body);
    } catch (err) {
      setRunnerFeedback('Failed to load autonomous trades: ' + err.message, 'error');
    }
  }

  async function runAutonomousCycleOnce() {
    const endpoint = currentEndpoint('runOnce');
    if (!endpoint) {
      setRunnerFeedback('Run-once blocked until account type is verified.', 'error');
      return;
    }
    setRunnerFeedback('Running ' + state.accountMode + ' robot once…');
    try {
      const body = await postJson(endpoint, {});
      const status = body.status || 'unknown';
      const msg = status === 'executed' || status === 'dry_run_executed'
        ? (state.accountMode === 'live'
          ? 'Live autonomous cycle accepted by runner.'
          : 'Paper trade executed and recorded.')
        : 'Runner: ' + status + (body.rejection_reason ? ' — ' + body.rejection_reason : '');
      setRunnerFeedback(
        msg,
        (status === 'executed' || status === 'dry_run_executed') ? 'success' : 'warning'
      );
      refreshRunnerStatus();
      refreshAutonomousTrades();
      refreshAudit();
    } catch (err) {
      setRunnerFeedback('Run-once failed: ' + err.message, 'error');
    }
  }

  async function evaluateExitsNow() {
    const endpoint = currentEndpoint('evaluateExits');
    if (!endpoint) {
      setRunnerFeedback('Exit evaluation blocked until account type is verified.', 'error');
      return;
    }
    setRunnerFeedback('Evaluating exits…');
    try {
      const body = await postJson(endpoint, {});
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

  /* ----------------------- Actual Live Trading modal ----------------------- */

  function openActualLiveConfirm() {
    logActivity('info', 'Operator clicked Actual Live Trading');
    const overlay = $('actualLiveConfirmOverlay');
    const detectedEl = $('actualLiveDetectedId');
    const conn = (state.modePayload && state.modePayload.connection) || {};
    const accountId = conn.running_account_id || state.liveAccountId || '';
    if (detectedEl) detectedEl.textContent = accountId || 'unavailable';

    // Show selected cycle in the modal title and warn strongly for continuous
    const cycle = selectedTradingCycle();
    const cycleLabelEl = $('actualLiveCycleLabel');
    const continuousWarningEl = $('actualLiveContinuousWarning');
    if (cycleLabelEl) {
      cycleLabelEl.textContent = cycle === 'continuous'
        ? 'Actual Live Continuous Trading'
        : 'Actual Live Single Trade';
    }
    if (continuousWarningEl) {
      continuousWarningEl.style.display = cycle === 'continuous' ? '' : 'none';
    }

    // Clear inputs
    const acctInput = $('actualLiveAccountId');
    const operatorInput = $('actualLiveOperator');
    const phraseInput = $('actualLivePhrase');
    const riskAck = $('actualLiveRiskAck');
    if (acctInput) acctInput.value = '';
    if (operatorInput) operatorInput.value = '';
    if (phraseInput) phraseInput.value = '';
    if (riskAck) riskAck.checked = false;
    overlay.style.display = 'flex';
  }

  function hideActualLiveConfirm() {
    $('actualLiveConfirmOverlay').style.display = 'none';
  }

  function cancelActualLiveConfirm() {
    logActivity('info', 'Actual Live Trading modal cancelled by operator');
    hideActualLiveConfirm();
  }

  async function confirmActualLiveActivation() {
    const conn = (state.modePayload && state.modePayload.connection) || {};
    const detectedAccountId = (conn.running_account_id || state.liveAccountId || '').trim();
    const typedAccountId = ($('actualLiveAccountId') || {}).value || '';
    const operator = ($('actualLiveOperator') || {}).value || '';
    const phrase = ($('actualLivePhrase') || {}).value || '';
    const riskAck = ($('actualLiveRiskAck') || {}).checked;

    // Client-side pre-validation
    if (!typedAccountId.trim() || typedAccountId.trim().toUpperCase() !== detectedAccountId.toUpperCase()) {
      setFeedback('Account ID does not match detected account.', 'error');
      logActivity('error', 'Actual Live: account ID mismatch');
      return;
    }
    if (!operator.trim()) {
      setFeedback('Operator identifier is required.', 'error');
      logActivity('error', 'Actual Live: operator identifier missing');
      return;
    }
    if (phrase.trim() !== ACTUAL_LIVE_CONFIRMATION_PHRASE) {
      setFeedback('Confirmation phrase does not match.', 'error');
      logActivity('error', 'Actual Live: confirmation phrase mismatch');
      return;
    }
    if (!riskAck) {
      setFeedback('You must acknowledge real money risk.', 'error');
      logActivity('error', 'Actual Live: risk acknowledgement not checked');
      return;
    }

    hideActualLiveConfirm();
    const tradingCycle = selectedTradingCycle();
    const cycleLabel = tradingCycle === 'continuous' ? 'Continuous Trading' : 'Single Trade';
    logActivity('warning', 'Actual Live Trading (' + cycleLabel + ') confirmed — submitting to backend');
    setFeedback('Activating Actual Live Trading (' + cycleLabel + ')…');

    try {
      const requestBody = {
        confirm: true,
        account_mode: 'live',
        trading_cycle: tradingCycle,
        expected_account_id: typedAccountId.trim(),
        confirmed_by: operator.trim(),
        confirmation_phrase: phrase.trim(),
        acknowledge_real_money_risk: true,
      };
      const body = await postJson('/api/autonomous/live/actual-live/activate', requestBody);
      const outcome = (body.run && body.run.outcome) || body.outcome || 'unknown';
      const decision = body.run && body.run.decision;
      if (decision) renderProposal(decision);

      if (outcome === 'LIVE_ORDER_SUBMITTED') {
        const orderId = (body.run && (body.run.submitted_order_id || (body.run.trade && (body.run.trade.entry_order_id || body.run.trade.order_id)))) || '';
        logActivity('success', 'LIVE ORDER SUBMITTED — Order ID: ' + orderId);
        setFeedback('LIVE ORDER SUBMITTED — Order ID: ' + orderId, 'success');
      } else if (outcome === 'NO_TRADE') {
        const reason = (body.run && body.run.rejection_reason) || 'no qualifying candidates';
        logActivity('info', 'NO TRADE: ' + reason);
        setFeedback('NO TRADE: ' + reason, 'info');
      } else if (outcome === 'LIVE_ORDER_REJECTED') {
        const reason = (body.run && body.run.rejection_reason) || body.error || 'unknown';
        logActivity('error', 'LIVE ORDER REJECTED: ' + reason);
        setFeedback('LIVE ORDER REJECTED: ' + reason, 'error');
      } else {
        logActivity('warning', 'Actual Live result: ' + outcome);
        setFeedback('Actual Live result: ' + outcome, 'warning');
      }
      refreshStatus();
      refreshAudit();
    } catch (err) {
      const errMsg = (err && err.message) || String(err);
      logActivity('error', 'Actual Live Trading activation failed: ' + errMsg);
      setFeedback('Actual Live Trading activation failed: ' + errMsg, 'error');
    }
  }

  /* ------------------------- wire up ------------------------- */

  document.addEventListener('DOMContentLoaded', () => {
    logActivity('info', 'Dashboard loaded; refreshing status');
    $('btnRefreshStatus').addEventListener('click', refreshStatus);
    $('btnScan').addEventListener('click', runScan);
    $('btnPropose').addEventListener('click', runPropose);
    $('btnAutonomousModeToggle').addEventListener('click', openAutonomousConfirm);
    $('btnEmergencyStop').addEventListener('click', triggerEmergencyStop);
    $('paperConfirmCancel').addEventListener('click', cancelPaperConfirm);
    $('paperConfirmGo').addEventListener('click', confirmAutonomousActivation);
    $('btnActualLiveTrading').addEventListener('click', openActualLiveConfirm);
    $('actualLiveCancel').addEventListener('click', cancelActualLiveConfirm);
    $('actualLiveGo').addEventListener('click', confirmActualLiveActivation);

    const btnRunRobot = $('btnRunPaperRobot');
    if (btnRunRobot) btnRunRobot.addEventListener('click', runAutonomousCycleOnce);
    const btnExits = $('btnEvaluateExits');
    if (btnExits) btnExits.addEventListener('click', evaluateExitsNow);
    const btnRefreshTrades = $('btnRefreshAutonomousTrades');
    if (btnRefreshTrades) btnRefreshTrades.addEventListener('click', refreshAutonomousTrades);
    document.querySelectorAll('input[name="tradingCycle"]').forEach((el) => {
      el.addEventListener('change', refreshStatus);
    });

    refreshStatus();
    refreshAudit();
    refreshRunnerStatus();
    refreshAutonomousTrades();
  });
})();
