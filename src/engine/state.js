// 게임 상태 모델과 효과(effect) 적용.
//
// 콘텐츠는 상태를 직접 건드리지 않는다. 오직 effect 객체를 서술할 뿐이고,
// 적용과 한계 처리(클램프), 변화 알림 문구 생성은 전부 여기서 담당한다.

import { getProfession } from '../content/professions.js';
import { getItem } from '../content/items.js';
import { makeCompanion } from '../content/companions.js';
import { getDifficulty, scaleDamage } from '../content/difficulty.js';
import { createRng } from './rng.js';

export const SAVE_VERSION = 1;

/**
 * 위험도의 상한.
 *
 * 처음에는 10 이었다. 장면 하나에는 맞았지만 한 챕터에는 맞지 않았다 —
 * 장면마다 +1, 실패마다 +1~3 이 쌓이면 유적 하나를 훑는 동안 상한에 닿고,
 * 닿는 순간 모든 판정이 +2 어려워져 실패가 실패를 부른다.
 * 16 은 4~6개 장면짜리 유적 하나를 끝까지 도는 분량이다.
 */
export const MAX_DANGER = 16;

/** 조용히 흐른 시간이 이만큼 쌓이면 위험도가 1 내려간다. 1틱 = 30분. */
export const CALM_TICKS = 6;

const START_DAY = { year: 1897, month: 11, day: 3 };
const START_MINUTES = 8 * 60; // 오전 8시 출발

/**
 * 1틱 = 30분.
 *
 * 날짜는 달을 넘긴다. 캠페인이 세 장으로 늘면서 여정만 8주가 되었고,
 * 그때까지 "11월 59일" 이라고 적혀 있었다.
 */
export function formatClock(tick) {
  const total = START_MINUTES + tick * 30;
  const dayOffset = Math.floor(total / (24 * 60));
  const m = total % (24 * 60);
  const hh = Math.floor(m / 60);
  const mm = m % 60;

  const d = new Date(Date.UTC(START_DAY.year, START_DAY.month - 1, START_DAY.day + dayOffset));
  const ampm = hh < 12 ? '오전' : '오후';
  const h12 = hh % 12 === 0 ? 12 : hh % 12;

  return {
    date: `${d.getUTCFullYear()}년 ${d.getUTCMonth() + 1}월 ${d.getUTCDate()}일`,
    time: `${ampm} ${h12}시${mm ? ` ${mm}분` : ''}`,
    night: hh >= 19 || hh < 5,
  };
}

export function dangerLabel(d) {
  if (d <= 2) return '평온';
  if (d <= 5) return '주의';
  if (d <= 8) return '경계';
  if (d <= 11) return '위험';
  if (d <= 14) return '치명';
  return '붕괴 직전';
}

export function createState({ name, professionId, difficulty, seed = Date.now() } = {}) {
  const prof = getProfession(professionId);
  const diff = getDifficulty(difficulty);
  const rng = createRng(seed);

  const maxHp = Math.max(5, 10 + prof.stats['체력'] + diff.hpBonus);
  // 정신력은 한 장을 훑고도 남을 만큼은 되어야 한다.
  // 서사 행동 하나하나가 정신력을 먹는데 풀이 그 합보다 작으면,
  // 이야기를 끝까지 읽는 플레이어가 가장 먼저 쓰러진다.
  const maxSan = Math.max(6, 10 + prof.stats['의지'] * 2 + diff.sanBonus);

  return {
    version: SAVE_VERSION,
    seed,
    difficulty: diff.id,
    rngState: rng.getState(),
    char: {
      name: (name || '이름 없는 탐사자').trim().slice(0, 20),
      professionId: prof.id,
      profession: prof.name,
      stats: { ...prof.stats },
      tags: [...prof.tags],
      perk: prof.perk,
    },
    hp: maxHp,
    maxHp,
    san: maxSan,
    maxSan,
    danger: 0,
    calm: 0,
    tick: 0,
    inventory: prof.items.map((n) => ({ name: n, uses: getItem(n)?.uses ?? null })),
    clues: [],
    flags: {},
    companions: {},
    episode: null,
    visitedEpisodes: [],
    combat: null,
    scene: null,
    visited: {},
    rolls: [],
    ended: null, // { type, title, text }
  };
}

