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
  const fields = window.FormcraftVoiceFields;
  if (!$('voice-widget') || !fields) return;
  let active = false;
  let consented = false;
  let session = '';
  let questions = [];
  let index = 0;
  let candidate;
  let originalValue;
  let phase = 'answer';
  let generation = 0;
  let stream;
  let recorder;
  let audioContext;
  let silenceTimer;
  let maxTimer;
  let controller;
  let busy = false;
  const status = (message) => { $('voice-status').textContent = message; };
  const visible = (id, show) => { $(id).hidden = !show; };
  function cleanupMic() {
    clearInterval(silenceTimer);
    clearTimeout(maxTimer);
    if (recorder?.state === 'recording') recorder.stop();
    stream?.getTracks().forEach((track) => track.stop());
    stream = null;
    if (audioContext) audioContext.close().catch(() => {});
    audioContext = null;
    $('voice-toggle').dataset.listening = 'false';
    $('voice-record').textContent = 'Record answer';
  }
  function cancelTurn() {
    generation++;
    controller?.abort();
    controller = null;
    cleanupMic();
    window.speechSynthesis?.cancel();
    busy = false;
  }
  function stop(message = 'Voice is off. You can continue filling the form yourself.') {
    active = false;
    cancelTurn();
    ['voice-record', 'voice-accept', 'voice-retry', 'voice-next', 'voice-stop', 'voice-candidate', 'voice-transcript'].forEach((id) => visible(id, false));
    visible('voice-start', !fields.isSubmitted());
    $('voice-start').textContent = 'Resume voice help';
    status(message);
  }
  function openPanel(open) {
    $('voice-panel').hidden = !open;
    $('voice-toggle').setAttribute('aria-expanded', String(open));
    visible('voice-invite', false);
    if (!open) { consented = false; stop(); }
  }
  function speak(message, listen = true) {
    const stamp = generation;
    status(message);
    if (!window.speechSynthesis || !window.SpeechSynthesisUtterance) {
      status(message + ' Tap Record answer when ready.');
      return;
    }
    const utterance = new SpeechSynthesisUtterance(message);
    utterance.lang = document.documentElement.lang || navigator.language;
    utterance.onend = () => {
      if (listen && active && generation === stamp) record();
    };
    utterance.onerror = () => {
      if (active && generation === stamp) status(message + ' Tap Record answer when ready.');
    };
    window.speechSynthesis.speak(utterance);
  }
  function ask() {
    cancelTurn();
    phase = 'answer';
    candidate = undefined;
    ['voice-accept', 'voice-retry', 'voice-candidate', 'voice-transcript'].forEach((id) => visible(id, false));
    while (index < questions.length && fields.hasValue(questions[index].id)) index++;
    if (index >= questions.length) {
      fields.review();
      stop('Your answers are ready to review. Check the form and press Submit yourself.');
      speak('Your answers are ready to review. Check the form and press Submit yourself.', false);
      return;
    }
    const q = questions[index];
    fields.reveal(q.id);
    originalValue = JSON.stringify(fields.read(q.id));
    visible('voice-record', true);
    visible('voice-next', true);
    visible('voice-stop', true);
    let message = `Question ${index + 1} of ${questions.length}. ${q.label}`;
    if (q.help_text) message += `. ${q.help_text}`;
    if (q.options.length) message += `. Options: ${q.options.join(', ')}`;
    if (q.type === 'scale' || q.type === 'rating') message += `. Choose a number from ${q.config.min ?? 1} to ${q.config.max ?? 5}.`;
    if (!q.required) message += '. You can say skip.';
    speak(message);
  }
  function accept() {
    if (!active || phase !== 'confirm' || candidate === undefined) return;
    cancelTurn();
    const q = questions[index];
    if (JSON.stringify(fields.read(q.id)) !== originalValue) {
      stop('This field changed while voice was running. Your manual edit was kept. Resume when ready.');
      return;
    }
    if (!fields.apply(q.id, candidate)) {
      stop('Please fill this field manually. Your answer could not be applied.');
      return;
    }
    index++;
    ask();
  }
  async function record() {
    if (!active || busy || fields.isSubmitted()) return;
    if (recorder?.state === 'recording') { recorder.stop(); return; }
    const stamp = generation;
    window.speechSynthesis?.cancel();
    busy = true;
    try {
      const acquired = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!active || generation !== stamp) { acquired.getTracks().forEach((track) => track.stop()); return; }
      stream = acquired;
      const mime = ['audio/webm', 'audio/mp4'].find((type) => MediaRecorder.isTypeSupported(type));
      if (!mime) throw new Error('This browser cannot record a supported audio format. Please type your answers.');
      const recording = new MediaRecorder(stream, { mimeType: mime, audioBitsPerSecond: 64000 });
      recorder = recording;
      const chunks = [];
      recording.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      recording.onstop = () => {
        acquired.getTracks().forEach((track) => track.stop());
        if (generation !== stamp || recorder !== recording) return;
        cleanupMic();
        if (active) send(new Blob(chunks, { type: mime }), stamp);
      };
      recording.onerror = () => stop('Recording failed. Check microphone access, or type instead.');
      recording.start();
      busy = false;
      $('voice-toggle').dataset.listening = 'true';
      $('voice-record').textContent = 'Finish recording';
      status(phase === 'confirm' ? 'Listening for yes, try again, or stop…' : 'Listening… Speak your answer. Say stop to finish voice help.');
      maxTimer = setTimeout(() => { if (recording.state === 'recording') recording.stop(); }, 30000);
      const Context = window.AudioContext || window.webkitAudioContext;
      if (Context) {
        audioContext = new Context();
        await audioContext.resume();
        if (!active || generation !== stamp || recording.state !== 'recording' || !audioContext) return;
        const analyser = audioContext.createAnalyser();
        analyser.fftSize = 1024;
        audioContext.createMediaStreamSource(stream).connect(analyser);
        const samples = new Float32Array(analyser.fftSize);
        let heard = false;
        let lastSound = Date.now();
        const started = Date.now();
        silenceTimer = setInterval(() => {
          analyser.getFloatTimeDomainData(samples);
          const level = Math.sqrt(samples.reduce((total, n) => total + n * n, 0) / samples.length);
          if (level > 0.015) { heard = true; lastSound = Date.now(); }
          if ((heard && Date.now() - lastSound > 1500) || (!heard && Date.now() - started > 8000)) {
            if (recording.state === 'recording') recording.stop();
          }
        }, 100);
      }
    } catch (err) {
      if (generation === stamp) stop(err.name === 'NotAllowedError' ? 'Microphone access was not granted. You can fill the form manually.' : err.message);
    }
  }
  async function send(blob, stamp) {
    busy = true;
    visible('voice-record', false);
    status('Understanding your answer…');
    const q = questions[index];
    const sentPhase = phase;
    const payload = new FormData();
    payload.set('audio', blob, blob.type === 'audio/mp4' ? 'answer.mp4' : 'answer.webm');
    payload.set('question', q.id);
    payload.set('mode', sentPhase);
    controller = new AbortController();
    const timeout = setTimeout(() => controller?.abort(), 90000);
    try {
      if (blob.size > 1024 * 1024) throw new Error('Recording too large. Try a shorter answer.');
      const response = await fetch(`/f/${encodeURIComponent(window.FORM_REF)}/ai/turn`, {
        method: 'POST', headers: { 'X-Voice-Session': session }, body: payload, signal: controller.signal,
      });
      const result = await response.json();
      if (!active || generation !== stamp) return;
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Voice request failed. Please try again or type.');
      busy = false;
      $('voice-transcript').textContent = `Heard: ${result.transcript}`;
      visible('voice-transcript', true);
      if (result.action === 'stop') { consented = false; stop(); return; }
      if (result.action === 'skip') { index++; ask(); return; }
      if (sentPhase === 'confirm' && result.action === 'accept') { accept(); return; }
      if (result.action === 'retry') { ask(); return; }
      if (sentPhase === 'answer' && result.action === 'answer' && Object.hasOwn(result, 'value')) {
        candidate = result.value;
        phase = 'confirm';
        const answer = Array.isArray(candidate) ? candidate.join(', ') : String(candidate);
        $('voice-candidate').textContent = answer || '(Empty answer)';
        ['voice-candidate', 'voice-accept', 'voice-retry', 'voice-record'].forEach((id) => visible(id, true));
        speak(`I heard: ${answer || 'an empty answer'}. Say yes to use this answer, or say try again.`);
      } else {
        visible('voice-record', true);
        // Do not loop paid requests automatically after silence or unclear speech.
        status((result.clarification || 'Please try again.') + ' Tap Record answer, or fill this field manually.');
      }
    } catch (err) {
      if (generation === stamp && active) {
        busy = false;
        visible('voice-record', true);
        status(err.name === 'AbortError' ? 'Voice request timed out. Try again or fill manually.' : err.message);
      }
    } finally { clearTimeout(timeout); }
  }
  $('voice-start').addEventListener('click', async () => {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder || !window.isSecureContext) {
      status('Voice needs microphone support and HTTPS. You can still fill this form manually.'); return;
    }
    cancelTurn();
    const stamp = generation;
    consented = true;
    $('voice-start').disabled = true;
    status('Starting voice assistance…');
    controller = new AbortController();
    try {
      const response = await fetch(`/f/${encodeURIComponent(window.FORM_REF)}/ai/session`, { method: 'POST', signal: controller.signal });
      const data = await response.json();
      if (generation !== stamp) return;
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Voice is unavailable.');
      session = data.token;
      questions = data.questions;
      active = true;
      index = 0;
      visible('voice-start', false);
      visible('voice-privacy', false);
      ask();
    } catch (err) { if (generation === stamp) status(err.message); }
    finally { $('voice-start').disabled = false; }
  });
  $('voice-toggle').addEventListener('click', () => openPanel($('voice-panel').hidden));
  $('voice-close').addEventListener('click', () => { openPanel(false); $('voice-toggle').focus(); });
  $('voice-stop').addEventListener('click', () => { consented = false; stop(); });
  $('voice-record').addEventListener('click', record);
  $('voice-accept').addEventListener('click', accept);
  $('voice-retry').addEventListener('click', ask);
  $('voice-next').addEventListener('click', () => { index++; ask(); });
  $('voice-panel').addEventListener('keydown', (event) => {
    if (event.key === 'Escape') { openPanel(false); $('voice-toggle').focus(); }
  });
  document.addEventListener('visibilitychange', () => { if (document.hidden) { consented = false; stop(); } });
  window.addEventListener('pagehide', () => stop());
  document.getElementById('form').addEventListener('submit', () => stop('Reviewing your submission…'));
  window.addEventListener('formcraft:handoff', (event) => {
    const message = event.detail.stage === 'payment'
      ? 'Please complete payment yourself using the payment controls. I cannot pay or confirm payment.'
      : event.detail.stage === 'booking'
        ? 'Your answers are saved. Please pick a meeting time and confirm it yourself using the scheduler.'
        : 'Your response is saved. Thank you.';
    stop(message);
    if (consented) { openPanel(true); speak(message, false); }
  });
})();
