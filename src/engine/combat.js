// 전투 — 턴제, 텍스트 로그, 선택지 기반 (기획서 10절).
//
// 이 게임의 전투는 적을 죽이는 일이 아니다. 좁은 통로에서 살아 나오는 일이다.
// 그래서 두 개의 시계를 돌린다.
//
//   전의(resolve)  — 상대가 이 일을 계속할 의지. 0이 되면 물러난다.
//   압박(pressure) — 당신이 노출된 정도. 꽉 차면 제압당한다.
//
// 공격만으로 이기려 하면 압박이 먼저 찬다. 엄폐는 압박을 내리지만 전의를 깎지 못한다.
// 지형·협상·도주는 각각 다른 출구다. 넷 다 유효한 결말이고, 그중 어느 것도 패배가 아니다.
//
// 판정은 전부 기존 1D20 엔진을 그대로 쓴다. 전투만의 주사위 규칙은 없다.

import { OUTCOME } from './dice.js';

export const MAX_PRESSURE = 10;

/** 전투의 끝. 넷 다 '전투 종료'이지, 셋이 패배인 것이 아니다. */
export const EXIT = {
  WIN: 'win', // 상대가 물러났다
  PARLEY: 'parley', // 말이 통했다
  ESCAPE: 'escape', // 빠져나왔다
  OVERRUN: 'overrun', // 제압당했다
};

/** 도주는 한 번에 되지 않는다. 두 번 성공해야 통로를 벗어난다. */
export const ESCAPE_NEEDED = 2;

export function startCombat(encounter) {
  return {
    id: encounter.id,
    round: 1,
    resolve: encounter.resolve,
    maxResolve: encounter.resolve,
    pressure: 0,
    maxPressure: encounter.maxPressure ?? MAX_PRESSURE,
    escape: 0,
    used: {},
    exit: null,
  };
}

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// ── 행동 정의 ───────────────────────────────────────────────────
//
// 각 행동은 어떤 능력치로 굴리고, 결과 구간마다 두 시계를 어떻게 움직이는지 정한다.
// 서술은 조우(encounter)가 갖는다 — 규칙은 공통이고 문장은 장소마다 다르다.

export const ACTIONS = {
  attack: {
    id: 'attack',
    label: '공격한다',
    stat: '민첩',
    tags: ['전투'],
    hint: '전의를 깎는다. 대신 소리가 난다',
    targetFrom: 'defense',
    deltas: {
      crit: { resolve: -3, pressure: 1 },
      success: { resolve: -2, pressure: 1 },
      partial: { resolve: -1, pressure: 2 },
      fail: { resolve: 0, pressure: 1, hp: -1 },
      fumble: { resolve: 0, pressure: 2, hp: -2 },
    },
  },
  cover: {
    id: 'cover',
    label: '엄폐한다',
    stat: '민첩',
    tags: ['전투', '잠입'],
    hint: '압박을 내린다. 전의는 깎지 못한다',
    target: 12,
    deltas: {
      crit: { pressure: -5 },
      success: { pressure: -4 },
      partial: { pressure: -2 },
      fail: { pressure: 1 },
      fumble: { pressure: 2, hp: -1 },
    },
  },
  terrain: {
    id: 'terrain',
    label: '지형을 이용한다',
    hint: '한 번뿐이다. 통하면 판이 바뀐다',
    once: true,
    deltas: {
      crit: { resolve: -5, pressure: -3 },
      success: { resolve: -4, pressure: -2 },
      partial: { resolve: -2, pressure: 1 },
      fail: { pressure: 2, hp: -1 },
      fumble: { pressure: 3, hp: -2 },
    },
  },
  parley: {
    id: 'parley',
    label: '말을 건다',
    stat: '설득',
    tags: ['사교', '정보'],
    hint: '전의가 낮을수록 잘 통한다',
    targetFrom: 'parleyTarget',
    deltas: {
      crit: { resolve: -4, pressure: -2, parley: true },
      success: { resolve: -3, pressure: -1, parley: true },
      partial: { resolve: -1 },
      fail: { pressure: 2 },
      fumble: { resolve: 2, pressure: 3 },
    },
  },
  flee: {
    id: 'flee',
    label: '도주한다',
    stat: '탐험',
    tags: ['탈출', '이동'],
    hint: `${ESCAPE_NEEDED}번 성공하면 벗어난다`,
    targetFrom: 'fleeTarget',
    deltas: {
      crit: { escape: 2, pressure: -1 },
      success: { escape: 1, pressure: 1 },
      partial: { escape: 1, pressure: 2, hp: -1 },
      fail: { pressure: 3, hp: -1 },
      fumble: { pressure: 4, hp: -2 },
    },
  },
};

