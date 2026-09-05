/*
Formcraft by catapultaiwork — https://catapultaiwork.com
Source-available with required attribution; see LICENSE.
Personal and commercial use is allowed. Every hosted form must retain the small
"Powered by catapultaiwork" link. There is no builder setting to hide it.
People controlling the source can edit it, but the license requires this credit.
This is a custom attribution license, not standard MIT or OSI-approved open source.
*/

/* Form builder: holds the form in memory, renders it, and saves as JSON. */

const OPTION_TYPES = window.OPTION_TYPES;
const SCALE_TYPES = window.SCALE_TYPES;

const els = {
  title: document.getElementById('f-title'),
  description: document.getElementById('f-description'),
  accent: document.getElementById('f-accent'),
  confirm: document.getElementById('f-confirm'),
  meetingUrl: document.getElementById('f-meeting-url'),
  meetingLabel: document.getElementById('f-meeting-label'),
  published: document.getElementById('f-published'),
  voice: document.getElementById('f-ai-voice'),
  sections: document.getElementById('sections'),
  addSection: document.getElementById('add-section'),
  save: document.getElementById('save-form'),
  del: document.getElementById('delete-form'),
  state: document.getElementById('save-state'),
  headTitle: document.getElementById('head-title'),
  feedback: document.getElementById('builder-feedback'),
};

let state = window.FORM_DATA
  ? {
      title: window.FORM_DATA.title,
      description: window.FORM_DATA.description,
      display_mode: window.FORM_DATA.display_mode,
      accent: window.FORM_DATA.accent,
      is_published: window.FORM_DATA.is_published,
      ai_voice_enabled: Boolean(window.FORM_DATA.ai_voice_enabled),
      confirm_msg: window.FORM_DATA.confirm_msg,
      meeting_url: window.FORM_DATA.meeting_url,
      meeting_label: window.FORM_DATA.meeting_label,
      sections: window.FORM_DATA.sections.map((s) => ({
        id: s.id,
        title: s.title,
        description: s.description,
        questions: s.questions.map((q) => ({
          id: q.id,
          type: q.type,
          label: q.label,
          help_text: q.help_text,
          placeholder: q.placeholder,
          required: q.required,
          options: q.options,
          config: q.config,
        })),
      })),
    }
  : {
      title: '',
      description: '',
      display_mode: 'single',
      accent: '#4f46e5',
      is_published: false,
      ai_voice_enabled: false,
      confirm_msg: 'Thanks — your response has been recorded.',
      meeting_url: '',
      meeting_label: 'Book a meeting',
      sections: [{ title: '', description: '', questions: [blankQuestion()] }],
    };

function blankQuestion() {
  return {
    type: 'short_text',
    label: '',
    help_text: '',
    placeholder: '',
    required: false,
    options: [],
    config: {},
  };
}

function markDirty() {
  els.state.textContent = 'Unsaved changes';
  els.state.classList.add('is-dirty');
}

