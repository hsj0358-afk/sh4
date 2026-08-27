// 앱 컨트롤러. 화면 전환, GM 엔진 구동, 연출 타이밍, 저장.

import { PROFESSIONS } from '../content/professions.js';
import { STATS } from '../content/stats.js';
import { DIFFICULTIES } from '../content/difficulty.js';
import { getEpisode, FIRST_EPISODE } from '../content/episodes/index.js';
import { createState, formatClock, dangerLabel, MAX_DANGER } from '../engine/state.js';
import { createGM } from '../engine/gm.js';
import { recap } from '../engine/recap.js';
import {
  advanceEpisode,
  hasNextEpisode,
  chapterNumber,
  interludeFor,
} from '../engine/campaign.js';
import {
  saveGame, loadGame, clearGame, loadSettings, saveSettings,
  slotList, firstEmptySlot, hasAnySave, migrateLegacy, SLOTS,
} from '../engine/save.js';
import { loadArchive, saveArchive, countRun, record } from '../engine/archive.js';
import { renderEvent, createSceneBlock } from './render.js';
import {
  statusPanel,
  inventoryPanel,
  codexPanel,
  partyPanel,
  archivePanel,
  PANEL_TITLES,
} from './panels.js';
import { mapPanel } from './map.js';
import { paint, kindFor } from './backdrop.js';
import { setMood, moodFor, setMusicEnabled, musicEnabled, stopMusic, duck } from './music.js';
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
  controls: $('controls'),
  choices: $('choices'),
  diceBar: $('dice-bar'),
  combatBar: $('combat-bar'),
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
// 배경음은 기본으로 켠다. 소리 자체를 끄면 음악도 함께 꺼진다.
setMusicEnabled(settings.sound !== false && settings.music !== false);
// 회차를 가로지르는 기록. 한 판이 끝나도 도감에는 남는다.
let archive = loadArchive();
// 같은 판의 끝을 두 번 세지 않는다.
let recordedRun = null;
// 지금 굴리고 있는 판이 앉은 슬롯. 자동 저장이 여기로 간다.
let slot = 0;
migrateLegacy();

// ── 화면 전환 ─────────────────────────────────────────────────

function show(name) {
  for (const [key, node] of Object.entries(dom.screens)) {
    node.dataset.active = String(key === name);
  }
}

// ── 캐릭터 생성 ───────────────────────────────────────────────

let picked = null;
let pickedDifficulty = 'standard';

// 이름 칸을 비워 두면 「이름 없는 탐사자」가 되고, 그 이름으로 나디아가
// 당신을 부르게 된다. 그래서 칸을 비워 두지 않는다 — 열 때마다 하나 채워 놓고,
// 마음에 안 들면 ⟳ 로 다시 뽑거나 그냥 지우고 쓰면 된다.
// 1897년에 이런 배를 탈 만한 사람들의 이름이다.
const NAME_SEEDS = [
  '에드워드 몰리', '헨리 콜브룩', '엘리자 반스', '오거스터스 리드',
  '마거릿 헤이스', '시어도어 팬쇼', '클라라 윈덤', '앰브로즈 켈러',
  '이사도라 렌', '루퍼트 애슈비', '베아트리스 놀런', '조사이아 그레이브스',
  '콘스턴스 페어리', '알로이시우스 하트', '실비아 머독', '너새니얼 퀸',
];