/**
 * 협상은 상대의 전의가 남아 있으면 통하지 않는다.
 * 말로 끝내려면 먼저 상대가 이 일이 수지 안 맞는다는 것을 알아야 한다.
 */
export function parleyReady(combat) {
  return combat.resolve <= Math.ceil(combat.maxResolve * 0.5);
}

/** 지금 고를 수 있는 전투 행동. */
export function combatActions(combat, state, encounter) {
  const out = [];

  for (const key of ['attack', 'cover', 'terrain', 'parley', 'flee']) {
    const base = ACTIONS[key];
    if (key === 'terrain') {
      if (!encounter.terrain) continue;
      if (combat.used.terrain) continue;
    }
    const label =
      key === 'terrain' ? encounter.terrain.label : base.label;
    const stat = key === 'terrain' ? encounter.terrain.stat : base.stat;

    let hint = base.hint;
    if (key === 'parley' && !parleyReady(combat)) {
      hint = '아직 들을 생각이 없다 — 전의를 더 깎아야 한다';
    }
    if (key === 'flee' && combat.escape > 0) {
      hint = `한 번 더 성공하면 벗어난다`;
    }

    out.push({ id: `combat:${key}`, action: key, label, hint, stat, isCheck: true });
  }

  // 동료 지원 — 유일하게 주사위를 굴리지 않는 행동.
  // 확실하지만 대가가 있다. 동료가 대신 노출된다.
  for (const c of Object.values(state.companions)) {
    if (!c.present || c.hp <= 0) continue;
    if (combat.used[`ally:${c.id}`]) continue;
    out.push({
      id: `combat:ally:${c.id}`,
      action: 'ally',
      companion: c.id,
      label: `${c.name}에게 지원을 요청한다`,
      hint: '판정 없음. 확실하지만 그가 대신 노출된다',
      isCheck: false,
    });
  }

  return out;
}

/** 행동 하나의 판정 사양을 만든다. */
export function buildAction(combat, state, encounter, actionKey) {
  const base = ACTIONS[actionKey];
  if (!base) return null;

  const custom = actionKey === 'terrain' ? encounter.terrain : null;
  const stat = custom?.stat || base.stat;
  const target =
    custom?.target ??
    (base.targetFrom ? encounter[base.targetFrom] : base.target) ??
    13;

  // 협상은 상대가 들을 준비가 되어야 쉬워진다.
  let bonus = 0;
  let bonusLabel;
  if (actionKey === 'parley' && parleyReady(combat)) {
    bonus = 3;
    bonusLabel = '꺾인 전의';
  }
  if (actionKey === 'flee' && combat.pressure >= 7) {
    bonus = -2;
    bonusLabel = '사방이 막혔다';
  }

  return {
    label: custom?.checkLabel || `${stat} 판정`,
    check: { stat, tags: custom?.tags || base.tags, target, bonus, bonusLabel },
  };
}

/**
 * 판정 결과를 전투에 반영한다.
 * @returns {{ deltas:object, effects:object }} 전투 변화와 플레이어 상태 변화
 */
export function applyAction(combat, encounter, actionKey, outcome) {
  const base = ACTIONS[actionKey];
  const d = base.deltas[outcome] || {};

  combat.resolve = clamp(combat.resolve + (d.resolve || 0), 0, combat.maxResolve);
  combat.pressure = clamp(combat.pressure + (d.pressure || 0), 0, combat.maxPressure);
  combat.escape = clamp(combat.escape + (d.escape || 0), 0, ESCAPE_NEEDED);
  if (base.once) combat.used[actionKey] = true;

  const effects = {};
  if (d.hp) effects.hp = d.hp;

  // 말이 통했는가 — 전의가 꺾인 뒤의 성공만 인정한다.
  if (d.parley && combat.resolve <= 0) combat.exit = EXIT.PARLEY;
  else if (d.parley && parleyReady(combat) && outcome === OUTCOME.CRIT) {
    combat.exit = EXIT.PARLEY;
  }

  return { deltas: d, effects };
}

