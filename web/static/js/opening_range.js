// ORB Autonomous Session dashboard (#207). Config + arm/disarm controls only;
// no orders are placed. Live modes are locked; paper-autonomous gated on readiness.
'use strict';

function orbCsrf() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.content : '';
}

function orbEscape(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

async function orbApi(url, method, body) {
  const headers = { 'Content-Type': 'application/json' };
  const token = orbCsrf();
  if (token) headers['X-CSRFToken'] = token;
  const opts = { method, headers };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  let data;
  try { data = await res.json(); } catch (_) { data = {}; }
  return { ok: res.ok, data };
}

function orbName() {
  return document.getElementById('orbName').value.trim();
}

function orbConfigBody() {
  return {
    name: orbName(),
    mode: document.getElementById('orbMode').value,
    symbols: document.getElementById('orbSymbols').value.split(',').map(s => s.trim()).filter(Boolean),
    require_stop: document.getElementById('orbStop').checked,
    require_target: document.getElementById('orbTarget').checked,
    require_bracket: document.getElementById('orbBracket').checked,
    parameters: {
      timezone: document.getElementById('orbTz').value,
      session_open: document.getElementById('orbOpen').value,
      opening_range_minutes: parseInt(document.getElementById('orbRange').value, 10),
      entry_cutoff_time: document.getElementById('orbCutoff').value,
      force_flat_time: document.getElementById('orbFlat').value,
      max_entry_slippage_bps: parseFloat(document.getElementById('orbSlip').value),
      risk_per_trade_equity_pct: parseFloat(document.getElementById('orbRisk').value),
      max_trades_per_symbol_per_session: parseInt(document.getElementById('orbMaxSym').value, 10),
      max_total_orb_trades_per_session: parseInt(document.getElementById('orbMaxTot').value, 10),
      model_a_enabled: document.getElementById('orbModelA').checked,
      model_b_enabled: document.getElementById('orbModelB').checked,
    },
  };
}

async function orbCfgSave() {
  const el = document.getElementById('orbCfgStatus');
  el.textContent = 'Saving…';
  const { ok, data } = await orbApi('/api/orb/strategies', 'POST', orbConfigBody());
  el.textContent = ok ? 'Saved' : 'Error: ' + (data.messages || [data.error || 'Unknown error']).join('; ');
  orbRefresh();
}

async function orbAct(action, body) {
  const el = document.getElementById('orbActStatus');
  el.textContent = '…';
  const { ok, data } = await orbApi(`/api/orb/strategies/${encodeURIComponent(orbName())}/${action}`, 'POST', body || {});
  el.textContent = ok ? action + ' ok' : 'Error: ' + (data.messages || [data.error || 'Unknown error']).join('; ');
  orbRefresh();
}

async function orbEmergency() {
  const { ok, data } = await orbApi('/api/orb/emergency-stop', 'POST', {});
  const el = document.getElementById('orbActStatus');
  el.textContent = ok ? 'emergency stop: all disarmed' : 'Error: ' + (data.messages || [data.error || 'Unknown error']).join('; ');
  orbRefresh();
}

function orbBadge(state) {
  const ok = state === true;
  return `<span style="color:${ok ? '#48bb78' : '#ecc94b'};font-weight:bold;">${ok ? 'YES' : 'NO'}</span>`;
}

async function orbRefresh() {
  const { data } = await orbApi('/api/orb/status', 'GET');
  const box = document.getElementById('orbStatusBox');
  const rows = (data.strategies || []).map(s => {
    const sess = s.session || {};
    const missing = (s.readiness.missing || []).map(orbEscape).join(', ') || 'none';
    return `<tr><td>${orbEscape(s.name)}</td><td>${orbEscape(s.mode)}${s.mode_locked ? ' 🔒' : ''}</td>
      <td>${orbEscape((s.symbols || []).join(', '))}</td><td>${orbBadge(s.readiness.paper_ready)}</td>
      <td>${sess.armed ? 'ARMED ' + orbEscape(sess.armed_for || '') : (sess.disabled_today ? 'DISABLED' : 'idle')}</td>
      <td>${missing}</td></tr>`;
  }).join('');
  box.innerHTML = rows
    ? `<table class="data-table"><thead><tr><th>Strategy</th><th>Mode</th><th>Symbols</th><th>Paper ready</th><th>Session</th><th>Missing gates</th></tr></thead><tbody>${rows}</tbody></table>`
    : '<p class="empty-state">No strategies configured.</p>';
}

document.addEventListener('DOMContentLoaded', orbRefresh);
