// 앱 컨트롤러. 화면 전환, GM 엔진 구동, 연출 타이밍, 저장.

import { PROFESSIONS } from '../content/professions.js';
import { STATS } from '../content/stats.js';
import { DIFFICULTIES } from '../content/difficulty.js';
import { getEpisode, FIRST_EPISODE } from '../content/episodes/index.js';
import { createState, formatClock, dangerLabel, MAX_DANGER } from '../engine/state.js';
import { createGM } from '../engine/gm.js';
import { advanceEpisode, hasNextEpisode, chapterNumber } from '../engine/campaign.js';
import { saveGame, loadGame, clearGame, loadSettings, saveSettings } from '../engine/save.js';
import { renderEvent, createSceneBlock } from './render.js';
import {
  statusPanel,
  inventoryPanel,
  codexPanel,
  partyPanel,
  PANEL_TITLES,
} from './panels.js';
import { mapPanel } from './map.js';
import { sfx, setAudioEnabled, audioEnabled } from './audio.js';

const $ = (id) => document.getElementById(id);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

const dom = {
  screens: {
    title: $('screen-title'),
    create: $('screen-create'),
    play: $('screen-play'),
  },
  log: $('log'),
  choices: $('choices'),
  diceBar: $('dice-bar'),
  btnRoll: $('btn-roll'),
  inputbar: $('inputbar'),
  freeInput: $('free-input'),
  sheet: $('sheet'),
  sheetScrim: $('sheet-scrim'),
  sheetTitle: $('sheet-title'),
  sheetBody: $('sheet-body'),
  diceOverlay: $('dice-overlay'),
  die: $('die'),
  dieFace: $('die-face'),
  diceLabel: $('dice-label'),
};

let state = null;
let gm = null;
let episode = getEpisode(FIRST_EPISODE);
let busy = false;
// 로그는 장면 단위 블록으로 쌓인다. 지난 장면은 접어 두어 화면을 짧게 유지한다.
let currentBlock = null;
let settings = loadSettings();
setAudioEnabled(settings.sound !== false);

// ── 화면 전환 ─────────────────────────────────────────────────

function show(name) {
  for (const [key, node] of Object.entries(dom.screens)) {
    node.dataset.active = String(key === name);
  }
}

// ── 캐릭터 생성 ───────────────────────────────────────────────

let picked = null;
let pickedDifficulty = 'standard';

function buildDifficulty() {
  const list = $('diff-list');
  list.innerHTML = '';
  for (const d of Object.values(DIFFICULTIES)) {
    const btn = document.createElement('button');
    btn.className = 'diff';
    btn.type = 'button';
    btn.dataset.id = d.id;
    btn.setAttribute('aria-pressed', String(d.id === pickedDifficulty));
    btn.innerHTML = `
      <span class="diff-name">${d.name}</span>
      <span class="diff-tagline">${d.tagline}</span>
      <span class="diff-desc">${d.desc}</span>`;
    btn.addEventListener('click', () => {
      pickedDifficulty = d.id;
      sfx.tap();
      for (const n of list.querySelectorAll('.diff')) {
        n.setAttribute('aria-pressed', String(n.dataset.id === d.id));
      }
    });
    list.appendChild(btn);
  }
}

function buildCreation() {
  const list = $('prof-list');
  list.innerHTML = '';
  for (const p of PROFESSIONS) {
    const btn = document.createElement('button');
    btn.className = 'prof';
    btn.type = 'button';
    btn.setAttribute('aria-pressed', 'false');
    btn.dataset.id = p.id;
    btn.innerHTML = `
      <span class="prof-top">
        <span class="prof-name">${p.name}</span>
        <span class="prof-tagline">${p.tagline}</span>
      </span>
      <p class="prof-desc">${p.desc}</p>
      <p class="prof-perk">특전 — ${p.perk}</p>`;
    btn.addEventListener('click', () => {
      picked = p;
      sfx.tap();
      for (const n of list.querySelectorAll('.prof')) {
        n.setAttribute('aria-pressed', String(n.dataset.id === p.id));
      }
      renderStatPreview(p);
      $('btn-begin').disabled = false;
    });
    list.appendChild(btn);
  }
}

