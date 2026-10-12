/* The hub page: talks to hub_api.HubApi through window.pywebview.api. */
const $ = (id) => document.getElementById(id);
const api = () => window.pywebview.api;
let loaded = null;        // the settings as last loaded or saved, to spot unsaved changes
let state = { running: null, status: '', brain: '' };
let voiceChoice = null;   // index into the voice list, once the list has arrived

/* ---- pages ---------------------------------------------------------------------------- */
document.querySelectorAll('.nav button').forEach((button) => {
  button.addEventListener('click', () => {
    document.querySelectorAll('.nav button').forEach((b) => b.classList.toggle('active', b === button));
    document.querySelectorAll('.page').forEach((p) => p.classList.toggle('active', p.id === 'page-' + button.dataset.page));
    if (button.dataset.page === 'memory') loadMemory();  // JARVIS may have learned something since
  });
});

/* ---- big headline: each letter rises in turn ------------------------------------------- */
function headline(el, text) {
  const chars = [...text].map((c, i) =>
    `<span class="ch" style="transition-delay:${i * 35}ms">${c === ' ' ? '&nbsp;' : escapeHtml(c)}</span>`).join('');
  el.innerHTML = `<span class="line-mask">${chars}</span>`;
  fitHeadline(el);
}

/* A long name ("Zephyrine the Great") shrinks to fit on one line instead of running off the page. */
function fitHeadline(el) {
  el.style.fontSize = '';
  const room = el.parentElement.clientWidth;
  const wide = el.firstElementChild ? el.firstElementChild.scrollWidth : 0;
  if (room && wide > room) {
    el.style.fontSize = `${parseFloat(getComputedStyle(el).fontSize) * room / wide * 0.98}px`;
  }
}
addEventListener('resize', () => fitHeadline($('home-name')));
function escapeHtml(s) { return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]); }

/* ---- status ----------------------------------------------------------------------------- */
const MOOD = { LISTENING: 'listening', RECOGNIZING: 'listening', THINKING: 'thinking', 'ASKING CLAUDE': 'thinking', SPEAKING: 'speaking' };
const WORD = { listening: 'Listening', thinking: 'Thinking', speaking: 'Speaking', idle: 'Waiting for you', off: 'Off' };
const THINKING_WORD = { fast: 'Fast', balanced: 'Balanced', deep: 'Deep' };

function showStatus(next) {
  const changedRunning = next.running !== state.running;
  state = next;
  const mood = !next.running ? 'off' : (MOOD[next.status] || 'idle');
  Orb.mood(mood);
  $('side-status').textContent = WORD[mood];
  $('home-kicker').textContent = next.running ? WORD[mood] : 'JARVIS is off';
  for (const dot of [$('side-dot'), $('home-dot')]) {
    dot.classList.toggle('on', next.running);
    dot.classList.toggle('live', mood === 'listening' || mood === 'speaking');
  }
  if (changedRunning) renderHome();
}

function renderHome() {
  const thinking = loaded ? THINKING_WORD[loaded.thinking] : '';
  $('home-sub').innerHTML = state.running
    ? `Thinking with <b>${escapeHtml(state.brain || 'Claude')}</b>${thinking ? ` · <b>${thinking}</b> mode` : ''}. Say "Hey ${escapeHtml(loaded ? loaded.assistant_name : 'Jarvis')}" to talk.`
    : 'Start it to talk. Your settings are saved either way.';
  const actions = $('home-actions');
  actions.innerHTML = '';
  const add = (label, cls, handler) => {
    const b = document.createElement('button');
    b.className = 'btn ' + cls; b.textContent = label;
    b.addEventListener('click', async () => { b.setAttribute('aria-busy', 'true'); await handler(); b.removeAttribute('aria-busy'); });
    actions.appendChild(b);
  };
  if (state.running) {
    add('Restart', 'ghost', async () => { toast('Restarting JARVIS…'); await api().restart(); });
    add('Quit', 'ghost danger', async () => { await api().stop(); toast('JARVIS is off'); });
  } else {
    add('Start JARVIS', '', async () => { await api().start(); toast('Starting JARVIS…'); });
  }
}

async function poll() {
  try { showStatus(await api().status()); } catch (e) { /* the window is closing */ }
  setTimeout(poll, 500);
}

/* ---- settings form ---------------------------------------------------------------------- */
const TEXT = ['user_name', 'assistant_name', 'hotkey', 'city', 'api_key'];
const SELECTS = ['language', 'model', 'microphone'];
const SWITCHES = ['wake_word', 'barge_in', 'face_lock', 'start_at_login', 'menu_bar'];
const SEGMENTS = ['brain', 'thinking'];

