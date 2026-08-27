// GM 엔진.
//
// 장면 진입 → 서술 → 선택/자유입력 → (필요시) 판정 → 결과 분기 → 다음 장면.
// UI 는 이 엔진이 뱉는 이벤트 배열을 로그에 붙이기만 한다.

import { subj, fill } from '../korean.js';
import { rollCheck, resolve, selectBranch, compareOutcome, OUTCOME } from './dice.js';
import { buildCheck, difficultyLabel, hasLight } from './rules.js';
import { applyEffects, formatClock, isDead, isBroken } from './state.js';
import { interpret, hallucination } from './freeform.js';
import { createRng } from './rng.js';
import { getItem } from '../content/items.js';
import { getEncounter } from '../content/encounters.js';
import { COMPANIONS } from '../content/companions.js';
import { resolveEnding, endingCoda } from '../content/endings.js';
import {
  checkBetrayal,
  checkRefusal,
  isShaky,
  warningFor,
  recoveryFor,
  setItemTier,
  MOMENT,
} from './betrayal.js';
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

// 배신 판정은 "가져갈 만한 것"을 알아야 하는데, 등급은 콘텐츠가 안다.
// 엔진이 콘텐츠를 import 하면 방향이 거꾸로가 되므로 여기서 한 번 주입한다.
setItemTier((name) => getItem(name)?.type || 'gear');

const WORTH_TAKING = ['relic', 'special'];

/**
 * 이 판정에서 장비가 실제로 결과를 바꿨는가.
 * 장비 보정을 빼고 다시 계산해 결과 구간이 내려가면 바꾼 것이다.
 */
export function itemMattered(built, result) {
  const entry = built.breakdown.find((b) => b.item);
  if (!entry || !entry.value) return false;
  const without = resolve(result.natural, result.modifier - entry.value, result.target);
  return compareOutcome(result.outcome, without.outcome) > 0;
}

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

/**
 * 콘텐츠가 준 문장을 화면에 올릴 수 있는 배열로 만든다.
 *
 * 여기가 서술이 지나가는 유일한 길목이라, 자리표({이름은} 따위)도 여기서 채운다.
 * 채우는 곳을 한 군데로 몰아 두면 콘텐츠 쪽에서 잊어버릴 일이 없다.
 */