function renderStatPreview(p) {
  const box = $('stat-preview');
  const rows = STATS.map((s) => {
    const v = p.stats[s.id];
    const dots = Array.from({ length: 5 }, (_, i) => `<i class="pip${i < v ? ' on' : ''}"></i>`).join('');
    return `<div class="stat-row"><span class="name">${s.id}</span><span class="pips">${dots}</span></div>`;
  }).join('');
  box.innerHTML = `
    <p class="field-label">능력치</p>
    <div class="stat-grid">${rows}</div>
    <p class="kit-line">시작 장비 — ${p.items.join(', ')}</p>`;
}

// ── HUD ───────────────────────────────────────────────────────

function meter(node, value, max, invert = false) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  node.querySelector('.bar i').style.width = `${pct}%`;
  node.querySelector('.meter-val').textContent = invert
    ? `${value}·${dangerLabel(value)}`
    : `${value}/${max}`;
  const low = invert ? value >= 7 : value <= Math.ceil(max * 0.3);
  node.classList.toggle('low', low);
}

function updateHud() {
  if (!state) return;
  const s = gm.scene();
  const clock = formatClock(state.tick);
  $('hud-loc').textContent = s.location;
  $('hud-date').textContent = clock.date;
  $('hud-time').textContent = clock.time;
  meter($('meter-hp'), state.hp, state.maxHp);
  meter($('meter-san'), state.san, state.maxSan);
  meter($('meter-danger'), state.danger, MAX_DANGER, true);
}

// ── 선택지 ────────────────────────────────────────────────────

function renderChoices() {
  dom.choices.innerHTML = '';
  if (busy) return;

  if (state.ended) {
    renderEndActions();
    return;
  }

  const list = gm.choices();
  list.forEach((c, i) => {
    const btn = document.createElement('button');
    btn.className = 'choice';
    btn.type = 'button';
    btn.disabled = c.locked;
    const statTag = c.isCheck && c.stat ? `<span class="stat-tag">${c.stat} 판정</span>` : '';
    const hint = c.hint ? `<span class="hint">${c.hint}</span>` : '';
    btn.innerHTML = `<span class="num">${i + 1}</span>${c.label}${statTag}${hint}`;
    btn.addEventListener('click', () => act(c.id));
    dom.choices.appendChild(btn);
  });

  if (!list.length && !gm.pending) {
    const p = document.createElement('p');
    p.className = 'empty';
    p.textContent = '무엇을 할지는 당신이 적는다.';
    dom.choices.appendChild(p);
  }
}

function renderEndActions() {
  const wrap = document.createElement('div');
  wrap.className = 'end-actions';

  // 장이 끝났을 뿐 탐사가 끝난 것이 아니라면, 다음 장으로 넘어갈 수 있다.
  if (state.ended?.type === 'chapter' && hasNextEpisode(state)) {
    const next = document.createElement('button');
    next.className = 'btn btn-primary';
    next.textContent = '다음 장으로';
    next.addEventListener('click', () => nextChapter());
    wrap.appendChild(next);
  }

  const again = document.createElement('button');
  again.className = 'btn btn-primary';
  again.textContent = '새 탐사 시작';
  again.addEventListener('click', () => {
    clearGame();
    show('create');
  });
  const codex = document.createElement('button');
  codex.className = 'btn';
  codex.textContent = '수첩을 다시 읽는다';
  codex.addEventListener('click', () => openPanel('codex'));
  wrap.appendChild(again);
  wrap.appendChild(codex);
  dom.choices.appendChild(wrap);
}

// ── 이벤트 재생 ───────────────────────────────────────────────