function suggestName() {
  const cur = $('input-name').value.trim();
  const pool = NAME_SEEDS.filter((n) => n !== cur);
  $('input-name').value = pool[Math.floor(Math.random() * pool.length)];
}

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
      <p class="prof-perk">특전 — ${p.perk}</p>
      <div class="prof-stats"></div>`;
    btn.addEventListener('click', () => {
      picked = p;
      sfx.tap();
      for (const n of list.querySelectorAll('.prof')) {
        const on = n.dataset.id === p.id;
        n.setAttribute('aria-pressed', String(on));
        if (!on) n.querySelector('.prof-stats').innerHTML = '';
      }
      renderStatPreview(p, btn);
      $('btn-begin').disabled = false;
    });
    list.appendChild(btn);
  }
}

/**
 * 능력치는 고른 직업 카드 안에서 펼쳐진다.
 *
 * 예전에는 목록 맨 아래 고정된 칸에 그렸다. 여덟 직업이 세로로 늘어선 화면에서
 * 위쪽 직업을 고르면 능력치는 화면 밖에 있었고, 무엇을 고르는지 보려면
 * 매번 끝까지 스크롤해야 했다. 고른 것 바로 아래에 있어야 비교가 된다.
 */
function renderStatPreview(p, btn) {
  const rows = STATS.map((s) => {
    const v = p.stats[s.id];
    const dots = Array.from({ length: 5 }, (_, i) => `<i class="pip${i < v ? ' on' : ''}"></i>`).join('');
    return `<div class="stat-row"><span class="name">${s.id}</span><span class="pips">${dots}</span></div>`;
  }).join('');
  btn.querySelector('.prof-stats').innerHTML = `
    <div class="stat-grid">${rows}</div>
    <p class="kit-line">시작 장비 — ${p.items.join(', ')}</p>`;

  // 카드가 길어지면서 아래쪽이 잘릴 수 있다. 펼쳐진 부분까지 보이게 한다.
  requestAnimationFrame(() => btn.scrollIntoView({ block: 'nearest', behavior: 'smooth' }));
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

/** 전투 상태 바. 전투 중에만 뜬다. */
function updateCombatBar() {
  const c = gm?.combat;
  if (!c) {
    dom.combatBar.hidden = true;
    return;
  }
  dom.combatBar.hidden = false;
  $('cb-name').textContent = c.name;
  $('cb-round').textContent = `${c.round}라운드`;

  const resolve = $('cb-resolve');
  resolve.querySelector('.bar i').style.width = `${(c.resolve / c.maxResolve) * 100}%`;
  resolve.querySelector('.cb-val').textContent = `${c.resolve}/${c.maxResolve}`;

  const pressure = $('cb-pressure');
  pressure.querySelector('.bar i').style.width = `${(c.pressure / c.maxPressure) * 100}%`;
  pressure.querySelector('.cb-val').textContent = `${c.pressure}/${c.maxPressure}`;
  pressure.classList.toggle('critical', c.pressure >= c.maxPressure - 3);

  const escape = $('cb-escape');
  escape.hidden = c.escape <= 0;
  const left = Math.max(1, c.escapeNeeded - c.escape);
  escape.textContent =
    `도주 ${c.escape}/${c.escapeNeeded} — ` +
    (left === 1 ? '한 번 더 성공하면 벗어난다' : `${left}번 더 성공하면 벗어난다`);
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
  updateCombatBar();
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
    next.addEventListener('click', () => beginInterlude());
    wrap.appendChild(next);
    dom.choices.appendChild(wrap);
    return;
  }

  const again = document.createElement('button');
  again.className = 'btn btn-primary';
  again.textContent = '새 탐사 시작';
  again.addEventListener('click', () => {
    // 끝난 판이 앉아 있던 칸은 비워 준다. 다음 판이 들어올 자리다.
    clearGame(slot);
    $('input-name').value = '';
    suggestName();
    show('create');
  });
  const codex = document.createElement('button');
  codex.className = 'btn';
  codex.textContent = '수첩을 다시 읽는다';
  codex.addEventListener('click', () => openPanel('codex'));
  const arc = document.createElement('button');
  arc.className = 'btn';
  arc.textContent = '도감을 연다';
  arc.addEventListener('click', () => openPanel('archive'));
  wrap.append(again, codex, arc);
  dom.choices.appendChild(wrap);
}

/**
 * 막간 — 다음 장으로 가는 항로를 고른다 (기획서 18절 '분기형 캠페인').
 * 고를 것이 하나뿐이면 막간을 건너뛴다. 선택지가 없는 선택은 선택이 아니다.
 */
async function beginInterlude() {
  if (busy) return;
  const inter = interludeFor(state);
  if (!inter) return nextChapter();

  sfx.page();
  await play([
    { type: 'narration', tone: 'gm', text: [inter.title] },
    { type: 'narration', text: inter.intro },
  ]);

  dom.choices.innerHTML = '';
  dom.inputbar.style.display = 'none';
  inter.routes.forEach((r, i) => {
    const btn = document.createElement('button');
    btn.className = 'choice';
    btn.type = 'button';
    btn.innerHTML =
      `<span class="num">${i + 1}</span>${r.label}` +
      `<span class="hint">${r.detail}</span>`;
    btn.addEventListener('click', () => nextChapter(r.id));
    dom.choices.appendChild(btn);
  });
  attachControls();
  scrollLog();
}

// ── 스크롤 ────────────────────────────────────────────────────
//
// 이 게임에서 읽는 것이 곧 플레이다. 그래서 스크롤의 규칙은 하나다:
// **이번에 새로 생긴 것의 첫 줄이 화면 맨 위에 온다.**
//
// 예전에는 무엇이 붙든 맨 아래로 내렸다. 장면이 바뀌어도 마찬가지여서,
// 새 장면의 지문은 늘 이미 한참 읽다 만 위치에서 나타났다. 처음부터
// 읽으려면 매번 손으로 올려야 했다.

/** 로그 안에서 이 요소의 위치. */
function offsetInLog(node) {
  return node.getBoundingClientRect().top - dom.log.getBoundingClientRect().top + dom.log.scrollTop;
}

/** 이 요소의 첫 줄을 화면 맨 위로 올린다. */
function scrollToTopOf(node, behavior = 'smooth') {
  if (!node) return;
  const top = Math.max(0, offsetInLog(node) - 6);
  dom.log.scrollTo({ top, behavior });
}

function scrollLog() {
  dom.log.scrollTo({ top: dom.log.scrollHeight, behavior: 'smooth' });
}

/** 아래에 더 읽을 것이 있으면 하단에 결을 하나 남긴다. */
function markOverflow() {
  const more = dom.log.scrollTop + dom.log.clientHeight < dom.log.scrollHeight - 4;
  dom.log.classList.toggle('more-below', more);
}

/**
 * 이번 턴에 붙은 것을 기준으로 화면을 맞춘다.
 *
 * 새로 생긴 것이 화면보다 짧으면 전부 보이고, 길면 위에서부터 보인다.
 * 아래로 밀어내지 않는 것이 핵심이다 — 밀어내면 첫 줄을 놓친다.
 */
function anchor(node) {
  if (!node) return scrollLog();
  const top = offsetInLog(node);
  const grown = dom.log.scrollHeight - dom.log.clientHeight;
  dom.log.scrollTo({ top: Math.min(Math.max(0, top - 6), Math.max(0, grown)), behavior: 'smooth' });
}

// ── 장면 그림 ─────────────────────────────────────────────────

/**
 * 장면 머리말 아래의 그림 띠를 그린다.
 *
 * 캔버스 크기는 레이아웃이 잡힌 뒤라야 알 수 있으므로 한 프레임 기다린다.
 * 그리지 못하면(캔버스가 아직 0×0) 띠는 투명한 채로 남는다 — 빈 칸이 보일 뿐
 * 아무것도 깨지지 않는다.
 */
function paintSceneArt(block, scene) {
  // 그림과 소리는 같은 것에서 나온다 — 장면의 종류.
  if (!gm.combat) setMood(moodFor(kindFor(scene)));
  const canvas = block.art.querySelector('canvas');
  requestAnimationFrame(() => {
    if (paint(canvas, kindFor(scene), scene.location || scene.id)) {
      block.art.classList.add('on');
    }
  });
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
  // 선택지와 주사위는 로그 안에 얹혀 산다. 로그를 비우기 전에 꺼내 두지 않으면
  // 같이 지워지고, 그 뒤로는 아무 버튼도 나타나지 않는다.
  dom.controls.append(dom.diceBar, dom.choices);
  dom.log.innerHTML = '';
  currentBlock = null;
}

const PACING = {
  scene: 260,
  narration: 340,
  player: 140,
  pressure: 320,
  betrayal: 420,
  relation: 260,
  recap: 700,
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

  // 이번 턴에 처음 붙은 것. 재생이 끝나면 이것의 첫 줄로 화면을 맞춘다.
  //
  // 보통은 장면이 바뀌면 기준을 그 장면으로 옮긴다 — 새 지문을 처음부터 읽어야 하니까.
  // 다만 줄거리 요약은 예외다. 이어하기의 첫 화면은 요약이어야 하고, 그 뒤에 오는
  // 장면 서술이 요약을 위로 밀어내면 정작 읽히지 않는다.
  let head = null;
  let pinned = false;
  const mark = (node) => {
    if (node && !head) head = node;
    return node;
  };

  for (const ev of events) {
    if (ev.type === 'pressure') sfx.danger();
    if (ev.type === 'combatStart') {
      sfx.danger();
      setMood('combat');
    }
    if (ev.type === 'combatEnd') setMood(moodFor(kindFor(gm.scene())));
    if (ev.type === 'betrayal') sfx.danger();
    if (ev.type === 'notes' && ev.notes.some((n) => n.kind === 'clue')) sfx.clue();

    if (ev.type === 'scene') {
      sfx.page();
      // 장면이 바뀌면 그 장면의 머리말이 기준이 된다. 앞의 것은 잊는다.
      const block = openSceneBlock(ev);
      if (!pinned) head = block.section;
      paintSceneArt(block, gm.scene());
    } else if (ev.type === 'notes') {
      // 단서는 칩 대신 카드로 보여준다. 같은 말을 두 번 하지 않는다.
      const chips = ev.notes.filter((n) => n.kind !== 'clue');
      if (chips.length) mark(renderEvent(logTarget(), { ...ev, notes: chips }));
      for (const n of ev.notes) {
        if (n.kind === 'clue' && n.clue) {
          await wait(180);
          mark(renderEvent(logTarget(), { type: 'clue', clue: n.clue }));
          anchor(head);
        }
      }
    } else {
      const node = mark(renderEvent(logTarget(), ev));
      if (ev.type === 'recap' && node) {
        head = node;
        pinned = true;
      }
    }

    updateHud();
    anchor(head);
    await wait(PACING[ev.type] ?? 200);
  }

  busy = false;
  dom.diceBar.hidden = !gm.pending;
  dom.inputbar.style.display = gm.pending || state.ended ? 'none' : '';
  dom.freeInput.placeholder = gm.combat
    ? '소지품을 쓴다면 이름을 적는다…'
    : '직접 행동을 적는다…';
  renderChoices();

  // 선택지와 주사위는 서술 뒤에 이어 붙는다. 화면 아래 고정된 판이 아니라
  // 읽던 문장 다음 줄에 온다 — 그래야 읽고 나서 고르는 순서가 된다.
  attachControls();
  anchor(head);
  setTimeout(markOverflow, 420); // 부드러운 스크롤이 멈춘 뒤에 잰다
  saveGame(state, slot);
  syncArchive();
}

/**
 * 선택지·주사위 버튼을 지금 장면의 기록 끝에 붙인다.
 *
 * 예전에는 화면 하단에 고정된 칸이었다. 선택지 넷이면 그 칸이 화면의 절반 가까이를
 * 차지했고, 정작 읽어야 할 서술은 남은 3분의 1에서 스크롤됐다. 이 게임에서 읽는 것이
 * 곧 플레이인데 읽을 자리가 가장 좁았다.
 *
 * DOM 을 옮기기만 한다 — 같은 노드라서 숫자키 단축키도 그대로 동작한다.
 */
function attachControls() {
  const target = logTarget();
  if (!dom.diceBar.hidden) target.appendChild(dom.diceBar);
  target.appendChild(dom.choices);
}

// ── 도감 갱신 ─────────────────────────────────────────────────
//
// 본 것은 판이 끝나기 전에, 한 턴마다 쌓아 둔다. 죽어서 끝난 회차도 본 것은 본 것이고,
// 브라우저를 그냥 닫은 회차도 마찬가지다.
//
// 그래서 '이번에 처음 본 것'은 판이 끝나는 순간에는 이미 전부 아카이브에 들어가 있다.
// 마지막에 물어보면 늘 빈손이 나온다. 매 턴 나온 것을 여기 모아 두었다가 끝에 한 번 읽는다.
const runFirsts = { clues: [], items: [], companions: [], ending: null };

function resetFirsts() {
  runFirsts.clues = [];
  runFirsts.items = [];
  runFirsts.companions = [];
  runFirsts.ending = null;
}

function syncArchive() {
  if (!state) return;
  const terminal = !!state.ended && state.ended.type !== 'chapter';
  const fresh = terminal && recordedRun !== state.seed;

  const { archive: next, firsts } = record(archive, state, {
    ended: fresh,
    completed: fresh && state.ended.type === 'finale',
  });
  archive = next;
  saveArchive(archive);

  for (const key of ['clues', 'items', 'companions']) {
    runFirsts[key] = [...new Set([...runFirsts[key], ...firsts[key]])];
  }
  if (firsts.ending) runFirsts.ending = firsts.ending;

  if (fresh) {
    recordedRun = state.seed;
    announceFirsts();
  }
}

/** 이번 회차에 처음 본 것들을 도감 알림으로 띄운다. */
function announceFirsts() {
  const lines = [];
  if (runFirsts.ending) lines.push('새로운 결말을 기록했다.');
  if (runFirsts.clues.length) lines.push(`처음 보는 단서 ${runFirsts.clues.length}개.`);
  if (runFirsts.items.length) lines.push(`처음 손에 넣은 물건 ${runFirsts.items.length}개.`);
  if (runFirsts.companions.length) {
    lines.push(`처음 만난 사람 ${runFirsts.companions.length}명.`);
  }
  if (!lines.length) return;

  renderEvent(logTarget(), {
    type: 'narration',
    tone: 'gm',
    text: ['도감에 새로 올라간 것이 있다.', ...lines],
  });
  scrollLog();
}

// ── 행동 ──────────────────────────────────────────────────────

/** 다음 에피소드로. 탐사자는 초기화되지 않는다. */
async function nextChapter(routeId) {
  if (busy) return;
  const moved = advanceEpisode(state, { routeId });
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
  // 고른 항로가 여정을 서술한다. 배 위에서 일어난 일도 여기서 드러난다.
  if (moved.route) intro.push({ type: 'narration', text: moved.route.text });
  if (moved.betrayal) {
    intro.push({
      type: 'betrayal',
      kind: moved.betrayal.kind,
      companion: moved.betrayal.companion.name,
      text: moved.betrayal.text,
    });
  }
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
  duck(true);
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
  duck(false);
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
  else if (kind === 'archive') content = archivePanel(archive);
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
    // 소리를 끄는 사람은 배경음도 끄려는 것이다. 켤 때는 각자 기억한 대로.
    setMusicEnabled(next && settings.music !== false);
    settings = { ...settings, sound: next };
    saveSettings(settings);
    syncSound();
    syncMusic();
  });

  const musicBtn = document.createElement('button');
  musicBtn.className = 'btn';
  const syncMusic = () => {
    musicBtn.textContent = `배경음 ${musicEnabled() ? '켜짐' : '꺼짐'}`;
  };
  syncMusic();
  musicBtn.addEventListener('click', () => {
    const next = !musicEnabled();
    setMusicEnabled(next);
    settings = { ...settings, music: next };
    saveSettings(settings);
    syncMusic();
    if (next && state) setMood(gm.combat ? 'combat' : moodFor(kindFor(gm.scene())));
  });

  const arcBtn = document.createElement('button');
  arcBtn.className = 'btn';
  arcBtn.textContent = '도감';
  arcBtn.addEventListener('click', () => openPanel('archive'));

  const saveBtn = document.createElement('button');
  saveBtn.className = 'btn';
  saveBtn.textContent = '지금 저장';
  saveBtn.addEventListener('click', () => {
    saveGame(state, slot);
    saveBtn.textContent = `${slot + 1}번 칸에 저장했습니다`;
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
    clearGame(slot);
    closePanel();
    stopMusic();
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

  wrap.append(soundBtn, musicBtn, arcBtn, saveBtn, restart, about);
  return wrap;
}

async function useItem(name) {
  closePanel();
  await freeAct(`${name} 사용`);
}

// ── 게임 시작 / 복구 ──────────────────────────────────────────

function boot(newState) {
  state = newState;
  recordedRun = null;
  resetFirsts();
  archive = countRun(archive);
  saveArchive(archive);
  episode = getEpisode(FIRST_EPISODE);
  gm = createGM({ state, episode });
  resetLog();
  show('play');
  updateHud();
  return play(gm.start());
}

function resume(n = 0) {
  const data = loadGame(n);
  if (!data) return false;
  slot = n;
  state = data.state;
  episode = getEpisode(state.episode);
  gm = createGM({ state, episode });
  resetLog();
  show('play');

  // 이어하기는 줄거리 요약으로 시작한다.
  //
  // 며칠 만에 돌아온 사람에게 장면 서술만 다시 보여 주면 "지금 이 방"만 알게 된다.
  // 왜 이 방에 있는지는 상태가 알고 있으므로 (engine/recap.js), 그것을 먼저 읽힌다.
  const scene = gm.scene();
  const intro = [
    { type: 'recap', lines: recap(state, episode) },
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

// ── 저장 칸 ───────────────────────────────────────────────────
//
// 슬롯 셋. 하나로 두면 새 직업을 시험해 보려다 진행 중인 판을 지우게 되고,
// 이 게임은 한 판이 한 시간짜리라 그 실수의 값이 크다.

const AGO = [
  [60, '분'],
  [24, '시간'],
  [Infinity, '일'],
];

/** 저장한 지 얼마나 됐는지. "3분 전" 정도면 충분하다. */
function agoText(ts) {
  let v = Math.max(0, (Date.now() - ts) / 1000 / 60);
  for (const [step, unit] of AGO) {
    if (v < step) return `${Math.floor(v) || 0}${unit} 전`;
    v /= step;
  }
  return '오래전';
}

function slotRow(info, mode) {
  const btn = document.createElement('button');
  btn.className = `btn slot${info.empty ? ' slot-vacant' : ''}`;
  btn.type = 'button';

  if (info.empty) {
    btn.innerHTML =
      `<span class="slot-no">${info.index + 1}</span>` +
      `<span class="slot-main"><b>빈 칸</b>` +
      `<span class="slot-sub">${mode === 'save' ? '여기서 시작한다' : '아직 아무것도 없다'}</span></span>`;
    btn.disabled = mode === 'load';
    return btn;
  }

  const clock = formatClock(info.tick);
  const where = getEpisode(info.episode)?.title.replace(/^에피소드\s*\d+\s*—\s*/, '') || '';
  const done = info.ended && info.ended !== 'chapter' ? ' · 끝난 판' : '';
  btn.innerHTML =
    `<span class="slot-no">${info.index + 1}</span>` +
    `<span class="slot-main"><b>${info.name}</b> <span class="slot-prof">${info.profession}</span>` +
    `<span class="slot-sub">제 ${info.chapter} 장 「${where}」 · 단서 ${info.clues}${done}</span>` +
    `<span class="slot-sub">${clock.date} · 체력 ${info.hp}/${info.maxHp} · 정신 ${info.san}/${info.maxSan}</span>` +
    `<span class="slot-sub faint">${agoText(info.savedAt)}에 저장</span></span>`;
  return btn;
}

/**
 * 저장 칸 목록을 연다.
 * @param {'load'|'save'} mode load 는 이어하기, save 는 새 판을 앉힐 칸 고르기
 * @param {Function} [onPick] save 일 때 고른 칸 번호를 받는다
 */
function openSlots(mode, onPick) {
  sfx.page();
  dom.sheetTitle.textContent = mode === 'load' ? '기록 이어하기' : '어느 칸에 시작할까';
  dom.sheetBody.innerHTML = '';

  const wrap = document.createElement('div');
  wrap.className = 'menu-list';

  if (mode === 'save') {
    wrap.appendChild(
      Object.assign(document.createElement('p'), {
        className: 'li-desc',
        textContent: '칸이 전부 차 있습니다. 덮어쓸 칸을 고르세요 — 그 판은 사라집니다.',
      }),
    );
  }

  for (const info of slotList()) {
    const row = slotRow(info, mode);
    row.addEventListener('click', () => {
      if (mode === 'load') {
        closePanel();
        resume(info.index);
        return;
      }
      // 덮어쓰기는 한 번 더 묻는다. 한 시간짜리 판이 사라지는 일이다.
      if (!info.empty && row.dataset.confirm !== '1') {
        row.dataset.confirm = '1';
        row.querySelector('.slot-sub').textContent = '정말 덮어씁니까? (한 번 더 누르면)';
        return;
      }
      closePanel();
      onPick(info.index);
    });
    wrap.appendChild(row);
  }

  dom.sheetBody.appendChild(wrap);
  dom.sheet.hidden = false;
  dom.sheetScrim.hidden = false;
}

function refreshTitle() {
  $('btn-continue').hidden = !hasAnySave();
}

// ── 이벤트 배선 ───────────────────────────────────────────────

$('btn-new').addEventListener('click', () => {
  sfx.page();
  if (!$('input-name').value.trim()) suggestName();
  show('create');
});

$('btn-reroll-name').addEventListener('click', () => {
  sfx.tap();
  suggestName();
});

$('btn-continue').addEventListener('click', () => {
  sfx.page();
  openSlots('load');
});

$('btn-archive').addEventListener('click', () => openPanel('archive'));

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

  const start = (n) => {
    slot = n;
    sfx.page();
    boot(
      createState({
        name,
        professionId: picked.id,
        difficulty: pickedDifficulty,
        seed: Date.now(),
      }),
    );
  };

  // 빈 칸이 있으면 묻지 않는다. 전부 차 있을 때만 무엇을 덮어쓸지 고르게 한다.
  const empty = firstEmptySlot();
  if (empty >= 0) start(empty);
  else openSlots('save', start);
});

dom.log.addEventListener('scroll', markOverflow, { passive: true });

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
  if (document.visibilityState === 'hidden' && state) saveGame(state, slot);
});

buildDifficulty();
buildCreation();
refreshTitle();