function options(select, pairs, current) {
  select.innerHTML = pairs.map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`).join('');
  if (current && !pairs.some(([v]) => v === current)) select.insertAdjacentHTML('beforeend', `<option value="${escapeHtml(current)}">${escapeHtml(current)}</option>`);
  select.value = current || '';
}

function setSegment(id, value) {
  $(id).querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.value === value));
  $(id).dataset.value = value;
}

function setSwitch(key, on) {
  const row = document.querySelector(`[data-switch="${key}"]`);
  row.dataset.on = on ? '1' : '';
  row.querySelector('.switch').classList.toggle('on', on);
  row.setAttribute('aria-checked', on);
}

function strictWord(v) {
  return v <= 60 ? 'Very strict' : v <= 75 ? 'Strict' : v <= 95 ? 'Normal' : 'Relaxed';
}

function fill(s) {
  for (const key of TEXT) $(key).value = s[key] || '';
  options($('language'), s.languages, s.language);
  options($('model'), s.models, s.model);
  setSegment('brain', s.brain);
  setSegment('thinking', s.thinking);
  for (const key of SWITCHES) setSwitch(key, s[key]);
  $('face_strictness').value = s.face_strictness;
  $('key-note').textContent = s.has_key ? 'A key is saved. Leave this empty to keep it.' : '';
  headline($('home-name'), s.assistant_name);
  $('brand-name').textContent = s.assistant_name;
  refreshDependents();
}

function refreshDependents() {
  $('key-row').classList.toggle('hidden', $('brain').dataset.value !== 'api');
  $('strict-row').classList.toggle('hidden', !document.querySelector('[data-switch="face_lock"]').dataset.on);
  const v = +$('face_strictness').value;
  $('strict-out').textContent = `${strictWord(v)} · ${v}`;
}

function collect() {
  const form = {};
  for (const key of [...TEXT, ...SELECTS]) form[key] = $(key).value;
  for (const key of SEGMENTS) form[key] = $(key).dataset.value;
  for (const key of SWITCHES) form[key] = !!document.querySelector(`[data-switch="${key}"]`).dataset.on;
  form.face_strictness = +$('face_strictness').value;
  form.voice_index = voiceChoice;
  return form;
}

let original = null;  // collect() right after loading
function changed() {
  const now = collect();
  const dirty = original && Object.keys(now).some((k) => k !== 'api_key' && now[k] !== original[k]) || !!now.api_key;
  $('savebar').classList.toggle('show', dirty);
  $('save').textContent = state.running ? 'Save and restart JARVIS' : 'Save';
  $('save-msg').className = 'msg';
  $('save-msg').textContent = 'You have unsaved changes';
}

document.addEventListener('input', (e) => { if (e.target.closest('.settings')) { refreshDependents(); changed(); } });
document.addEventListener('change', (e) => { if (e.target.closest('.settings')) changed(); });
for (const id of SEGMENTS) {
  $(id).addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    setSegment(id, b.dataset.value); refreshDependents(); changed();
  });
}
document.querySelectorAll('[data-switch]').forEach((row) => {
  row.setAttribute('role', 'switch'); row.tabIndex = 0;
  const flip = () => { setSwitch(row.dataset.switch, !row.dataset.on); refreshDependents(); changed(); };
  row.addEventListener('click', flip);
  row.addEventListener('keydown', (e) => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); flip(); } });
});

$('discard').addEventListener('click', async () => { await load(); $('savebar').classList.remove('show'); });
$('save').addEventListener('click', async () => {
  const button = $('save');
  button.setAttribute('aria-busy', 'true');
  const result = await api().save(collect());
  button.removeAttribute('aria-busy');
  if (!result.ok) {
    $('save-msg').className = 'msg error'; $('save-msg').textContent = result.error;
    return;
  }
  const restart = state.running;
  await load();
  $('savebar').classList.remove('show');
  toast(restart ? 'Saved. Restarting JARVIS…' : 'Saved');
  if (restart) api().restart();
});

/* ---- voices ------------------------------------------------------------------------------ */
const PLAY = '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M3 1.5v9l7.5-4.5z" fill="currentColor"/></svg>';
async function loadVoices() {
  const { voices, chosen } = await api().list_voices();
  voiceChoice = chosen;
  if (original) original.voice_index = chosen;
  $('voices').innerHTML = voices.map((v, i) => `
    <div class="voice${i === chosen ? ' selected' : ''}" data-index="${i}" role="radio" tabindex="0" aria-checked="${i === chosen}">
      <button class="play" data-play="${i}" aria-label="Play ${escapeHtml(v.name)}">${PLAY}<span class="bars"><b></b><b></b><b></b></span></button>
      <span class="name">${escapeHtml(v.name)}</span>
      <span class="source">${v.source === 'kokoro' ? 'Kokoro' : v.source === 'voicebox' ? 'Voicebox' : 'System'}</span>
    </div>`).join('');
}
$('voices').addEventListener('click', (e) => {
  const play = e.target.closest('[data-play]');
  const card = e.target.closest('.voice');
  if (!card) return;
  const index = +card.dataset.index;
  document.querySelectorAll('.voice').forEach((v) => { v.classList.toggle('selected', v === card); v.setAttribute('aria-checked', v === card); });
  voiceChoice = index;
  changed();
  if (play) {
    document.querySelectorAll('.voice.playing').forEach((v) => v.classList.remove('playing'));
    card.classList.add('playing');
    api().preview_voice(index, $('user_name').value, $('assistant_name').value);
  }
});
window.onPreviewDone = () => document.querySelectorAll('.voice.playing').forEach((v) => v.classList.remove('playing'));

/* ---- memory ------------------------------------------------------------------------------ */
const TRASH = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg>';

async function loadMemory() {
  const facts = await api().list_memory();
  $('fact-count').textContent = facts.length;
  $('facts-empty').classList.toggle('hidden', facts.length > 0);
  // Newest first: the fact just taught sits at the top.
  $('facts').innerHTML = facts.slice().reverse().map((f, i) => `
    <li class="fact" data-index="${f.index}" style="animation-delay:${Math.min(i, 12) * 35}ms">
      <span class="num">${String(f.index + 1).padStart(2, '0')}</span>
      <span class="text" contenteditable="plaintext-only" spellcheck="true" aria-label="Fact ${f.index + 1}">${escapeHtml(f.text)}</span>
      <button class="icon-btn danger" data-delete aria-label="Forget this">${TRASH}</button>
    </li>`).join('');
  $('facts').querySelectorAll('.fact').forEach((li, i) => { li.dataset.was = facts[facts.length - 1 - i].text; });
}

$('teach').addEventListener('submit', async (e) => {
  e.preventDefault();
  const result = await api().add_memory($('new-fact').value);
  $('teach-note').textContent = result.ok ? '' : result.error;
  if (!result.ok) return;
  $('new-fact').value = '';
  await loadMemory();
  toast('Remembered');
});

$('facts').addEventListener('keydown', (e) => {
  const text = e.target.closest('.text'); if (!text) return;
  if (e.key === 'Enter') { e.preventDefault(); text.blur(); }
  if (e.key === 'Escape') { text.textContent = text.closest('.fact').dataset.was; text.blur(); }
});
$('facts').addEventListener('focusout', async (e) => {
  const text = e.target.closest('.text'); if (!text) return;
  const li = text.closest('.fact');
  if (text.textContent.trim() === li.dataset.was) return;
  const result = await api().edit_memory(+li.dataset.index, text.textContent, li.dataset.was);
  toast(result.ok ? 'Updated' : result.error);
  await loadMemory();
});
$('facts').addEventListener('click', async (e) => {
  if (!e.target.closest('[data-delete]')) return;
  const li = e.target.closest('.fact');
  const index = +li.dataset.index, was = li.dataset.was;
  li.classList.add('leaving');
  const result = await api().delete_memory(index, was);
  await new Promise((r) => setTimeout(r, 250));
  await loadMemory();
  if (!result.ok) { toast(result.error); return; }
  toast('Forgot that', async () => { await api().add_memory(was, index); await loadMemory(); });
});

/* ---- toast ------------------------------------------------------------------------------- */
let toastTimer = null;
let toastUndo = null;
function toast(text, undo) {
  $('toast-text').textContent = text;
  toastUndo = undo || null;
  $('toast-undo').classList.toggle('hidden', !undo);
  $('toast').classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('toast').classList.remove('show'), undo ? 6000 : 2600);
}
$('toast-undo').addEventListener('click', async () => {
  const undo = toastUndo; toastUndo = null;
  $('toast').classList.remove('show');
  if (undo) await undo();
});

/* ---- start ------------------------------------------------------------------------------- */
async function load() {
  loaded = await api().load();
  fill(loaded);
  original = collect();
  renderHome();
}

window.addEventListener('pywebviewready', async () => {
  await load();
  poll();
  api().list_microphones().then((mics) => {
    options($('microphone'), [['', 'Default microphone'], ...mics.map((m) => [m, m])], loaded.microphone);
    if (original) original.microphone = $('microphone').value;
  });
  loadVoices();
});
