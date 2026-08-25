// GM 엔진.
//
// 장면 진입 → 서술 → 선택/자유입력 → (필요시) 판정 → 결과 분기 → 다음 장면.
// UI 는 이 엔진이 뱉는 이벤트 배열을 로그에 붙이기만 한다.

import { rollCheck, selectBranch, OUTCOME } from './dice.js';
import { buildCheck, difficultyLabel } from './rules.js';
import { applyEffects, formatClock, isDead, isBroken } from './state.js';
import { interpret, hallucination } from './freeform.js';
import { createRng } from './rng.js';
import { getItem } from '../content/items.js';
import { getEncounter } from '../content/encounters.js';
import {
  startCombat,
  combatActions,
  buildAction,
  applyAction,
  applyAlly,
  survivable,
  enemyTurn,
  checkExit,
  combatStatus,
  actionNarration,
  EXIT,
} from './combat.js';

/** 조건 확인. 콘텐츠의 requires 를 상태와 대조한다. */
export function meets(state, req) {
  if (!req) return { ok: true };

  for (const name of req.items || []) {
    const has = state.inventory.some((i) => i.name === name && (i.uses === null || i.uses > 0));
    if (!has) return { ok: false, reason: `${name} 필요` };
  }
  for (const id of req.clues || []) {
    if (!state.clues.includes(id)) return { ok: false, reason: '아직 모르는 것이 있다' };
  }
  for (const [k, v] of Object.entries(req.flags || {})) {
    if (state.flags[k] !== v) return { ok: false, reason: '조건이 맞지 않는다' };
  }
  for (const k of req.notFlags || []) {
    if (state.flags[k]) return { ok: false, reason: '이미 지나간 일이다' };
  }
  for (const t of req.tags || []) {
    if (!state.char.tags.includes(t)) return { ok: false, reason: `${t} 전문 지식 필요` };
  }
  for (const id of req.companions || []) {
    const c = state.companions[id];
    if (!c || !c.present) return { ok: false, reason: '동행이 필요하다' };
  }
  if (req.minStat) {
    for (const [stat, v] of Object.entries(req.minStat)) {
      if ((state.char.stats[stat] || 0) < v) return { ok: false, reason: `${stat} ${v} 이상 필요` };
    }
  }
  if (req.when && !req.when(state)) return { ok: false, reason: '지금은 아니다' };
  return { ok: true };
}

const asArray = (v, state) => {
  const r = typeof v === 'function' ? v(state) : v;
  if (!r) return [];
  return Array.isArray(r) ? r : [r];
};

