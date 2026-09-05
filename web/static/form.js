/*
Formcraft by catapultaiwork — https://catapultaiwork.com
Source-available with required attribution; see LICENSE.
Personal and commercial use is allowed. Every hosted form must retain the small
"Powered by catapultaiwork" link. There is no builder setting to hide it.
People controlling the source can edit it, but the license requires this credit.
This is a custom attribution license, not standard MIT or OSI-approved open source.
*/

/* Public form renderer: handles the three display modes, validation and submit. */

const form = document.getElementById('form');
const intro = document.getElementById('intro');
const progress = document.getElementById('progress');
const backBtn = document.getElementById('back');
const nextBtn = document.getElementById('next');
const submitBtn = document.getElementById('submit');
const done = document.getElementById('done');
const trust = document.getElementById('trust');
const hint = document.getElementById('hint');
const bookingBlock = document.querySelector('[data-booking-block]');
const againBtn = document.getElementById('again');
const nativeSlots = document.getElementById('native-booking-slots');
const bookingTimezone = document.getElementById('booking-timezone');
const confirmBookingBtn = document.getElementById('confirm-booking');
const retryBookingSlotsBtn = document.getElementById('retry-booking-slots');
const bookingSelection = document.getElementById('booking-selection');
const bookingSelectionText = document.getElementById('booking-selection-text');

const mode = window.FORM_MODE;
let steps = [];
let current = 0;
let responseSaving = false;
let responseSaved = false;
let responseId = '';
let bookingToken = '';
let selectedBookingStart = '';
let selectedBookingDate = '';
let viewerTimezone = 'UTC';
let slotsLoading = false;
let availableBookingSlots = [];
let bookingSlotsByDate = new Map();
let bookingMonths = [];
let activeBookingMonthIndex = 0;
let bookingLoadController = null;
const bookingFormatters = new Map();
const BOOKING_LOAD_TIMEOUT_MS = 15000;

function buildSteps() {
  if (mode === 'single') return [];
  if (mode === 'section') return Array.from(document.querySelectorAll('[data-step]'));
  // one_by_one: every question is its own step
  return Array.from(document.querySelectorAll('.field[data-hidden="0"]'));
}

function showStep(index) {
  if (!steps.length) return;
  current = Math.max(0, Math.min(index, steps.length - 1));

  steps.forEach((step, i) => {
    const active = i === current;
    step.hidden = !active;
    if (active) step.classList.add('enter');
  });

  if (mode === 'one_by_one') {
    // Each question is its own step, so show only the section that holds it.
    document.querySelectorAll('[data-step]').forEach((section) => {
      section.hidden = !section.contains(steps[current]);
    });
  }

  if (intro) intro.hidden = current > 0;
  // The trust strip is a first-impression element, not a distraction mid-flow.
  if (trust) trust.hidden = current > 0;
  backBtn.hidden = current === 0;
  nextBtn.hidden = current >= steps.length - 1;
  if (submitBtn) submitBtn.hidden = current < steps.length - 1;
  if (hint) hint.hidden = nextBtn.hidden;

  progress.style.width = `${((current + 1) / steps.length) * 100}%`;
  window.scrollTo({ top: 0, behavior: 'smooth' });

  // preventScroll matters: without it the browser scrolls the field into view
  // and undoes the scroll-to-top above.
  const firstInput = steps[current].querySelector('input, select, textarea');
  if (firstInput) setTimeout(() => firstInput.focus({ preventScroll: true }), 60);
}

function readField(field) {
  const id = field.dataset.question;
  const type = field.dataset.type;
  if (type === 'checkbox') {
    return Array.from(field.querySelectorAll('input:checked')).map((el) => el.value);
  }
  if (type === 'radio' || type === 'scale' || type === 'rating') {
    const picked = field.querySelector('input:checked');
    return picked ? picked.value : '';
  }
  const el = field.querySelector('input, select, textarea');
  return el ? el.value : '';
}