function scrollLog() {
  dom.log.scrollTo({ top: dom.log.scrollHeight, behavior: 'smooth' });
}

/** 새 장면이 시작되면 이전 장면을 접고 새 블록을 연다. */
function openSceneBlock(ev) {
  if (currentBlock) currentBlock.setCollapsed(true);
  const block = createSceneBlock(ev);
  dom.log.appendChild(block.section);
  currentBlock = block;
  return block;
}

/** 지금 기록이 들어갈 곳. 장면 블록이 없으면 로그에 바로 붙인다. */
function logTarget() {
  return currentBlock ? currentBlock.body : dom.log;
}

function resetLog() {
  dom.log.innerHTML = '';
  currentBlock = null;
}

const PACING = {
  scene: 260,
  narration: 340,
  player: 140,
  pressure: 320,
  checkRequest: 220,
  roll: 260,
  notes: 160,
  clue: 240,
  end: 300,
};

async function play(events) {
  busy = true;
  dom.choices.innerHTML = '';
  dom.diceBar.hidden = true;

  for (const ev of events) {
    if (ev.type === 'pressure') sfx.danger();
    if (ev.type === 'notes' && ev.notes.some((n) => n.kind === 'clue')) sfx.clue();

    if (ev.type === 'scene') {
      sfx.page();
      openSceneBlock(ev);
    } else if (ev.type === 'notes') {
      // 단서는 칩 대신 카드로 보여준다. 같은 말을 두 번 하지 않는다.
      const chips = ev.notes.filter((n) => n.kind !== 'clue');
      if (chips.length) renderEvent(logTarget(), { ...ev, notes: chips });
      for (const n of ev.notes) {
        if (n.kind === 'clue' && n.clue) {
          await wait(180);
          renderEvent(logTarget(), { type: 'clue', clue: n.clue });
          scrollLog();
        }
      }
    } else {
      renderEvent(logTarget(), ev);
    }

    updateHud();
    scrollLog();
    await wait(PACING[ev.type] ?? 200);
  }

  busy = false;
  dom.diceBar.hidden = !gm.pending;
  dom.inputbar.style.display = gm.pending || state.ended ? 'none' : '';
  renderChoices();
  scrollLog();
  saveGame(state);
}

// ── 행동 ──────────────────────────────────────────────────────

/** 다음 에피소드로. 탐사자는 초기화되지 않는다. */
async function nextChapter() {
  if (busy) return;
  const moved = advanceEpisode(state);
  if (!moved.ok) return;

  sfx.page();
  episode = moved.episode;
  gm = createGM({ state, episode });
  resetLog();

  const intro = [
    {
      type: 'narration',
      text: [`제 ${chapterNumber(state)} 장 — ${episode.title.replace(/^에피소드 \d+ — /, '')}`],
      tone: 'gm',
    },
  ];
  if (moved.notes?.length) intro.push({ type: 'notes', notes: moved.notes });

  await play(intro.concat(gm.start()));
}

async function act(choiceId) {
  if (busy || gm.pending) return;
  sfx.tap();
  await play(gm.act(choiceId));
}

async function freeAct(text) {
  if (busy || gm.pending) return;
  sfx.tap();
  await play(gm.freeAct(text));
}

