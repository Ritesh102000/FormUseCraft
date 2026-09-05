/*
Formcraft by catapultaiwork — https://catapultaiwork.com
Source-available with required attribution; see LICENSE.
Personal and commercial use is allowed. Every hosted form must retain the small
"Powered by catapultaiwork" link. There is no builder setting to hide it.
People controlling the source can edit it, but the license requires this credit.
This is a custom attribution license, not standard MIT or OSI-approved open source.
*/

(() => {
  const $ = (id) => document.getElementById(id);
  let draft = null;
  let busy = false;
  function setBusy(value) {
    busy = value;
    ['ai-generate', 'ai-create', 'ai-reset'].forEach((id) => { $(id).disabled = value; });
  }
  function node(tag, text) {
    const el = document.createElement(tag);
    el.textContent = text;
    return el;
  }
  function preview() {
    const root = $('ai-preview');
    root.replaceChildren(node('h2', draft.title), node('p', draft.description));
    draft.sections.forEach((section) => {
      const group = document.createElement('section');
      group.append(node('h3', section.title), node('p', section.description));
      section.questions.forEach((q) => {
        const field = document.createElement('div');
        field.className = 'ai-preview-field';
        field.append(node('strong', q.label + (q.required ? ' *' : '')), node('small', q.type.replaceAll('_', ' ')));
        if (q.help_text) field.append(node('p', q.help_text));
        if (q.options.length) field.append(node('p', q.options.join(' · ')));
        group.append(field);
      });
      root.append(group);
    });
    root.hidden = false;
    $('ai-empty').hidden = true;
    $('ai-create-controls').hidden = false;
    $('ai-notes').textContent = draft.notes;
    $('ai-notes').hidden = !draft.notes;
    $('ai-meeting').checked = draft.meeting_requested;
    $('ai-reset').hidden = false;
    $('ai-generate').textContent = 'Refine draft';
  }
  async function request(url, options) {
    const response = await fetch(url, { ...options, signal: AbortSignal.timeout(90000) });
    let data;
    try { data = await response.json(); } catch { throw new Error('The server could not complete this request. Try again.'); }
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Request failed. Check your input.');
    return data;
  }
  $('ai-builder-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (busy) return;
    const file = $('ai-file').files[0];
    if (file && file.size > 2 * 1024 * 1024) { $('ai-status').textContent = 'Use a reference file up to 2 MB.'; return; }
    const payload = new FormData();
    payload.set('prompt', $('ai-prompt').value);
    payload.set('api_key', $('ai-key').value);
    if (file) payload.set('file', file);
    if (draft) payload.set('previous', JSON.stringify(draft));
    $('ai-key').value = '';
    setBusy(true);
    $('ai-status').textContent = 'Building your draft…';
    try {
      draft = await request('/api/ai/generate', { method: 'POST', body: payload });
      preview();
      $('ai-status').textContent = 'Draft ready. Review it, request a change, or create it in your dashboard.';
    } catch (err) { $('ai-status').textContent = err.message; }
    finally { payload.delete('api_key'); setBusy(false); }
  });
  $('ai-create').addEventListener('click', async () => {
    if (busy || !draft) return;
    setBusy(true);
    $('ai-status').textContent = 'Saving your draft…';
    try {
      const data = await request('/api/ai/create', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ draft, meeting: $('ai-meeting').checked }),
      });
      window.location.assign(`/admin/${encodeURIComponent(data.id)}`);
    } catch (err) { $('ai-status').textContent = err.message; setBusy(false); }
  });
  $('ai-reset').addEventListener('click', () => {
    draft = null;
    $('ai-builder-form').reset();
    $('ai-preview').replaceChildren();
    ['ai-preview', 'ai-create-controls', 'ai-reset'].forEach((id) => { $(id).hidden = true; });
    $('ai-empty').hidden = false;
    $('ai-status').textContent = '';
    $('ai-generate').textContent = 'Generate draft';
  });
})();