function showFeedback(kind, message, details = []) {
  els.feedback.className = `alert alert-${kind} builder-feedback`;
  els.feedback.replaceChildren();

  const lead = document.createElement('strong');
  lead.textContent = message;
  els.feedback.append(lead);
  if (details.length) {
    const list = document.createElement('ul');
    details.forEach((detail) => {
      const item = document.createElement('li');
      item.textContent = detail;
      list.append(item);
    });
    els.feedback.append(list);
  }
  els.feedback.hidden = false;
  els.feedback.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function clearFeedback() {
  els.feedback.hidden = true;
  els.feedback.replaceChildren();
  document.querySelectorAll('.is-invalid').forEach((el) => el.classList.remove('is-invalid'));
}

function validateForm() {
  const errors = [];
  const questions = state.sections.flatMap((section) => section.questions);
  const normalizedQuestionNames = new Set();
  const normalizedSectionNames = new Set();

  if (!state.title.trim()) errors.push('Give the form a name.');
  if (!state.confirm_msg.trim()) errors.push('Add a confirmation message.');
  if (!state.meeting_label.trim()) errors.push('Add meeting button text.');
  if (state.meeting_url.trim()) {
    try {
      const meetingUrl = new URL(state.meeting_url);
      if (meetingUrl.protocol !== 'https:') throw new Error('not https');
    } catch (error) {
      errors.push('Meeting link must be a complete https URL.');
    }
  }
  if (!state.sections.length) errors.push('Add at least one section.');
  if (!questions.length) errors.push('Add at least one question.');
  if (state.sections.length > 50) errors.push('A form can contain at most 50 sections.');
  if (questions.length > 500) errors.push('A form can contain at most 500 questions.');

  state.sections.forEach((section, sectionIndex) => {
    const sectionName = section.title.trim().toLocaleLowerCase();
    if (sectionName && normalizedSectionNames.has(sectionName)) {
      errors.push(`Section ${sectionIndex + 1} has the same name as another section.`);
    }
    if (sectionName) normalizedSectionNames.add(sectionName);
    if (!section.questions.length) {
      errors.push(`Section ${sectionIndex + 1} needs at least one question.`);
    }

    section.questions.forEach((question, questionIndex) => {
      const prefix = `Section ${sectionIndex + 1}, question ${questionIndex + 1}`;
      const questionName = question.label.trim().toLocaleLowerCase();
      if (!questionName) {
        errors.push(`${prefix} needs a name.`);
      } else if (normalizedQuestionNames.has(questionName)) {
        errors.push(`“${question.label.trim()}” is used for more than one question.`);
      }
      if (questionName) normalizedQuestionNames.add(questionName);

      if (OPTION_TYPES.includes(question.type)) {
        const options = question.options.map((option) => option.trim()).filter(Boolean);
        const uniqueOptions = new Set(options.map((option) => option.toLocaleLowerCase()));
        if (options.length < 2) errors.push(`${prefix} needs at least two choices.`);
        if (uniqueOptions.size !== options.length) {
          errors.push(`${prefix} has a repeated choice.`);
        }
      }

      if (SCALE_TYPES.includes(question.type)) {
        const rawMinimum = question.config.min;
        const rawMaximum = question.config.max;
        const minimum = rawMinimum == null && question.type !== 'number' ? 1 : Number(rawMinimum);
        const maximum = rawMaximum == null && question.type !== 'number' ? 5 : Number(rawMaximum);
        const hasMinimum = rawMinimum != null || question.type !== 'number';
        const hasMaximum = rawMaximum != null || question.type !== 'number';
        if ((hasMinimum && !Number.isFinite(minimum)) || (hasMaximum && !Number.isFinite(maximum))) {
          errors.push(`${prefix} needs valid minimum and maximum numbers.`);
        } else if (hasMinimum && hasMaximum && minimum >= maximum) {
          errors.push(`${prefix} needs a maximum greater than its minimum.`);
        }
      }
    });
  });
  return errors;
}

function apiError(body, status) {
  const detail = body?.detail;
  if (typeof detail === 'string') return { message: detail, errors: [] };
  if (detail && typeof detail === 'object') {
    return {
      message: detail.message || 'The form could not be saved.',
      errors: Array.isArray(detail.errors) ? detail.errors.map((item) => item.message) : [],
      field: detail.field,
    };
  }
  if (status >= 500) {
    return { message: 'The server is temporarily unavailable. Your changes remain on this page.', errors: [] };
  }
  return { message: 'The form could not be saved. Check the highlighted fields.', errors: [] };
}

function move(list, index, delta) {
  const target = index + delta;
  if (target < 0 || target >= list.length) return;
  [list[index], list[target]] = [list[target], list[index]];
}

/* ------------------------------------------------------------------ render */

function renderOptions(wrap, question) {
  const list = wrap.querySelector('.opt-list');
  list.innerHTML = '';
  question.options.forEach((value, index) => {
    const row = document.createElement('div');
    row.className = 'opt-row';
    const input = document.createElement('input');
    input.type = 'text';
    input.value = value;
    input.maxLength = 500;
    input.placeholder = `Option ${index + 1}`;
    input.addEventListener('input', () => {
      question.options[index] = input.value;
      markDirty();
    });
    const remove = document.createElement('button');
    remove.className = 'icon-btn danger';
    remove.textContent = '✕';
    remove.addEventListener('click', () => {
      question.options.splice(index, 1);
      renderOptions(wrap, question);
      markDirty();
    });
    row.append(input, remove);
    list.append(row);
  });
}

function renderQuestion(question, sectionIndex, questionIndex) {
  const node = document.getElementById('tpl-question').content.firstElementChild.cloneNode(true);
  const label = node.querySelector('.q-label');
  const type = node.querySelector('.q-type');
  const help = node.querySelector('.q-help');
  const required = node.querySelector('.q-required');
  const optionsWrap = node.querySelector('.q-options');
  const scaleWrap = node.querySelector('.q-scale');
  const min = node.querySelector('.q-min');
  const max = node.querySelector('.q-max');

  label.value = question.label;
  type.value = question.type;
  help.value = question.help_text;
  required.checked = question.required;
  min.value = question.config.min ?? 1;
  max.value = question.config.max ?? 5;

  const syncVisibility = () => {
    optionsWrap.classList.toggle('hidden', !OPTION_TYPES.includes(question.type));
    scaleWrap.classList.toggle('hidden', !SCALE_TYPES.includes(question.type));
  };

  label.addEventListener('input', () => { question.label = label.value; markDirty(); });
  help.addEventListener('input', () => { question.help_text = help.value; markDirty(); });
  required.addEventListener('change', () => { question.required = required.checked; markDirty(); });

  type.addEventListener('change', () => {
    question.type = type.value;
    if (OPTION_TYPES.includes(question.type) && question.options.length === 0) {
      question.options = ['Option 1'];
      renderOptions(optionsWrap, question);
    }
    if (SCALE_TYPES.includes(question.type)) {
      question.config.min = Number(min.value);
      question.config.max = Number(max.value);
    } else {
      question.config = {};
    }
    syncVisibility();
    markDirty();
  });

  min.addEventListener('input', () => { question.config.min = Number(min.value); markDirty(); });
  max.addEventListener('input', () => { question.config.max = Number(max.value); markDirty(); });

  node.querySelector('[data-act="add-opt"]').addEventListener('click', () => {
    question.options.push(`Option ${question.options.length + 1}`);
    renderOptions(optionsWrap, question);
    markDirty();
  });

  node.querySelectorAll('.q-main [data-act]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const list = state.sections[sectionIndex].questions;
      const act = btn.dataset.act;
      if (act === 'del') list.splice(questionIndex, 1);
      if (act === 'up') move(list, questionIndex, -1);
      if (act === 'down') move(list, questionIndex, 1);
      render();
      markDirty();
    });
  });

  renderOptions(optionsWrap, question);
  syncVisibility();
  return node;
}