// ── 인벤토리 ────────────────────────────────────────────────────

export function hasItem(state, name) {
  return state.inventory.some((i) => i.name === name && (i.uses === null || i.uses > 0));
}

export function findItem(state, name) {
  return state.inventory.find((i) => i.name === name) || null;
}

export function addItem(state, name) {
  const def = getItem(name);
  const existing = findItem(state, name);
  if (existing && def && def.uses !== null && def.uses !== undefined) {
    existing.uses = Math.min((existing.uses || 0) + def.uses, def.uses * 2);
    return `${name} (보충)`;
  }
  if (existing) return null;
  state.inventory.push({ name, uses: def?.uses ?? null });
  return name;
}

export function spendItem(state, name, amount = 1) {
  const it = findItem(state, name);
  if (!it) return false;
  if (it.uses === null) return true; // 소모되지 않는 장비
  it.uses -= amount;
  if (it.uses <= 0) {
    state.inventory = state.inventory.filter((i) => i !== it);
    return 'depleted';
  }
  return true;
}

export function removeItem(state, name) {
  const before = state.inventory.length;
  state.inventory = state.inventory.filter((i) => i.name !== name);
  return state.inventory.length !== before;
}

// ── 단서 / 플래그 ───────────────────────────────────────────────

export function hasClue(state, id) {
  return state.clues.includes(id);
}

export function addClue(state, id) {
  if (state.clues.includes(id)) return false;
  state.clues.push(id);
  return true;
}

// ── 효과 적용 ───────────────────────────────────────────────────

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

/**
 * effect 객체를 상태에 적용하고, 화면에 띄울 변화 목록을 돌려준다.
 *
 * effect = {
 *   hp, san, danger, time,          // 숫자 증감
 *   items: ['횃불'],                // 획득
 *   removeItems: ['횃불'],          // 상실
 *   spend: { '횃불': 1 },           // 사용/내구 소모
 *   clues: ['black_sun'],           // 단서
 *   flags: { doorOpen: true },      // 플래그
 *   companions: ['nadia'],          // 합류
 *   companion: { id, affinity, trust, hp, injured, present },
 *   goto: 'scene_id',
 *   end: { type, title, text },
 * }
 */
