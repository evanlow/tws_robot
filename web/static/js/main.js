// TWS Robot — main JavaScript

document.addEventListener('DOMContentLoaded', () => {
  console.log('[TWS Robot] UI ready');

  // Auto-enrich symbol cells with company names
  _enrichSymbolNames();
});

const _originalFetch = window.fetch.bind(window);

function _getCsrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta && meta.content) return meta.content;

  const input = document.querySelector('input[name="csrf_token"]');
  return input ? input.value : '';
}

function _isSafeMethod(method) {
  return ['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes((method || 'GET').toUpperCase());
}

function _isSameOriginRequest(resource) {
  const requestUrl = resource instanceof Request ? resource.url : String(resource || '');
  if (!requestUrl) return true;

  try {
    return new URL(requestUrl, window.location.origin).origin === window.location.origin;
  } catch (err) {
    console.debug('[TWS Robot] Unable to resolve request URL for CSRF handling:', err);
    return false;
  }
}

window.fetch = function(resource, init) {
  const method = init?.method || (resource instanceof Request ? resource.method : 'GET');
  if (_isSafeMethod(method) || !_isSameOriginRequest(resource)) {
    return _originalFetch(resource, init);
  }

  const token = _getCsrfToken();
  if (!token) return _originalFetch(resource, init);

  const headers = new Headers(resource instanceof Request ? resource.headers : undefined);
  if (init?.headers) {
    new Headers(init.headers).forEach((value, key) => headers.set(key, value));
  }
  if (!headers.has('X-CSRFToken')) {
    headers.set('X-CSRFToken', token);
  }

  if (resource instanceof Request) {
    return _originalFetch(new Request(resource, { headers }));
  }

  return _originalFetch(resource, { ...init, headers });
};

/**
 * Shared utility: render a markdown-ish string as HTML.
 * Handles ## headings, **bold**, and newlines for simple LLM output.
 * For production use, swap this for a proper markdown library.
 *
 * @param {string} text
 * @returns {string} HTML string
 */
window.renderMarkdown = function renderMarkdown(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm,  '<h2>$1</h2>')
    .replace(/^# (.+)$/gm,   '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g,    '<em>$1</em>')
    .replace(/`(.+?)`/g,      '<code>$1</code>')
    .replace(/\n/g,           '<br>');
};

/**
 * Fetch company names for all ``[data-symbol]`` elements on the page
 * and enrich them with a tooltip (title) and a small subtitle showing
 * the company name.
 *
 * Elements should set ``data-symbol="AAPL"`` to opt in.
 * @private
 */
function _enrichSymbolNames() {
  var elements = document.querySelectorAll('[data-symbol]');
  if (!elements.length) return;

  // Collect unique symbols — only stock-like tickers (letters/digits, optional
  // dot suffix).  Option symbols (e.g. "MRNA 261218P00025000") contain spaces
  // and are skipped to avoid a wasted or failed API call.
  var _tickerRe = /^[A-Z0-9]{1,10}(\.[A-Z]{1,5})?$/;
  var symbolSet = new Set();
  elements.forEach(function(el) {
    var sym = (el.getAttribute('data-symbol') || '').trim().toUpperCase();
    if (sym && _tickerRe.test(sym)) symbolSet.add(sym);
  });
  var symbols = Array.from(symbolSet);
  if (!symbols.length) return;

  fetch('/api/account/symbol-names?symbols=' + encodeURIComponent(symbols.join(',')))
    .then(function(res) { return res.json(); })
    .then(function(data) {
      var names = data.names || {};
      elements.forEach(function(el) {
        var sym = el.getAttribute('data-symbol');
        var name = names[sym];
        if (!name) return;
        // Add tooltip
        el.setAttribute('title', name);
        // Append subtitle if not already added
        if (!el.querySelector('.symbol-name')) {
          var sub = document.createElement('span');
          sub.className = 'symbol-name';
          sub.textContent = name;
          el.appendChild(sub);
        }
      });
    })
    .catch(function(err) {
      console.debug('[TWS Robot] Symbol name enrichment failed:', err);
    });
}

/**
 * Re-run symbol enrichment on demand (e.g. after dynamic content loads).
 * Call this after inserting new ``[data-symbol]`` elements into the DOM.
 */
window.enrichSymbolNames = _enrichSymbolNames;