/** 동료 지원. 주사위를 굴리지 않는다. */
export function applyAlly(combat, state, companionId) {
  const c = state.companions[companionId];
  if (!c) return { effects: {}, injured: false };

  combat.used[`ally:${companionId}`] = true;

  // 그가 뛰어든 순간의 압박이 그가 감당한 위험이다.
  // 완화된 뒤의 수치로 재면, 도와준 대가가 도움의 크기만큼 깎인다.
  const exposure = combat.pressure;

  combat.resolve = clamp(combat.resolve - 2, 0, combat.maxResolve);
  combat.pressure = clamp(combat.pressure - 2, 0, combat.maxPressure);

  const risk = exposure >= 6 ? -3 : -1;
  return {
    effects: { companion: { id: companionId, hp: risk, trust: 1 } },
    injured: risk <= -3,
  };
}

/**
 * 상대의 차례. 압박이 오르고, 높으면 맞는다.
 * @returns {{ tier:string, effects:object }}
 */
export function enemyTurn(combat, encounter) {
  combat.pressure = clamp(combat.pressure + (encounter.threat ?? 2), 0, combat.maxPressure);

  const effects = {};
  const ratio = combat.pressure / combat.maxPressure;
  let tier = 'low';
  if (ratio >= 0.8) {
    tier = 'high';
    effects.hp = -1;
  } else if (ratio >= 0.5) {
    tier = 'mid';
  }

  combat.round += 1;
  return { tier, effects };
}

/** 전투가 끝났는가. 끝났다면 어떻게. */
export function checkExit(combat) {
  if (combat.exit) return combat.exit;
  if (combat.escape >= ESCAPE_NEEDED) return (combat.exit = EXIT.ESCAPE);
  if (combat.resolve <= 0) return (combat.exit = EXIT.WIN);
  if (combat.pressure >= combat.maxPressure) return (combat.exit = EXIT.OVERRUN);
  return null;
}

/**
 * 결과 구간에 맞는 서술을 고른다.
 * 대성공·대실패는 성공·실패 서술 위에 한 줄을 얹는다 — 같은 일이 더 크게 벌어진 것이므로.
 */
export function actionNarration(encounter, actionKey, outcome) {
  const a = encounter.actions?.[actionKey];
  if (!a) return [];

  const tier =
    outcome === OUTCOME.CRIT || outcome === OUTCOME.SUCCESS
      ? 'good'
      : outcome === OUTCOME.PARTIAL
        ? 'mixed'
        : 'bad';

  const lines = [...(a[tier] || [])];
  if (outcome === OUTCOME.CRIT && a.critLine) lines.push(a.critLine);
  if (outcome === OUTCOME.FUMBLE && a.fumbleLine) lines.push(a.fumbleLine);
  return lines;
}

/**
 * 제압당하는 것은 죽는 것이 아니다.
 *
 * 출구의 서술은 "깨어났을 때 가방이 열려 있었다"라고 말한다. 그 서술이 나온 직후에
 * 체력이 0이 되어 죽으면, 게임이 방금 한 말을 스스로 뒤집는 셈이다.
 * 그래서 제압 출구의 피해는 최소 1을 남긴다. 값은 체력이 아니라 잃은 물건으로 치른다.
 */
export function survivable(effects, state) {
  if (!effects?.hp || effects.hp >= 0) return effects;
  const floor = -(state.hp - 1);
  return { ...effects, hp: Math.max(effects.hp, Math.min(0, floor)) };
}

/** 화면에 띄울 전투 상태. */
export function combatStatus(combat, encounter) {
  return {
    name: encounter.name,
    subtitle: encounter.subtitle,
    round: combat.round,
    resolve: combat.resolve,
    maxResolve: combat.maxResolve,
    pressure: combat.pressure,
    maxPressure: combat.maxPressure,
    escape: combat.escape,
    escapeNeeded: ESCAPE_NEEDED,
  };
}
