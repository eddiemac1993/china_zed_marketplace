(function () {
'use strict';
const key = 'czConsent';
function read() {
  try {
    const pair = document.cookie.split('; ').find(x => x.startsWith(key + '='));
    const value = pair ? JSON.parse(decodeURIComponent(pair.slice(key.length + 1))) : null;
    const age = value ? Date.now() - value.savedAt : -1;
    return value && value.version === 2 && age >= 0 && age < 180 * 86400000 ? value : null;
  } catch (_) { return null; }
}
window.czConsent = { allows: category => Boolean(read() && read()[category] === true) };
function clearHistory() {
  try { localStorage.removeItem('czRecentlyViewed'); localStorage.removeItem('czFlashSaleEnd'); } catch (_) {}
}
if (!window.czConsent.allows('personalization')) clearHistory();
document.addEventListener('DOMContentLoaded', function () {
  const panel = document.getElementById('cookie-choices');
  const analytics = document.getElementById('consent-analytics');
  const personalization = document.getElementById('consent-personalization');
  if (!panel) return;
  function open() {
    const current = read() || {};
    analytics.checked = current.analytics === true;
    personalization.checked = current.personalization === true;
    panel.hidden = false;
    panel.querySelector('h2').focus();
  }
  window.czOpenCookieChoices = open;
  document.querySelectorAll('[data-cookie-settings]').forEach(button => button.addEventListener('click', open));
  if (!read()) panel.hidden = false;
  else panel.hidden = true;
  panel.querySelectorAll('[data-consent-choice]').forEach(button => button.addEventListener('click', function () {
    const choice = button.dataset.consentChoice;
    const value = {version:2, savedAt:Date.now(), analytics:choice==='accept'||(choice==='save'&&analytics.checked), personalization:choice==='accept'||(choice==='save'&&personalization.checked)};
    document.cookie = key+'='+encodeURIComponent(JSON.stringify(value))+'; Max-Age=15552000; Path=/; SameSite=Lax; Secure';
    if (!read()) { document.getElementById('cookie-status').textContent = 'Your browser could not save this choice. Optional features remain off.'; return; }
    if (!value.personalization) clearHistory();
    panel.hidden = true;
    window.location.reload();
  }));
});
})();