export function createGM({ state, episode }) {
  const rng = createRng(state.seed);
  if (state.rngState !== undefined) rng.setState(state.rngState);

  // 지도가 "지금 어느 에피소드에 있는지"를 알아야 한다.
  state.episode = episode.id;

  let pending = null; // { label, check, built, outcomes, choiceId }

  const sync = () => {
    state.rngState = rng.getState();
  };

  function scene() {
    return episode.scenes[state.scene] || episode.scenes[episode.start];
  }

  // ── 전투 ──────────────────────────────────────────────────────

  function encounter() {
    return state.combat ? getEncounter(state.combat.id) : null;
  }

  function inCombat() {
    return !!state.combat && !state.combat.exit;
  }

  function beginCombat(id, events) {
    const enc = getEncounter(id);
    if (!enc) return;
    state.combat = startCombat(enc);
    events.push({ type: 'combatStart', status: combatStatus(state.combat, enc) });
    events.push({ type: 'narration', text: asArray(enc.intro, state), tone: 'combat' });
  }

  /** 전투를 끝내고 출구의 결과를 처리한다. */
  function finishCombat(events) {
    const enc = encounter();
    const exit = state.combat.exit;
    let result = enc.exits?.[exit];

    // 제압당한 것은 진 것이지 죽은 것이 아니다. 그 출구의 피해로는 죽지 않는다.
    if (exit === EXIT.OVERRUN && result?.effects) {
      result = { ...result, effects: survivable(result.effects, state) };
    }

    events.push({ type: 'combatEnd', exit, status: combatStatus(state.combat, enc) });
    state.combat = null;

    applyResult(result, events);
  }

  /** 상대의 차례와 전투 종료 판단. 플레이어 행동 뒤에 항상 이어진다. */
  function afterPlayerAction(events) {
    const enc = encounter();
    if (!enc) return;

    if (checkExit(state.combat)) {
      finishCombat(events);
      return;
    }

    const turn = enemyTurn(state.combat, enc);
    events.push({ type: 'narration', text: asArray(enc.enemyTurn[turn.tier], state), tone: 'enemy' });

    const notes = applyEffects(state, turn.effects);
    if (notes.length) events.push({ type: 'notes', notes });

    events.push({ type: 'combatRound', status: combatStatus(state.combat, enc) });

    if (checkVitals(events)) return;
    if (checkExit(state.combat)) finishCombat(events);
    sync();
  }

  /** 전투 행동 실행. */
  function combatAct(actionId, events) {
    const enc = encounter();
    const key = actionId.replace(/^combat:/, '');

    // 동료 지원 — 주사위를 굴리지 않는 유일한 행동.
    if (key.startsWith('ally:')) {
      const companionId = key.slice('ally:'.length);
      const c = state.companions[companionId];
      events.push({ type: 'player', text: `${c?.name || '동행'}에게 지원을 요청한다` });

      const { effects, injured } = applyAlly(state.combat, state, companionId);
      events.push({
        type: 'narration',
        text: injured
          ? [
              `${c.name}가 당신 앞으로 나선다. 말릴 틈이 없었다.`,
              '한 사람 몫의 시간을 벌었고, 그 값은 그가 치렀다.',
            ]
          : [
              `${c.name}가 옆으로 붙는다. 둘이 서면 통로가 좁아지는 쪽은 저쪽이다.`,
              '숨을 고를 틈이 생긴다.',
            ],
        tone: 'combat',
      });
      const notes = applyEffects(state, effects);
      if (notes.length) events.push({ type: 'notes', notes });

      afterPlayerAction(events);
      return events;
    }

    const spec = buildAction(state.combat, state, enc, key);
    const label = combatActions(state.combat, state, enc).find((a) => a.action === key)?.label || key;
    events.push({ type: 'player', text: label });

    if (key === 'terrain' && enc.terrain?.prompt) {
      events.push({ type: 'narration', text: asArray(enc.terrain.prompt, state) });
    }

    return requestCheck({ ...spec, combatAction: key }, events);
  }

  /** 전투 판정의 결과를 반영한다. */
  function resolveCombatRoll(actionKey, result, events) {
    const enc = encounter();
    const { effects } = applyAction(state.combat, enc, actionKey, result.outcome);

    events.push({
      type: 'narration',
      text: actionNarration(enc, actionKey, result.outcome),
      tone: 'combat',
    });

    const notes = applyEffects(state, effects);
    if (notes.length) events.push({ type: 'notes', notes });

    if (checkVitals(events)) return;
    afterPlayerAction(events);
  }

  function usedKey(sceneId, choiceId) {
    return `used:${sceneId}:${choiceId}`;
  }

  function headerEvent() {
    const s = scene();
    const clock = formatClock(state.tick);
    return {
      type: 'scene',
      id: s.id,
      location: s.location,
      date: clock.date,
      time: clock.time,
      danger: state.danger,
    };
  }

  /** 사망 / 정신 붕괴를 검사해 종료 이벤트를 만든다. */
  function checkVitals(events) {
    if (state.ended) {
      state.combat = null;
      return true;
    }
    if (isDead(state)) {
      state.ended = {
        type: 'death',
        title: '기록은 여기서 끊긴다',
        text:
          '수첩의 마지막 장은 젖어 있었고, 글씨는 중간에 멈춰 있었다.\n' +
          '탐사대는 당신을 찾지 못했다. 유적은 다시 조용해졌다.',
      };
      events.push({ type: 'end', end: state.ended });
      state.combat = null; // 탐사가 끝났으면 전투도 끝났다
      return true;
    }
    if (isBroken(state)) {
      state.ended = {
        type: 'broken',
        title: '당신은 돌아왔다. 전부는 아니었다',
        text:
          '카이로의 병실에서 당신은 같은 문장을 반복해서 적었다.\n' +
          '"우리가 처음이 아니었다."\n' +
          '의사들은 그것을 섬망이라고 기록했다.',
      };
      events.push({ type: 'end', end: state.ended });
      state.combat = null;
      return true;
    }
    return false;
  }

  /** 위험도가 높을 때 터지는 압박 이벤트. */
  function pressureEvent(events) {
    if (state.ended || pending) return;
    const pool = (episode.pressureEvents || []).filter(
      (e) =>
        state.danger >= e.minDanger &&
        !state.flags[`pressure:${e.id}`] &&
        (!e.when || e.when(state)) &&
        (!e.scenes || e.scenes.includes(state.scene)),
    );
    if (!pool.length) return;
    if (!rng.chance(Math.min(0.55, state.danger * 0.07))) return;

    const ev = rng.pick(pool);
    state.flags[`pressure:${ev.id}`] = true;
    events.push({ type: 'pressure', text: asArray(ev.text, state) });
    const notes = applyEffects(state, ev.effects || {});
    if (notes.length) events.push({ type: 'notes', notes });
    sync();
  }

  function enterScene(id, events = []) {
    const s = episode.scenes[id];
    if (!s) {
      events.push({ type: 'narration', text: ['(길이 끊겼다. 이 앞은 아직 지도에 없다.)'] });
      return events;
    }
    state.scene = id;
    state.visited[id] = (state.visited[id] || 0) + 1;

    // 진입 효과는 먼저 상태에 반영하되(본문 서술이 그 결과를 참조할 수 있으므로),
    // 변화 알림은 장면 서술 뒤에 붙인다. 알림이 서술보다 먼저 오면 흐름이 끊긴다.
    let enterNotes = [];
    if (s.onEnter) {
      enterNotes = applyEffects(state, s.onEnter(state, state.visited[id]) || {});
    }

    events.push(headerEvent());

    const revisit = state.visited[id] > 1 && s.revisitBody;
    events.push({ type: 'narration', text: asArray(revisit ? s.revisitBody : s.body, state) });

    if (enterNotes.length) events.push({ type: 'notes', notes: enterNotes });

    // 장면이 조우를 걸고 있으면 바로 전투로 들어간다.
    if (s.combat && !state.combat && !state.flags[`combatDone:${id}`]) {
      state.flags[`combatDone:${id}`] = true;
      beginCombat(s.combat, events);
    }

    if (s.end) {
      state.ended = { type: s.end.type || 'chapter', title: s.end.title, text: s.end.text };
      events.push({ type: 'end', end: state.ended });
    }
    checkVitals(events);
    sync();
    return events;
  }

  /** 지금 화면에 띄울 선택지. */
  function choices() {
    if (pending) return [];
    if (state.ended) return [];

    // 전투 중에는 장면의 선택지 대신 전투 행동만 내준다.
    if (inCombat()) return combatActions(state.combat, state, encounter());

    const s = scene();
    const out = [];
    for (const c of s.choices || []) {
      if (c.once && state.flags[usedKey(s.id, c.id)]) continue;
      const m = meets(state, c.requires);
      if (!m.ok && c.hideIfLocked !== false) continue;
      out.push({
        id: c.id,
        label: typeof c.label === 'function' ? c.label(state) : c.label,
        hint: c.hint,
        locked: !m.ok,
        lockReason: m.reason,
        isCheck: !!c.check,
        stat: c.check?.stat,
      });
    }
    return out;
  }

  /** 결과(서술 + 효과 + 이동)를 처리한다. */
  function applyResult(res, events) {
    if (!res) return;
    const text = asArray(res.text, state);
    if (text.length) events.push({ type: 'narration', text, tone: res.tone });

    const notes = applyEffects(state, res.effects || {});
    if (notes.length) events.push({ type: 'notes', notes });

    if (res.clueDetail) events.push({ type: 'clue', clue: res.clueDetail });

    if (checkVitals(events)) return;

    const goto = res.goto || res.effects?.goto;
    if (goto) enterScene(goto, events);
    else pressureEvent(events);
  }

  /** 판정을 준비한다. */
  function requestCheck(source, events) {
    const built = buildCheck(state, source.check);
    pending = {
      label: source.check.label || source.label || '판정',
      stat: source.check.stat,
      tags: source.check.tags || [],
      built,
      outcomes: source.outcomes,
      after: source.after,
      combatAction: source.combatAction,
    };
    if (source.check.prompt) {
      events.push({ type: 'narration', text: asArray(source.check.prompt, state) });
    }
    events.push({
      type: 'checkRequest',
      label: pending.label,
      stat: pending.stat,
      target: built.target,
      modifier: built.modifier,
      breakdown: built.breakdown,
      difficulty: difficultyLabel(built.target),
      pressure: built.pressure,
      difficultyShift: built.difficultyShift,
    });
    sync();
    return events;
  }

  /** 대기 중인 판정의 주사위를 굴린다. */
  function roll() {
    const events = [];
    if (!pending) return events;

    const p = pending;
    const result = rollCheck(rng, { modifier: p.built.modifier, target: p.built.target });

    state.rolls.push({
      scene: state.scene,
      label: p.label,
      natural: result.natural,
      total: result.total,
      target: result.target,
      outcome: result.outcome,
    });

    events.push({
      type: 'roll',
      label: p.label,
      stat: p.stat,
      result,
      breakdown: p.built.breakdown,
    });

    // 판정에 동원한 장비가 닳는다.
    if (p.built.usedItem) {
      const def = getItem(p.built.usedItem);
      if (def && def.uses !== null && def.uses !== undefined && !def.consumable) {
        const notes = applyEffects(state, { spend: { [p.built.usedItem]: 1 } });
        if (notes.length) events.push({ type: 'notes', notes });
      }
    }

    pending = null;

    if (p.combatAction && state.combat) {
      resolveCombatRoll(p.combatAction, result, events);
      sync();
      return events;
    }

    const branch = selectBranch(p.outcomes, result.outcome);
    applyResult(branch, events);

    if (p.after) applyResult(p.after(state, result) || {}, events);

    sync();
    return events;
  }

  /** 선택지 실행. */
  function act(choiceId) {
    const events = [];
    if (state.ended || pending) return events;

    if (inCombat()) {
      if (!String(choiceId).startsWith('combat:')) return events;
      return combatAct(choiceId, events);
    }

    const s = scene();
    const c = (s.choices || []).find((x) => x.id === choiceId);
    if (!c) return events;

    const m = meets(state, c.requires);
    if (!m.ok) {
      events.push({
        type: 'narration',
        text: [c.lockedText || `그렇게 하려면 아직 부족한 것이 있다. (${m.reason})`],
      });
      return events;
    }

    events.push({ type: 'player', text: typeof c.label === 'function' ? c.label(state) : c.label });
    if (c.once) state.flags[usedKey(s.id, c.id)] = true;

    if (c.check) return requestCheck(c, events);

    applyResult(c, events);
    sync();
    return events;
  }

  /** 자유 입력. */
  function freeAct(input) {
    const events = [];
    if (state.ended || pending) return events;

    events.push({ type: 'player', text: input, free: true });

    // 전투 중의 자유 입력은 소지품 사용만 받는다 (기획서 10절의 '아이템 사용').
    // 그 외에는 지금 할 수 있는 일이 아니라고 세계관 안에서 말한다.
    if (inCombat()) {
      const action = interpret(input, {
        state,
        scene: scene(),
        getItemDef: getItem,
        clueTitles: episode.clueTitles || {},
      });

      if (action.effects?.spend || action.effects?.hp > 0 || action.effects?.san > 0) {
        events.push({ type: 'narration', text: asArray(action.text, state), tone: 'combat' });
        const notes = applyEffects(state, { ...action.effects, time: 0 });
        if (notes.length) events.push({ type: 'notes', notes });
        afterPlayerAction(events);
        sync();
        return events;
      }

      events.push({
        type: 'narration',
        text: [
          '지금은 그럴 시간이 없다.',
          '손에 쥔 것을 쓰거나, 몸으로 결정하거나. 둘 중 하나다.',
        ],
        tone: 'gm',
      });
      return events;
    }

    const halluc = hallucination(state, rng);
    if (halluc) events.push({ type: 'narration', text: [halluc], tone: 'eerie' });

    const action = interpret(input, {
      state,
      scene: scene(),
      getItemDef: getItem,
      clueTitles: episode.clueTitles || {},
    });

    if (action.kind === 'choice') {
      const s = scene();
      if (action.choice.once) state.flags[usedKey(s.id, action.choice.id)] = true;
      if (action.choice.check) return requestCheck(action.choice, events);
      applyResult(action.choice, events);
      sync();
      return events;
    }

    if (action.kind === 'check') return requestCheck(action, events);

    if (action.kind === 'unknown') {
      events.push({ type: 'narration', text: asArray(action.text, state), tone: 'gm' });
      sync();
      return events;
    }

    applyResult(action, events);
    sync();
    return events;
  }

  return {
    get pending() {
      return pending;
    },
    get combat() {
      return inCombat() ? combatStatus(state.combat, encounter()) : null;
    },
    scene,
    choices,
    enterScene,
    act,
    freeAct,
    roll,
    header: headerEvent,
    start() {
      return enterScene(state.scene || episode.start, []);
    },
  };
}

export { OUTCOME };