function renderSection(section, index) {
  const node = document.getElementById('tpl-section').content.firstElementChild.cloneNode(true);
  const title = node.querySelector('.s-title');
  const desc = node.querySelector('.s-desc');
  const questions = node.querySelector('.questions');

  title.value = section.title;
  desc.value = section.description;
  title.addEventListener('input', () => { section.title = title.value; markDirty(); });
  desc.addEventListener('input', () => { section.description = desc.value; markDirty(); });

  section.questions.forEach((question, qi) => {
    questions.append(renderQuestion(question, index, qi));
  });

  node.querySelector('[data-act="add-q"]').addEventListener('click', () => {
    section.questions.push(blankQuestion());
    render();
    markDirty();
  });

  node.querySelectorAll('.section-head [data-act]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const act = btn.dataset.act;
      if (act === 'del') {
        if (state.sections.length === 1) return alert('A form needs at least one section.');
        state.sections.splice(index, 1);
      }
      if (act === 'up') move(state.sections, index, -1);
      if (act === 'down') move(state.sections, index, 1);
      render();
      markDirty();
    });
  });

  return node;
}

function render() {
  els.sections.innerHTML = '';
  state.sections.forEach((section, index) => {
    els.sections.append(renderSection(section, index));
  });
}

/* ------------------------------------------------------------------- wire */

els.title.value = state.title;
els.description.value = state.description;
els.accent.value = state.accent;
els.confirm.value = state.confirm_msg;
els.meetingUrl.value = state.meeting_url;
els.meetingLabel.value = state.meeting_label;
els.published.checked = state.is_published;
els.voice.checked = state.ai_voice_enabled;
els.voice.addEventListener('change', () => { state.ai_voice_enabled = els.voice.checked; markDirty(); });
document.querySelector(`input[name="mode"][value="${state.display_mode}"]`).checked = true;

els.title.addEventListener('input', () => {
  state.title = els.title.value;
  els.headTitle.textContent = state.title || 'New form';
  els.title.classList.remove('is-invalid');
  markDirty();
});
els.description.addEventListener('input', () => { state.description = els.description.value; markDirty(); });
els.accent.addEventListener('input', () => {
  state.accent = els.accent.value;
  document.documentElement.style.setProperty('--accent', state.accent);
  markDirty();
});
els.confirm.addEventListener('input', () => { state.confirm_msg = els.confirm.value; markDirty(); });
els.meetingUrl.addEventListener('input', () => { state.meeting_url = els.meetingUrl.value; markDirty(); });
els.meetingLabel.addEventListener('input', () => { state.meeting_label = els.meetingLabel.value; markDirty(); });
els.published.addEventListener('change', () => { state.is_published = els.published.checked; markDirty(); });
document.querySelectorAll('input[name="mode"]').forEach((radio) => {
  radio.addEventListener('change', () => { state.display_mode = radio.value; markDirty(); });
});