/** 주사위 연출 — 굴림, 지연, 결과 공개 (기획서 7-3). */
async function rollDice() {
  if (busy || !gm.pending) return;
  busy = true;
  dom.diceBar.hidden = true;

  const label = gm.pending.label;
  dom.diceLabel.textContent = label;
  dom.die.className = 'die rolling';
  dom.die.removeAttribute('data-outcome');
  dom.diceOverlay.hidden = false;
  sfx.diceRoll();

  // 굴러가는 동안 숫자가 계속 바뀐다.
  const spin = setInterval(() => {
    dom.dieFace.textContent = String(1 + Math.floor(Math.random() * 20));
  }, 70);

  await wait(950);

  const events = gm.roll();
  const rollEv = events.find((e) => e.type === 'roll');
  clearInterval(spin);

  if (rollEv) {
    const r = rollEv.result;
    dom.dieFace.textContent = String(r.natural);
    dom.die.className = 'die landed';
    dom.die.dataset.outcome = r.outcome;
    dom.diceLabel.textContent = `${r.natural} ${r.modifier >= 0 ? '+' : '−'} ${Math.abs(
      r.modifier,
    )} = ${r.total} / 목표 ${r.target}`;
    sfx.diceLand();
    await wait(180);
    if (r.outcome === 'crit') sfx.crit();
    else if (r.outcome === 'fumble') sfx.fumble();
    else if (r.ok) sfx.success();
    else sfx.fail();
  }

  await wait(820);
  dom.diceOverlay.hidden = true;
  busy = false;
  await play(events);
}

// ── 시트 ──────────────────────────────────────────────────────

function openPanel(kind) {
  sfx.page();
  dom.sheetTitle.textContent = PANEL_TITLES[kind] || '';
  dom.sheetBody.innerHTML = '';

  let content;
  if (kind === 'status') content = statusPanel(state);
  else if (kind === 'inventory') content = inventoryPanel(state, useItem);
  else if (kind === 'codex') content = codexPanel(state);
  else if (kind === 'party') content = partyPanel(state);
  else if (kind === 'map') content = mapPanel(state, episode);
  else if (kind === 'menu') content = menuPanel();

  dom.sheetBody.appendChild(content);
  dom.sheet.hidden = false;
  dom.sheetScrim.hidden = false;
}

function closePanel() {
  dom.sheet.hidden = true;
  dom.sheetScrim.hidden = true;
}

function menuPanel() {
  const wrap = document.createElement('div');
  wrap.className = 'menu-list';

  const soundBtn = document.createElement('button');
  soundBtn.className = 'btn';
  const syncSound = () => {
    soundBtn.textContent = `소리 ${audioEnabled() ? '켜짐' : '꺼짐'}`;
  };
  syncSound();
  soundBtn.addEventListener('click', () => {
    const next = !audioEnabled();
    setAudioEnabled(next);
    settings = { ...settings, sound: next };
    saveSettings(settings);
    syncSound();
  });

  const saveBtn = document.createElement('button');
  saveBtn.className = 'btn';
  saveBtn.textContent = '지금 저장';
  saveBtn.addEventListener('click', () => {
    saveGame(state);
    saveBtn.textContent = '저장했습니다';
    setTimeout(() => (saveBtn.textContent = '지금 저장'), 1400);
  });

  const restart = document.createElement('button');
  restart.className = 'btn';
  restart.textContent = '탐사 포기하고 처음으로';
  restart.addEventListener('click', () => {
    if (restart.dataset.confirm !== '1') {
      restart.dataset.confirm = '1';
      restart.textContent = '정말 포기합니까? (한 번 더)';
      return;
    }
    clearGame();
    closePanel();
    show('title');
    refreshTitle();
  });

  const about = document.createElement('p');
  about.className = 'li-desc';
  about.style.marginTop = '14px';
  about.textContent =
    '판정: 1D20 + 보정 ≥ 목표값이면 성공. 자연 20은 대성공, 자연 1은 대실패. ' +
    '목표값에서 3 이내로 모자라면 부분 성공 — 대가를 치르고 얻는다. ' +
    '실패해도 이야기는 멈추지 않는다.';

  wrap.append(soundBtn, saveBtn, restart, about);
  return wrap;
}

async function useItem(name) {
  closePanel();
  await freeAct(`${name} 사용`);
}

// ── 게임 시작 / 복구 ──────────────────────────────────────────

function boot(newState) {
  state = newState;
  episode = getEpisode(FIRST_EPISODE);
  gm = createGM({ state, episode });
  resetLog();
  show('play');
  updateHud();
  return play(gm.start());
}