const asArray = (v, state) => {
  const r = typeof v === 'function' ? v(state) : v;
  if (!r) return [];
  const list = Array.isArray(r) ? r : [r];
  const vars = { 이름: state?.char?.name, 직업: state?.char?.profession };
  if (!vars.이름) return list;
  return list.map((line) => fill(line, vars));
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
    state.flags[`encountered:${id}`] = true; // 도감이 이 플래그로 조우를 되짚는다
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

    noteRelations(events);
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

      // 부르는 것과 오는 것은 다른 일이다.
      const refusal = checkRefusal(c, rng);
      if (refusal) {
        events.push({
          type: 'betrayal',
          kind: refusal.kind,
          companion: c.name,
          text: refusal.text,
        });
        const refuseNotes = applyEffects(state, refusal.effects);
        if (refuseNotes.length) events.push({ type: 'notes', notes: refuseNotes });
        afterPlayerAction(events);
        sync();
        return events;
      }

      const { effects, injured } = applyAlly(state.combat, state, companionId);
      events.push({
        type: 'narration',
        text: injured
          ? [
              `${subj(c.name)} 당신 앞으로 나선다. 말릴 틈이 없었다.`,
              '한 사람 몫의 시간을 벌었고, 그 값은 그가 치렀다.',
            ]
          : [
              `${subj(c.name)} 옆으로 붙는다. 둘이 서면 통로가 좁아지는 쪽은 저쪽이다.`,
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

  // ── 배신 ──────────────────────────────────────────────────────

  /**
   * 관계가 문턱을 넘나들면 그때마다 한 줄 남긴다.
   *
   * 배신의 첫 번째 원칙은 '예고된다'이다. 동행 패널을 열어야만 알 수 있으면
   * 예고가 아니라 열람이다. 흔들리기 시작한 순간과 다시 붙은 순간을 로그에 적는다.
   */
  function noteRelations(events) {
    for (const c of Object.values(state.companions)) {
      const key = `shakyWarned:${c.id}`;
      if (isShaky(c)) {
        if (state.flags[key]) continue;
        state.flags[key] = true;
        events.push({ type: 'relation', tone: 'warn', text: [warningFor(c)] });
      } else if (state.flags[key]) {
        delete state.flags[key];
        if (c.present) events.push({ type: 'relation', tone: 'good', text: [recoveryFor(c)] });
      }
    }
  }

  /** 배신을 판정하고, 일어났으면 로그와 상태에 반영한다. */
  function maybeBetrayal(moment, events) {
    const b = checkBetrayal(state, rng, moment);
    if (!b) return null;

    events.push({
      type: 'betrayal',
      kind: b.kind,
      companion: b.companion.name,
      text: b.text,
    });
    const notes = applyEffects(state, b.effects);
    if (notes.length) events.push({ type: 'notes', notes });
    sync();
    return b;
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
      let eff = s.onEnter(state, state.visited[id]) || {};
      // 절정 장면은 들어서는 것만으로 사람을 죽이지 않는다.
      if (s.nonLethal) eff = survivable(eff, state);
      enterNotes = applyEffects(state, eff);
    }

    // 빛 없이 어둠으로 들어서면, 곁에 있는 사람이 자기 것을 하나 내준다.
    //
    // 유적의 서술은 램프가 있다는 전제로 쓰여 있고 그것이 맞다. 다만 준비를
    // 건너뛴 사람을 장 하나 내내 -2 로 묶어 두는 것은, 빛이 중요하다는 것을
    // 알기 전에 내린 선택의 값으로 지나치다. 빌린 등불은 제 것보다 어둡고
    // 오래 가지 않는다 — 그 차이가 시장에 들르는 이유로 남는다.
    let lender = null;
    if (s.dark && !hasLight(state) && !state.flags.lentLight) {
      lender = Object.values(state.companions).find((c) => c.present) || null;
      if (lender) {
        state.flags.lentLight = true;
        enterNotes.push(...applyEffects(state, { items: ['동행의 등불'] }));
      }
    }

    events.push(headerEvent());

    const revisit = state.visited[id] > 1 && s.revisitBody;
    events.push({ type: 'narration', text: asArray(revisit ? s.revisitBody : s.body, state) });

    // 등불을 건네는 장면은 방을 서술한 뒤에 온다. 그 전에 오면 장면 표시보다 앞선다.
    if (lender) {
      events.push({
        type: 'narration',
        tone: 'gm',
        text: [
          `${subj(lender.name)} 말없이 자기 짐에서 등불을 꺼내 건넨다.`,
          '"제 것도 얼마 안 남았습니다." 그 말만 하고 앞장선다.',
        ],
      });
    }

    if (enterNotes.length) events.push({ type: 'notes', notes: enterNotes });
    noteRelations(events);

    // 장면이 조우를 걸고 있으면 바로 전투로 들어간다.
    if (s.combat && !state.combat && !state.flags[`combatDone:${id}`]) {
      state.flags[`combatDone:${id}`] = true;
      beginCombat(s.combat, events);
    }

    // 결말 장면은 고정된 문장을 갖지 않는다. 세 대륙을 지나온 상태가 결말을 고른다.
    if (s.ending) {
      const ending = resolveEnding(state);
      state.ended = {
        type: 'finale',
        ending: ending.id,
        title: ending.title,
        text: `${ending.text}\n\n${endingCoda(state).join('\n')}`,
      };
      events.push({ type: 'end', end: state.ended });
    } else if (s.end) {
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

    // 효과도 상태를 볼 수 있다. "곁에 남은 사람 수만큼" 같은 것이 여기 걸린다.
    let effects =
      typeof res.effects === 'function' ? res.effects(state) || {} : res.effects || {};

    // 절정 장면은 사람을 죽이지 않는다.
    //
    // 세 대륙을 걸어 마지막 문 앞에 선 사람이 그 문을 만지는 순간 쓰러지면,
    // 캠페인 내내 쌓아 온 결말 분기를 영영 못 본다. 대가는 결말의 문장이 치른다 —
    // 정신이 바닥난 채 도착한 사람의 후일담은 이미 다르게 읽힌다.
    if (scene().nonLethal) effects = survivable(effects, state);

    const notes = applyEffects(state, effects);
    if (notes.length) events.push({ type: 'notes', notes });

    if (res.clueDetail) events.push({ type: 'clue', clue: res.clueDetail });

    noteRelations(events);
    if (checkVitals(events)) return;

    // 값나가는 것이 가방에 들어온 직후는 흔들리는 사람에게 가장 선명한 순간이다.
    const gained = (effects.items || []).filter((n) =>
      WORTH_TAKING.includes(getItem(n)?.type),
    );
    if (gained.length) maybeBetrayal(MOMENT.RELIC, events);

    const goto = res.goto || effects.goto;
    if (goto) enterScene(goto, events);
    else pressureEvent(events);
  }

  /** 판정을 준비한다. */
  function requestCheck(source, events) {
    const built = buildCheck(state, source.check, { dark: scene()?.dark });
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

    // 판정에 동원한 장비가 닳는다 — 단, 그것이 결과를 바꿨을 때만.
    //
    // 처음에는 무조건 닳게 했다. 그랬더니 목표값 11 짜리 잡담 판정에서 보정이 +12 인데도
    // 「위조 소개장」이 한 장뿐인 사용 횟수를 통째로 먹었다. 있으나 없으나 같은 결과였는데.
    // 플레이어는 어느 장비가 자동으로 동원될지 고르지 않으므로, 값은 그 장비가
    // 실제로 무언가를 바꿨을 때만 치르게 한다. 쓰지 않은 것을 쓴 것으로 세지 않는다.
    if (p.built.usedItem) {
      const def = getItem(p.built.usedItem);
      const wearable = def && def.uses !== null && def.uses !== undefined && !def.consumable;
      if (wearable && itemMattered(p.built, result)) {
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
        roster: COMPANIONS,
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
      roster: COMPANIONS,
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