function setError(field, message) {
  const slot = field.querySelector('.field-error');
  slot.textContent = message || '';
  slot.hidden = !message;
  field.classList.toggle('has-error', Boolean(message));
}

function validate(fields) {
  let ok = true;
  fields.forEach((field) => {
    const value = readField(field);
    const required = field.dataset.required === '1';
    const empty = Array.isArray(value) ? value.length === 0 : !String(value).trim();

    if (required && empty) {
      setError(field, 'This question is required.');
      ok = false;
      return;
    }
    if (field.dataset.type === 'email' && !empty && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value)) {
      setError(field, 'Enter a valid email address.');
      ok = false;
      return;
    }
    setError(field, '');
  });
  if (!ok) {
    const first = fields.find((f) => f.classList.contains('has-error'));
    if (first) first.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
  return ok;
}

function fieldsIn(step) {
  if (!step) return Array.from(document.querySelectorAll('.field[data-hidden="0"]'));
  return step.classList.contains('field') ? [step] : Array.from(step.querySelectorAll('.field'));
}

function collect() {
  const payload = {};
  document.querySelectorAll('.field').forEach((field) => {
    payload[field.dataset.question] = readField(field);
  });
  return payload;
}

nextBtn?.addEventListener('click', () => {
  if (validate(fieldsIn(steps[current]))) showStep(current + 1);
});

backBtn?.addEventListener('click', () => showStep(current - 1));

