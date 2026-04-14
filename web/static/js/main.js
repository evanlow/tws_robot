// TWS Robot — main JavaScript

document.addEventListener('DOMContentLoaded', () => {
  console.log('[TWS Robot] UI ready');
});

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