function resume() {
  const data = loadGame();
  if (!data) return false;
  state = data.state;
  episode = getEpisode(state.episode);
  gm = createGM({ state, episode });
  resetLog();
  show('play');

  // 이어하기는 현재 장면을 다시 서술하며 시작한다. 어디였는지 상기시켜야 한다.
  const scene = gm.scene();
  const intro = [
    { type: 'scene', ...gm.header() },
    {
      type: 'narration',
      text: ['(기록을 이어서 읽는다.)'],
      tone: 'gm',
    },
    {
      type: 'narration',
      text:
        typeof scene.revisitBody === 'function'
          ? scene.revisitBody(state)
          : scene.revisitBody || (typeof scene.body === 'function' ? scene.body(state) : scene.body),
    },
  ];
  updateHud();
  play(intro);
  return true;
}

function refreshTitle() {
  $('btn-continue').hidden = !loadGame();
}

// ── 이벤트 배선 ───────────────────────────────────────────────

$('btn-new').addEventListener('click', () => {
  sfx.page();
  show('create');
});

$('btn-continue').addEventListener('click', () => {
  sfx.page();
  resume();
});

$('btn-about').addEventListener('click', () => {
  dom.sheetTitle.textContent = '이 게임에 대하여';
  dom.sheetBody.innerHTML = `
    <p class="li-desc">1897년. 증기선과 전신은 있고, 위성과 인터넷은 없는 시대.
    당신은 세계 각지의 유적을 조사하는 탐사대의 일원이다.</p>
    <p class="li-desc" style="margin-top:12px">이 게임은 전투 연출이 아니라 <b>GM의 서술</b>로 굴러간다.
    선택지를 고르거나, 직접 행동을 적는다. 결과가 불확실하면 1D20을 굴린다.</p>
    <p class="li-desc" style="margin-top:12px">실패는 막다른 길이 아니다.
    소음이 나고, 다치고, 무언가를 잃는 대신 — 다른 문이 열린다.</p>
    <p class="li-desc" style="margin-top:12px">에피소드 1: 이집트의 검은 태양.</p>`;
  dom.sheet.hidden = false;
  dom.sheetScrim.hidden = false;
});

$('create-back').addEventListener('click', () => {
  show('title');
  refreshTitle();
});

$('btn-begin').addEventListener('click', () => {
  if (!picked) return;
  const name = $('input-name').value.trim();
  sfx.page();
  boot(
    createState({
      name,
      professionId: picked.id,
      difficulty: pickedDifficulty,
      seed: Date.now(),
    }),
  );
});

dom.btnRoll.addEventListener('click', rollDice);

dom.inputbar.addEventListener('submit', (e) => {
  e.preventDefault();
  const text = dom.freeInput.value.trim();
  if (!text) return;
  dom.freeInput.value = '';
  dom.freeInput.blur();
  freeAct(text);
});

for (const btn of document.querySelectorAll('.tabbar button')) {
  btn.addEventListener('click', () => openPanel(btn.dataset.panel));
}

$('btn-menu').addEventListener('click', () => openPanel('menu'));
$('sheet-close').addEventListener('click', closePanel);
dom.sheetScrim.addEventListener('click', closePanel);

// 물리 키보드가 있으면 숫자키로 선택지를 고를 수 있다.
window.addEventListener('keydown', (e) => {
  if (dom.screens.play.dataset.active !== 'true') return;
  if (document.activeElement === dom.freeInput) return;
  if (e.key === 'Escape') return closePanel();
  if (e.key === ' ' && gm?.pending) {
    e.preventDefault();
    return rollDice();
  }
  const n = Number(e.key);
  if (n >= 1 && n <= 9) {
    const btn = dom.choices.querySelectorAll('.choice')[n - 1];
    if (btn && !btn.disabled) btn.click();
  }
});

// 앱을 벗어날 때 저장.
window.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden' && state) saveGame(state);
});

buildDifficulty();
buildCreation();
refreshTitle();