form.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter') return;
  const tag = event.target.tagName;
  if (tag === 'TEXTAREA') return;
  if (!nextBtn.hidden) {
    event.preventDefault();
    nextBtn.click();
  }
});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (responseSaving || responseSaved) return;
  if (!validate(fieldsIn(null))) {
    return;
  }

  if (window.IS_PREVIEW) {
    alert('This form is a draft. Publish it before collecting responses.');
    return;
  }

  responseSaving = true;
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = 'Submitting…';
  }

  try {
    const res = await fetch(`/f/${window.FORM_REF}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(collect()),
    });
    const data = await res.json();

    if (res.status === 422 && data.errors) {
      Object.entries(data.errors).forEach(([qid, message]) => {
        const field = document.querySelector(`[data-question="${qid}"]`);
        if (field) setError(field, message);
      });
      const first = document.querySelector('.has-error');
      if (first) first.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    if (!res.ok) throw new Error(data.detail || 'Something went wrong.');

    responseSaved = true;
    window.dispatchEvent(new CustomEvent('formcraft:handoff', { detail: { stage: window.MEETING_PROVIDER ? 'booking' : 'done' } }));
    responseId = data.id || '';
    bookingToken = data.booking_token || '';
    document.getElementById('done-msg').textContent = data.message;
    form.hidden = true;
    progress.parentElement.hidden = true;
    if (trust) trust.hidden = true;
    const nativeBooking = window.MEETING_PROVIDER === 'google_api';
    done.hidden = nativeBooking;
    if (bookingBlock) bookingBlock.hidden = false;
    if (nativeBooking) {
      document.body.classList.add('booking-stage');
      loadNativeBookingSlots();
      requestAnimationFrame(() => document.getElementById('booking-title')?.focus());
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  } catch (err) {
    alert(err.message || 'Could not submit. Please try again.');
  } finally {
    responseSaving = false;
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Submit form';
    }
  }
});

function browserTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch (_) {
    return 'UTC';
  }
}

function bookingFormatter(name, options, timeZone = viewerTimezone) {
  const key = `${name}:${timeZone}`;
  if (!bookingFormatters.has(key)) {
    bookingFormatters.set(key, new Intl.DateTimeFormat(undefined, {
      ...options,
      timeZone,
    }));
  }
  return bookingFormatters.get(key);
}

function zonedDateKey(value) {
  const parts = bookingFormatter('date-key', {
    year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(new Date(value));
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function calendarDate(dateKey) {
  const [year, month, day] = dateKey.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, day, 12));
}

function bookingDateLabel(dateKey, { short = false } = {}) {
  return bookingFormatter(short ? 'date-short' : 'date-long', {
    weekday: short ? 'short' : 'long',
    month: short ? 'short' : 'long',
    day: 'numeric',
    year: short ? undefined : 'numeric',
  }, 'UTC').format(calendarDate(dateKey));
}

function bookingTimeLabel(value) {
  return bookingFormatter('time', {
    hour: 'numeric', minute: '2-digit',
  }).format(new Date(value));
}

function formatBookingSlot(slot) {
  const dateKey = zonedDateKey(slot.start);
  const crossesMidnight = zonedDateKey(slot.end) !== dateKey;
  const rollover = crossesMidnight ? ' (next day)' : '';
  return `${bookingDateLabel(dateKey)} · ${bookingTimeLabel(slot.start)}–${bookingTimeLabel(slot.end)}${rollover}`;
}

function bookingWallTimeLabel(value) {
  const [hour, minute] = String(value || '').split(':').map(Number);
  if (!Number.isFinite(hour) || !Number.isFinite(minute)) return value || '';
  const period = hour < 12 ? 'AM' : 'PM';
  const displayHour = hour % 12 || 12;
  return `${displayHour}:${String(minute).padStart(2, '0')} ${period}`;
}

function bookingScheduleLabel(schedule = {}) {
  const firstStart = schedule.first_start || '09:00';
  const lastStart = schedule.last_start || '23:00';
  const [lastHour, lastMinute] = lastStart.split(':').map(Number);
  const endMinutes = ((lastHour * 60) + lastMinute + Number(schedule.duration_minutes || 60)) % 1440;
  const endLabel = endMinutes === 0
    ? 'midnight'
    : bookingWallTimeLabel(`${String(Math.floor(endMinutes / 60)).padStart(2, '0')}:${String(endMinutes % 60).padStart(2, '0')}`);
  const weekdays = Array.isArray(schedule.weekdays)
    ? schedule.weekdays.join(',')
    : '0,1,2,3,4,5';
  const daysLabel = weekdays === '0,1,2,3,4,5' ? 'Mon–Sat' : 'selected days';
  const ownerTimezone = schedule.timezone || 'Asia/Kolkata';
  const zoneLabel = ownerTimezone === 'Asia/Kolkata' ? 'IST' : ownerTimezone;
  return `Available hours: ${daysLabel}, ${bookingWallTimeLabel(firstStart)}–${endLabel} ${zoneLabel}. Last meeting starts at ${bookingWallTimeLabel(lastStart)}.`;
}

function groupBookingSlots(slots) {
  const grouped = new Map();
  slots.forEach((slot) => {
    const dateKey = zonedDateKey(slot.start);
    if (!grouped.has(dateKey)) grouped.set(dateKey, []);
    grouped.get(dateKey).push(slot);
  });
  grouped.forEach((daySlots) => {
    daySlots.sort((left, right) => new Date(left.start) - new Date(right.start));
  });
  return new Map([...grouped.entries()].sort(([left], [right]) => left.localeCompare(right)));
}

function showBookingLoading() {
  if (!nativeSlots) return;
  nativeSlots.setAttribute('aria-busy', 'true');
  nativeSlots.innerHTML = `
    <div class="native-booking__loading" role="status">
      <div class="booking-skeleton booking-skeleton--calendar" aria-hidden="true"></div>
      <div class="booking-skeleton booking-skeleton--times" aria-hidden="true"></div>
      <span>Checking live availability…</span>
    </div>`;
  if (bookingSelection) bookingSelection.hidden = true;
}

function renderBookingMonth() {
  if (!nativeSlots || !bookingMonths.length) return;
  const monthKey = bookingMonths[activeBookingMonthIndex];
  const [year, month] = monthKey.split('-').map(Number);
  const monthTitle = nativeSlots.querySelector('[data-booking-month-title]');
  const calendarGrid = nativeSlots.querySelector('[data-booking-calendar-grid]');
  const previous = nativeSlots.querySelector('[data-booking-nav="-1"]');
  const next = nativeSlots.querySelector('[data-booking-nav="1"]');
  if (!monthTitle || !calendarGrid) return;

  monthTitle.textContent = bookingFormatter('month-title', {
    month: 'long', year: 'numeric',
  }, 'UTC').format(new Date(Date.UTC(year, month - 1, 1, 12)));
  if (previous) previous.disabled = activeBookingMonthIndex === 0;
  if (next) next.disabled = activeBookingMonthIndex === bookingMonths.length - 1;

  calendarGrid.replaceChildren();
  const fragment = document.createDocumentFragment();
  const leadingDays = new Date(Date.UTC(year, month - 1, 1)).getUTCDay();
  const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const todayKey = zonedDateKey(new Date());

  for (let index = 0; index < leadingDays; index += 1) {
    const spacer = document.createElement('span');
    spacer.className = 'booking-calendar__spacer';
    spacer.setAttribute('aria-hidden', 'true');
    fragment.appendChild(spacer);
  }

  for (let day = 1; day <= daysInMonth; day += 1) {
    const dateKey = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    const daySlots = bookingSlotsByDate.get(dateKey) || [];
    const control = document.createElement(daySlots.length ? 'button' : 'span');
    control.className = 'booking-calendar__day';
    control.textContent = String(day);
    if (dateKey === todayKey) control.classList.add('is-today');
    if (daySlots.length) {
      control.type = 'button';
      control.dataset.bookingDate = dateKey;
      control.classList.add('is-available');
      control.classList.toggle('is-selected', dateKey === selectedBookingDate);
      control.setAttribute('aria-pressed', String(dateKey === selectedBookingDate));
      control.setAttribute(
        'aria-label',
        `${bookingDateLabel(dateKey)}, ${daySlots.length} available ${daySlots.length === 1 ? 'time' : 'times'}`,
      );
    } else {
      control.classList.add('is-unavailable');
      control.setAttribute('aria-hidden', 'true');
    }
    fragment.appendChild(control);
  }
  calendarGrid.appendChild(fragment);
}

function renderBookingTimes() {
  if (!nativeSlots) return;
  const heading = nativeSlots.querySelector('[data-booking-selected-date]');
  const count = nativeSlots.querySelector('[data-booking-time-count]');
  const timeList = nativeSlots.querySelector('[data-booking-time-list]');
  if (!heading || !timeList) return;
  const daySlots = bookingSlotsByDate.get(selectedBookingDate) || [];
  if (count) count.textContent = `${daySlots.length} available ${daySlots.length === 1 ? 'time' : 'times'}`;
  heading.textContent = bookingDateLabel(selectedBookingDate, { short: true });
  timeList.setAttribute('aria-label', `Available times for ${bookingDateLabel(selectedBookingDate)}`);
  timeList.replaceChildren();
  const fragment = document.createDocumentFragment();

  daySlots.forEach((slot) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'native-booking__time';
    button.dataset.bookingStart = slot.start;
    button.classList.toggle('is-selected', slot.start === selectedBookingStart);
    button.setAttribute('aria-pressed', String(slot.start === selectedBookingStart));
    button.setAttribute('aria-label', formatBookingSlot(slot));

    const time = document.createElement('strong');
    time.textContent = bookingTimeLabel(slot.start);
    const duration = document.createElement('span');
    duration.textContent = '60 min';
    button.append(time, duration);
    fragment.appendChild(button);
  });
  timeList.appendChild(fragment);
}

function clearBookingSelection() {
  selectedBookingStart = '';
  if (bookingSelection) {
    bookingSelection.hidden = true;
    bookingSelection.classList.remove('is-retry');
  }
  if (confirmBookingBtn) {
    confirmBookingBtn.hidden = false;
    confirmBookingBtn.disabled = true;
    confirmBookingBtn.textContent = 'Confirm meeting';
    delete confirmBookingBtn.dataset.action;
  }
}

function selectBookingDate(dateKey, { focus = true } = {}) {
  if (!bookingSlotsByDate.has(dateKey)) return;
  selectedBookingDate = dateKey;
  const monthIndex = bookingMonths.indexOf(dateKey.slice(0, 7));
  if (monthIndex >= 0) activeBookingMonthIndex = monthIndex;
  clearBookingSelection();
  renderBookingMonth();
  renderBookingTimes();
  const status = document.getElementById('booking-status');
  if (status) status.textContent = `${bookingDateLabel(dateKey)} selected. Choose a meeting time.`;
  if (focus) nativeSlots?.querySelector('[data-booking-selected-date]')?.focus();
}

function selectBookingTime(start) {
  const slot = availableBookingSlots.find((item) => item.start === start);
  if (!slot) return;
  selectedBookingStart = slot.start;
  nativeSlots?.querySelectorAll('[data-booking-start]').forEach((button) => {
    const selected = button.dataset.bookingStart === selectedBookingStart;
    button.classList.toggle('is-selected', selected);
    button.setAttribute('aria-pressed', String(selected));
  });
  if (bookingSelectionText) bookingSelectionText.textContent = formatBookingSlot(slot);
  if (bookingSelection) bookingSelection.hidden = false;
  if (confirmBookingBtn) confirmBookingBtn.disabled = false;
  const status = document.getElementById('booking-status');
  if (status) status.textContent = `${formatBookingSlot(slot)} selected. Confirm to book it.`;
  if (bookingSelection && window.matchMedia('(max-width: 680px)').matches) {
    window.requestAnimationFrame(() => bookingSelection.scrollIntoView({ block: 'nearest' }));
  }
}

function changeBookingMonth(offset) {
  const nextIndex = Math.max(
    0,
    Math.min(activeBookingMonthIndex + offset, bookingMonths.length - 1),
  );
  if (nextIndex === activeBookingMonthIndex) return;
  activeBookingMonthIndex = nextIndex;
  const monthKey = bookingMonths[activeBookingMonthIndex];
  const firstAvailable = [...bookingSlotsByDate.keys()].find((dateKey) => dateKey.startsWith(monthKey));
  if (firstAvailable) selectBookingDate(firstAvailable, { focus: false });
}

function renderBookingPicker(slots, preferredDate = '') {
  availableBookingSlots = slots;
  bookingSlotsByDate = groupBookingSlots(slots);
  bookingMonths = [...new Set([...bookingSlotsByDate.keys()].map((dateKey) => dateKey.slice(0, 7)))];
  selectedBookingDate = bookingSlotsByDate.has(preferredDate)
    ? preferredDate
    : bookingSlotsByDate.keys().next().value;
  activeBookingMonthIndex = Math.max(0, bookingMonths.indexOf(selectedBookingDate.slice(0, 7)));
  clearBookingSelection();

  nativeSlots.innerHTML = `
    <div class="native-booking__picker">
      <section class="booking-calendar" aria-label="Choose a meeting date">
        <div class="booking-calendar__head">
          <button class="booking-calendar__nav" type="button" data-booking-nav="-1" aria-label="Previous month">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg>
          </button>
          <h3 data-booking-month-title></h3>
          <button class="booking-calendar__nav" type="button" data-booking-nav="1" aria-label="Next month">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg>
          </button>
        </div>
        <div class="booking-calendar__weekdays" aria-hidden="true">
          <span>Sun</span><span>Mon</span><span>Tue</span><span>Wed</span><span>Thu</span><span>Fri</span><span>Sat</span>
        </div>
        <div class="booking-calendar__grid" data-booking-calendar-grid></div>
      </section>
      <section class="booking-times" aria-label="Choose a meeting time">
        <p data-booking-time-count>Available times</p>
        <h3 data-booking-selected-date tabindex="-1"></h3>
        <div class="booking-times__list" data-booking-time-list></div>
      </section>
    </div>`;
  nativeSlots.setAttribute('aria-busy', 'false');
  renderBookingMonth();
  renderBookingTimes();
}

function bookingSheetStatus(data, { allowRetry = false } = {}) {
  if (!data.sheet_connected) {
    return 'Meeting confirmed. Your response is saved, but no Google Sheet is connected to this form.';
  }
  if (data.sheet_synced) {
    return 'Meeting confirmed and the Google Sheet was updated.';
  }
  return allowRetry
    ? 'Meeting confirmed. The Google Sheet update did not finish. Press “Retry Sheet update” below.'
    : 'Meeting confirmed. Your response is saved and the Google Sheet update is pending.';
}

async function loadNativeBookingSlots(statusMessage = '', { preferredDate = selectedBookingDate } = {}) {
  if (!nativeSlots || !responseId || !bookingToken || slotsLoading) return;
  slotsLoading = true;
  showBookingLoading();
  if (retryBookingSlotsBtn) retryBookingSlotsBtn.hidden = true;
  clearBookingSelection();
  const status = document.getElementById('booking-status');
  if (status) status.textContent = statusMessage || 'Checking Google Calendar for available times…';
  if (bookingLoadController) bookingLoadController.abort();
  bookingLoadController = new AbortController();
  const timeout = window.setTimeout(() => bookingLoadController.abort(), BOOKING_LOAD_TIMEOUT_MS);
  try {
    const timezone = browserTimezone();
    const res = await fetch(
      `/f/${window.FORM_REF}/responses/${responseId}/booking/slots?timezone=${encodeURIComponent(timezone)}`,
      {
        headers: { 'X-Booking-Token': bookingToken },
        signal: bookingLoadController.signal,
      },
    );
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Meeting times are unavailable.');
    viewerTimezone = data.viewer_timezone || timezone;
    bookingFormatters.clear();
    if (bookingTimezone) {
      const source = data.timezone_source === 'ip'
        ? 'your location'
        : data.timezone_source === 'browser' ? 'your device' : 'a UTC fallback';
      bookingTimezone.textContent = `Times shown in ${viewerTimezone}, based on ${source}. ${bookingScheduleLabel(data.schedule)}`;
    }
    if (!data.slots.length) {
      nativeSlots.innerHTML = '<p class="native-booking__empty">No times are currently available. Please check again later.</p>';
      nativeSlots.setAttribute('aria-busy', 'false');
      if (retryBookingSlotsBtn) {
        retryBookingSlotsBtn.hidden = false;
        retryBookingSlotsBtn.textContent = 'Check for times again';
      }
      if (status) {
        status.textContent = statusMessage || 'Your form response is saved even if you do not book now.';
      }
      return;
    }
    renderBookingPicker(data.slots, preferredDate);
    if (status) {
      status.textContent = statusMessage || 'Your form response is saved. Choose a time to book the meeting.';
    }
  } catch (err) {
    const error = document.createElement('p');
    error.className = 'native-booking__empty';
    error.textContent = err.name === 'AbortError'
      ? 'Availability is taking longer than expected. Please try again.'
      : err.message || 'Meeting times are temporarily unavailable.';
    nativeSlots.replaceChildren(error);
    nativeSlots.setAttribute('aria-busy', 'false');
    if (retryBookingSlotsBtn) {
      retryBookingSlotsBtn.hidden = false;
      retryBookingSlotsBtn.textContent = 'Retry loading times';
    }
    if (status) status.textContent = 'Your form response is saved. Meeting times could not load.';
  } finally {
    window.clearTimeout(timeout);
    bookingLoadController = null;
    slotsLoading = false;
  }
}

retryBookingSlotsBtn?.addEventListener('click', () => loadNativeBookingSlots());

nativeSlots?.addEventListener('click', (event) => {
  const control = event.target.closest('button');
  if (!control || !nativeSlots.contains(control)) return;
  if (control.dataset.bookingNav) {
    changeBookingMonth(Number(control.dataset.bookingNav));
  } else if (control.dataset.bookingDate) {
    selectBookingDate(control.dataset.bookingDate);
  } else if (control.dataset.bookingStart) {
    selectBookingTime(control.dataset.bookingStart);
  }
});

confirmBookingBtn?.addEventListener('click', async () => {
  if (!selectedBookingStart || !bookingToken) return;
  const status = document.getElementById('booking-status');
  const retryingSheet = confirmBookingBtn.dataset.action === 'retry-sheet';
  confirmBookingBtn.disabled = true;
  confirmBookingBtn.textContent = retryingSheet ? 'Retrying…' : 'Confirming…';
  if (status) {
    status.textContent = retryingSheet
      ? 'Retrying the Google Sheet update…'
      : 'Creating your Calendar event and Google Meet link…';
  }
  try {
    const res = await fetch(
      `/f/${window.FORM_REF}/responses/${responseId}/booking/confirm`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Booking-Token': bookingToken,
        },
        body: JSON.stringify({ start: selectedBookingStart, timezone: browserTimezone() }),
      },
    );
    const data = await res.json();
    if (!res.ok) {
      if (res.status === 409) {
        await loadNativeBookingSlots(
          data.detail || 'That time is no longer available. Choose another time.',
          { preferredDate: selectedBookingDate },
        );
        return;
      }
      throw new Error(data.detail || 'Could not confirm the meeting.');
    }
    viewerTimezone = data.viewer_timezone || viewerTimezone;
    selectedBookingStart = data.start;
    const confirmation = document.createElement('div');
    confirmation.className = 'booking-confirmation';
    const heading = document.createElement('h3');
    heading.tabIndex = -1;
    heading.textContent = 'Meeting confirmed';
    const when = document.createElement('p');
    when.textContent = formatBookingSlot({ start: data.start, end: data.end });
    const email = document.createElement('p');
    email.textContent = 'Google Calendar sent an invitation with the Meet link to your email.';
    confirmation.append(heading, when, email);
    if (data.meet_url) {
      const meet = document.createElement('a');
      meet.className = 'btn btn-primary';
      meet.href = data.meet_url;
      meet.target = '_blank';
      meet.rel = 'noopener';
      meet.textContent = 'Open Google Meet';
      confirmation.appendChild(meet);
    }
    nativeSlots.replaceChildren(confirmation);
    nativeSlots.setAttribute('aria-busy', 'false');
    if (bookingTimezone) bookingTimezone.textContent = `Confirmed in ${viewerTimezone}.`;
    const sheetNeedsRetry = Boolean(data.sheet_connected) && !data.sheet_synced;
    if (sheetNeedsRetry) {
      if (bookingSelection) {
        bookingSelection.hidden = false;
        bookingSelection.classList.add('is-retry');
      }
      if (bookingSelectionText) {
        bookingSelectionText.textContent = 'Your meeting is confirmed. Only the Sheet update needs another try.';
      }
      confirmBookingBtn.hidden = false;
      confirmBookingBtn.disabled = false;
      confirmBookingBtn.textContent = 'Retry Sheet update';
      confirmBookingBtn.dataset.action = 'retry-sheet';
    } else {
      if (bookingSelection) bookingSelection.hidden = true;
      delete confirmBookingBtn.dataset.action;
    }
    if (status) status.textContent = bookingSheetStatus(data, { allowRetry: true });
    if (againBtn) againBtn.hidden = false;
    heading.focus();
  } catch (err) {
    if (status) {
      status.textContent = retryingSheet
        ? 'Your meeting remains confirmed, but the Google Sheet update still needs to be retried.'
        : err.message || 'Could not confirm the meeting. Please retry.';
    }
    confirmBookingBtn.disabled = false;
  } finally {
    if (!confirmBookingBtn.hidden) {
      confirmBookingBtn.textContent = confirmBookingBtn.dataset.action === 'retry-sheet'
        ? 'Retry Sheet update'
        : 'Confirm meeting';
    }
  }
});

window.addEventListener('message', async (event) => {
  if (
    window.MEETING_PROVIDER !== 'calendly'
    ||
    event.origin !== 'https://calendly.com'
    || event.data?.event !== 'calendly.event_scheduled'
  ) return;

  const payload = event.data?.payload || {};
  const bookingFields = {
    status: 'Booked',
    event_uri: payload.event?.uri || '',
    invitee_uri: payload.invitee?.uri || '',
    completed_at: new Date().toISOString(),
  };
  document.querySelectorAll('[data-calendly-field]').forEach((field) => {
    const input = field.querySelector('input');
    if (input) input.value = bookingFields[field.dataset.calendlyField] || '';
  });
  if (againBtn) againBtn.hidden = false;
  const status = document.getElementById('booking-status');
  if (status) status.textContent = 'Meeting booked. Linking it to your submitted response…';
  if (!responseId) return;

  try {
    const res = await fetch(`/f/${window.FORM_REF}/responses/${responseId}/booking`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(bookingFields),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Could not link booking details.');
    if (status) {
      status.textContent = data.sheet_connected && !data.sheet_synced
        ? 'Meeting booked. Your details are saved and Google Sheet synchronization is pending.'
        : 'Meeting booked. The booking details were added to your submitted response.';
    }
  } catch (err) {
    if (status) status.textContent = 'Meeting booked. Your form response is safe, but the booking details could not be linked yet.';
  }
});

againBtn?.addEventListener('click', () => {
  window.location.reload();
});

// Star ratings fill up to the hovered/selected value.
document.querySelectorAll('.rating').forEach((group) => {
  const stars = Array.from(group.querySelectorAll('.star'));
  const paint = (upto) => stars.forEach((s, i) => s.classList.toggle('on', i <= upto));
  stars.forEach((star, index) => {
    star.addEventListener('mouseenter', () => paint(index));
    star.addEventListener('click', () => paint(index));
  });
  group.addEventListener('mouseleave', () => {
    const picked = stars.findIndex((s) => s.querySelector('input').checked);
    paint(picked);
  });
});

steps = buildSteps();
if (steps.length) {
  showStep(0);
} else {
  progress.parentElement.hidden = true;
  backBtn.hidden = true;
  nextBtn.hidden = true;
  if (hint) hint.hidden = true;
}


// A narrow field adapter: deliberately exposes no submit, booking or payment action.
window.FormcraftVoiceFields = (() => {
  const fieldFor = (id) => Array.from(form.querySelectorAll('.field[data-hidden="0"]')).find((el) => el.dataset.question === id);
  return Object.freeze({
    isSubmitted: () => responseSaved || responseSaving,
    read: (id) => { const field = fieldFor(id); return field ? readField(field) : ''; },
    hasValue: (id) => {
      const field = fieldFor(id);
      if (!field) return true;
      const value = readField(field);
      return Array.isArray(value) ? value.length > 0 : String(value).trim() !== '';
    },
    reveal: (id) => {
      const field = fieldFor(id);
      if (!field || responseSaved) return;
      const step = steps.findIndex((el) => el === field || el.contains(field));
      if (step >= 0) showStep(step);
      field.scrollIntoView({ behavior: 'smooth', block: 'center' });
    },
    review: () => { if (steps.length) showStep(steps.length - 1); },
    apply: (id, value) => {
      const field = fieldFor(id);
      if (!field || responseSaved || responseSaving) return false;
      const controls = Array.from(field.querySelectorAll('input, select, textarea'));
      if (!controls.length || controls.some((el) => el.disabled || el.readOnly)) return false;
      if (['radio', 'checkbox', 'scale', 'rating'].includes(field.dataset.type)) {
        const values = (Array.isArray(value) ? value : [value]).map(String);
        if (values.some((v) => !controls.some((el) => el.value === v))) return false;
        controls.forEach((el) => { el.checked = values.includes(el.value); });
      } else {
        const el = controls[0];
        if (el.tagName === 'SELECT' && !Array.from(el.options).some((o) => o.value === String(value))) return false;
        el.value = String(value);
        if (String(value) && !el.value) return false;
      }
      controls.forEach((el) => {
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
      });
      return true;
    },
  });
})();