els.addSection.addEventListener('click', () => {
  state.sections.push({ title: '', description: '', questions: [blankQuestion()] });
  render();
  markDirty();
});

els.save.addEventListener('click', async () => {
  clearFeedback();
  const errors = validateForm();
  if (errors.length) {
    if (!state.title.trim()) {
      els.title.classList.add('is-invalid');
      els.title.focus();
    }
    showFeedback('error', 'Fix these problems before saving.', errors);
    return;
  }

  els.save.disabled = true;
  els.state.textContent = 'Saving…';

  const isNew = !window.FORM_ID;
  let res;
  try {
    res = await fetch(isNew ? '/api/forms' : `/api/forms/${window.FORM_ID}`, {
      method: isNew ? 'POST' : 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(state),
    });
  } catch (error) {
    els.save.disabled = false;
    els.state.textContent = 'Not saved';
    showFeedback(
      'error',
      'The server could not be reached. Your changes are still here—check your connection and try again.',
    );
    console.error(error);
    return;
  }

  if (!res.ok) {
    els.save.disabled = false;
    const body = await res.json().catch(() => ({}));
    const error = apiError(body, res.status);
    els.state.textContent = 'Not saved';
    if (error.field === 'title') {
      els.title.classList.add('is-invalid');
      els.title.focus();
    }
    showFeedback('error', error.message, error.errors);
    console.error(body);
    return;
  }

  const data = await res.json();
  if (isNew) {
    if (data.sheet?.status === 'error') {
      sessionStorage.setItem('formcraft-save-notice', JSON.stringify({
        kind: 'warn',
        message: data.sheet.detail,
      }));
    } else if (data.sheet?.created) {
      sessionStorage.setItem('formcraft-save-notice', JSON.stringify({
        kind: 'success',
        message: 'Form saved and its Google Sheet was created.',
      }));
    }
    const setup = data.sheet?.status === 'not_connected' ? '?setup=google' : '';
    window.location.href = `/admin/${data.id}${setup}`;
    return;
  }
  els.save.disabled = false;
  if (data.sheet?.updated) {
    els.state.textContent = 'Saved · Sheet updated';
    showFeedback('success', 'Form saved and Google Sheet updated.');
  } else if (data.sheet?.status === 'error') {
    els.state.textContent = 'Saved · Sheet pending';
    showFeedback('warn', data.sheet.detail);
    console.warn('Google Sheet update:', data.sheet.detail);
  } else {
    els.state.textContent = 'Saved';
  }
  els.state.classList.remove('is-dirty');
});

els.del?.addEventListener('click', async () => {
  if (!confirm('Delete this form and all of its responses? The Google Sheet is not deleted.')) return;
  await fetch(`/api/forms/${window.FORM_ID}`, { method: 'DELETE' });
  window.location.href = '/';
});

document.documentElement.style.setProperty('--accent', state.accent);
render();

try {
  const savedNotice = JSON.parse(sessionStorage.getItem('formcraft-save-notice'));
  if (savedNotice?.message) showFeedback(savedNotice.kind || 'success', savedNotice.message);
  sessionStorage.removeItem('formcraft-save-notice');
} catch (error) {
  sessionStorage.removeItem('formcraft-save-notice');
}


const googleSetupPrompt = document.getElementById('google-setup-prompt');
if (googleSetupPrompt?.hasAttribute('data-open-google-setup')) googleSetupPrompt.showModal();
document.getElementById('google-setup-later')?.addEventListener('click', () => googleSetupPrompt.close());
document.querySelector('[data-attach-google-sheet]')?.addEventListener('click', async (event) => {
  const button = event.currentTarget;
  const status = document.getElementById('google-setup-status');
  button.disabled = true;
  status.hidden = false;
  status.textContent = 'Creating your Google Sheet…';
  try {
    const response = await fetch(`/api/forms/${button.dataset.attachGoogleSheet}/sheet`, { method: 'POST' });
    const data = await response.json();
    status.textContent = data.created ? 'Google Sheet created. Refresh this page after saving any pending edits to see its link.' : (data.detail || 'Could not create a Sheet. Check your Google connection.');
  } catch {
    status.textContent = 'Could not reach the server. Your form is still saved; please try again.';
  } finally { button.disabled = false; }
});