export function applyEffects(state, effect) {
  const notes = [];
  if (!effect) return notes;

  // 피해에는 난이도 배율이 걸린다. 회복은 그대로 들어간다.
  if (effect.hp) {
    const before = state.hp;
    state.hp = clamp(state.hp + scaleDamage(effect.hp, state.difficulty), 0, state.maxHp);
    const d = state.hp - before;
    if (d) notes.push({ kind: d > 0 ? 'good' : 'bad', text: `체력 ${d > 0 ? '+' : ''}${d}` });
  }

  if (effect.san) {
    const before = state.san;
    state.san = clamp(state.san + scaleDamage(effect.san, state.difficulty), 0, state.maxSan);
    const d = state.san - before;
    if (d) notes.push({ kind: d > 0 ? 'good' : 'bad', text: `정신력 ${d > 0 ? '+' : ''}${d}` });
  }

  if (effect.danger) {
    const before = state.danger;
    state.danger = clamp(state.danger + effect.danger, 0, MAX_DANGER);
    const d = state.danger - before;
    if (d) notes.push({ kind: d > 0 ? 'bad' : 'good', text: `위험도 ${d > 0 ? '+' : ''}${d}` });
  }

  if (effect.time) {
    state.tick += effect.time;

    // 위험도는 시간이 지나면 가라앉는다.
    //
    // 이것이 없으면 위험도는 한쪽으로만 도는 톱니가 된다 — 유적 하나를 꼼꼼히 훑는
    // 동안 상한에 닿고, 닿는 순간 모든 판정이 어려워져 실패가 실패를 부른다.
    // 소리를 내지 않고 시간이 흐르면 추적은 식는다. 기획서 7-6의 '압박'은
    // 올라가기만 하는 숫자가 아니라 관리하는 숫자여야 한다.
    if (!effect.danger || effect.danger <= 0) {
      state.calm = (state.calm || 0) + effect.time;
      while (state.calm >= CALM_TICKS && state.danger > 0) {
        state.calm -= CALM_TICKS;
        state.danger -= 1;
      }
    } else {
      state.calm = 0;
    }
  }

  for (const name of effect.items || []) {
    const added = addItem(state, name);
    if (added) notes.push({ kind: 'good', text: `획득: ${added}` });
  }

  for (const name of effect.removeItems || []) {
    if (removeItem(state, name)) notes.push({ kind: 'bad', text: `상실: ${name}` });
  }

  for (const [name, amount] of Object.entries(effect.spend || {})) {
    const r = spendItem(state, name, amount);
    if (r === 'depleted') notes.push({ kind: 'bad', text: `${name} 소진` });
  }

  for (const id of effect.clues || []) {
    if (addClue(state, id)) notes.push({ kind: 'clue', text: `단서 기록됨`, clue: id });
  }

  if (effect.flags) Object.assign(state.flags, effect.flags);

  for (const id of effect.companions || []) {
    if (!state.companions[id]) {
      const c = makeCompanion(id);
      if (c) {
        state.companions[id] = c;
        notes.push({ kind: 'good', text: `${c.name} 합류` });
      }
    }
  }

  const cEffects = effect.companion ? [effect.companion] : effect.companionChanges || [];
  for (const ce of cEffects) {
    const c = state.companions[ce.id];
    if (!c) continue;
    if (ce.affinity) {
      c.affinity = clamp(c.affinity + ce.affinity, 0, 5);
      notes.push({
        kind: ce.affinity > 0 ? 'good' : 'bad',
        text: `${c.name} 호감도 ${ce.affinity > 0 ? '+' : ''}${ce.affinity}`,
      });
    }
    if (ce.trust) {
      c.trust = clamp(c.trust + ce.trust, 0, 5);
      notes.push({
        kind: ce.trust > 0 ? 'good' : 'bad',
        text: `${c.name} 신뢰도 ${ce.trust > 0 ? '+' : ''}${ce.trust}`,
      });
    }
    if (ce.hp) {
      c.hp = clamp(c.hp + ce.hp, 0, c.maxHp);
      notes.push({ kind: ce.hp > 0 ? 'good' : 'bad', text: `${c.name} 체력 ${ce.hp > 0 ? '+' : ''}${ce.hp}` });
      if (c.hp === 0) {
        c.present = false;
        notes.push({ kind: 'bad', text: `${c.name} 이탈` });

        // 한 사람이 쓰러지면 남은 사람들은 다음이 자기 차례일 수 있다고 생각한다.
        // 신뢰가 관리하는 수치가 되려면 이런 식으로도 깎여야 한다 —
        // 대사 한 줄을 잘못 고르는 것 말고, 사람을 잃는 것으로도.
        for (const other of Object.values(state.companions)) {
          if (other.id === c.id || !other.present || other.trust <= 0) continue;
          other.trust = clamp(other.trust - 1, 0, 5);
          notes.push({ kind: 'bad', text: `${other.name} 신뢰도 -1` });
        }
      }
    }
    if (ce.injured !== undefined) c.injured = ce.injured;
    if (ce.present !== undefined) c.present = ce.present;
  }

  if (effect.end) state.ended = effect.end;

  return notes;
}

/** 현재 상태가 판정에 주는 페널티. 음수로 반환한다. */
export function conditionPenalty(state) {
  let p = 0;
  const reasons = [];
  if (state.hp <= Math.ceil(state.maxHp * 0.3)) {
    p -= 2;
    reasons.push('중상');
  } else if (state.hp <= Math.ceil(state.maxHp * 0.6)) {
    p -= 1;
    reasons.push('부상');
  }
  if (state.san <= Math.ceil(state.maxSan * 0.3)) {
    p -= 2;
    reasons.push('공황');
  } else if (state.san <= Math.ceil(state.maxSan * 0.6)) {
    p -= 1;
    reasons.push('동요');
  }
  return { value: p, reasons };
}

/** 위험도가 판정 난이도에 주는 가중치. 양수로 반환한다(목표값에 더한다). */
export function dangerPressure(danger) {
  if (danger >= 13) return 2;
  if (danger >= 8) return 1;
  return 0;
}

export function isDead(state) {
  return state.hp <= 0;
}

export function isBroken(state) {
  return state.san <= 0;
}
