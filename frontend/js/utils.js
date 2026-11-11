/**
 * Small DOM-safety helpers shared by every page.
 *
 * `esc()`       escapes text for innerHTML interpolation.
 * `escAttr()`   escapes a JS string that is embedded in an inline HTML
 *               attribute (e.g. onclick="app.foo(1, ...)").
 * `safeUrl()`   only allows http(s), root-relative, or data:image URLs.
 */
(function () {
  const MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

  window.esc = function (value) {
    return String(value === null || value === undefined ? '' : value)
      .replace(/[&<>"']/g, (ch) => MAP[ch]);
  };

  window.escAttr = function (value) {
    return window.esc(JSON.stringify(String(value === null || value === undefined ? '' : value)));
  };

  window.safeUrl = function (value) {
    const url = String(value === null || value === undefined ? '' : value).trim();
    if (/^(https?:\/\/|\/|data:image\/(?:png|jpe?g|gif|webp);base64,)/i.test(url)) {
      return window.esc(url);
    }
    return '';
  };
})();
