// 신뢰와 배신 (기획서 18절).
//
// 배신은 벌이 아니라 결과다. 그래서 이 파일이 지키는 것은 확률이 아니라 세 가지 약속이다.
//   1. 합류하는 순간부터 흔들리는 사람은 없다 (플레이어가 만든 결과여야 한다)
//   2. 예고 없이 터지지 않는다 (경고가 먼저 뜬다)
//   3. 흔들리지 않는 사람은 절대 등을 돌리지 않는다

import test from 'node:test';
import assert from 'node:assert/strict';
import {
  isShaky,
  checkBetrayal,
  checkRefusal,
  warnings,
  setItemTier,
  MOMENT,
} from '../src/engine/betrayal.js';
import { COMPANIONS, makeCompanion } from '../src/content/companions.js';
import { ITEMS } from '../src/content/items.js';
import { createState, applyEffects } from '../src/engine/state.js';
import { createRng } from '../src/engine/rng.js';
import { createGM } from '../src/engine/gm.js';
import { EPISODES } from '../src/content/episodes/index.js';

setItemTier((name) => ITEMS[name]?.type || 'gear');

/** 무슨 확률이든 반드시 일어나는 / 절대 일어나지 않는 주사위. */
const always = { chance: () => true, pick: (a) => a[0] };
const never = { chance: () => false, pick: (a) => a[0] };

function party(overrides = {}) {
  const state = createState({ professionId: 'archaeologist', seed: 5 });
  applyEffects(state, { companions: ['nadia'] });
  Object.assign(state.companions.nadia, overrides);
  return state;
}

test('합류하는 순간부터 흔들리는 동료는 없다', () => {
  for (const id of Object.keys(COMPANIONS)) {
    const c = makeCompanion(id);
    assert.equal(isShaky(c), false, `${c.name}가 합류하자마자 배신 후보다`);
  }
});

test('신뢰와 호감이 둘 다 바닥일 때만 흔들린다', () => {
  assert.equal(isShaky({ present: true, trust: 0, affinity: 0 }), true);
  assert.equal(isShaky({ present: true, trust: 1, affinity: 1 }), true);
  assert.equal(isShaky({ present: true, trust: 0, affinity: 3 }), false, '좋아하면 남는다');
  assert.equal(isShaky({ present: true, trust: 4, affinity: 0 }), false, '믿으면 남는다');
  assert.equal(isShaky({ present: false, trust: 0, affinity: 0 }), false, '이미 떠난 사람');
});

test('흔들리지 않으면 어떤 주사위로도 배신은 없다', () => {
  const state = party();
  assert.equal(checkBetrayal(state, always, MOMENT.CHAPTER), null);
  assert.equal(checkRefusal(state.companions.nadia, always), null);
});

test('배신은 예고된다 — 경고가 먼저 뜬다', () => {
  const state = party({ trust: 0, affinity: 0 });
  const warn = warnings(state);
  assert.equal(warn.length, 1);
  assert.equal(warn[0].id, 'nadia');
  assert.ok(warn[0].text.includes('나디아'));

  // 경고가 뜨는 상태에서만 배신이 일어난다.
  const b = checkBetrayal(state, always, MOMENT.CHAPTER);
  assert.ok(b, '경고까지 떴는데 아무 일도 일어나지 않는다');
  assert.equal(b.companion.id, 'nadia');
  assert.ok(b.text.length >= 2, '이유가 문장으로 남지 않았다');
});

test('가져갈 만한 것이 있으면 유물을 들고 간다', () => {
  const state = party({ trust: 0, affinity: 0 });
  applyEffects(state, { items: ['조각난 석판'] });

  const b = checkBetrayal(state, always, MOMENT.RELIC);
  assert.equal(b.kind, 'take');
  assert.deepEqual(b.effects.removeItems, ['조각난 석판']);

  applyEffects(state, b.effects);
  assert.equal(state.companions.nadia.present, false);
  assert.equal(state.inventory.some((i) => i.name === '조각난 석판'), false);
});

test('가져갈 유물이 없으면 조용히 떠난다', () => {
  const state = party({ trust: 0, affinity: 0 });
  state.inventory = [{ name: '횃불', uses: 6 }]; // 일반 장비는 값이 안 나간다

  const b = checkBetrayal(state, always, MOMENT.RELIC);
  assert.equal(b.kind, 'leave');
  assert.equal(b.effects.removeItems, undefined);
});

test('되돌릴 수 있다 — 신뢰를 올리면 후보에서 빠진다', () => {
  const state = party({ trust: 0, affinity: 0 });
  assert.equal(warnings(state).length, 1);

  applyEffects(state, { companion: { id: 'nadia', trust: 2 } });
  assert.equal(isShaky(state.companions.nadia), false);
  assert.deepEqual(warnings(state), []);
  assert.equal(checkBetrayal(state, always, MOMENT.CHAPTER), null);
});

test('주사위가 나오지 않으면 흔들려도 남는다', () => {
  const state = party({ trust: 0, affinity: 0 });
  assert.equal(checkBetrayal(state, never, MOMENT.CHAPTER), null);
});

test('전투 중 지원 거절은 호감도를 깎고 사람을 데려가지는 않는다', () => {
  const state = party({ trust: 0, affinity: 1 });
  const r = checkRefusal(state.companions.nadia, always);
  assert.equal(r.kind, 'refuse');
  assert.equal(r.effects.companion.affinity, -1);
  assert.equal(r.effects.companion.present, undefined, '거절이 이탈이 되어서는 안 된다');
});

test('같은 시드는 같은 배신을 낸다', () => {
  const make = () => party({ trust: 0, affinity: 0 });
  const a = checkBetrayal(make(), createRng(77), MOMENT.CHAPTER);
  const b = checkBetrayal(make(), createRng(77), MOMENT.CHAPTER);
  assert.deepEqual(a?.kind, b?.kind);
});

test('흔들리기 시작하면 로그에 한 줄이 남는다 — 동행 패널을 열지 않아도', () => {
  const state = createState({ professionId: 'archaeologist', seed: 5 });
  const gm = createGM({ state, episode: EPISODES.luxor });
  gm.start();
  applyEffects(state, { companions: ['nadia'] });

  const events = [];
  // 관계 알림은 장면 진입과 결과 처리에 얹혀 나온다.
  const emit = () => events.push(...gm.enterScene(state.scene, []));

  Object.assign(state.companions.nadia, { trust: 1, affinity: 1 });
  emit();
  const warn = events.filter((e) => e.type === 'relation');
  assert.equal(warn.length, 1, '흔들리는데 아무 말도 없었다');
  assert.equal(warn[0].tone, 'warn');

  // 같은 경고를 계속 반복하지 않는다.
  events.length = 0;
  emit();
  assert.deepEqual(events.filter((e) => e.type === 'relation'), []);

  // 회복하면 그것도 알려 준다.
  events.length = 0;
  applyEffects(state, { companion: { id: 'nadia', trust: 2 } });
  emit();
  const back = events.filter((e) => e.type === 'relation');
  assert.equal(back.length, 1);
  assert.equal(back[0].tone, 'good');
});

test('사람을 잃으면 남은 사람들의 신뢰가 깎인다', () => {
  const state = createState({ professionId: 'archaeologist', seed: 5 });
  applyEffects(state, { companions: ['nadia', 'finch'] });
  const before = state.companions.finch.trust;

  applyEffects(state, { companion: { id: 'nadia', hp: -99 } });
  assert.equal(state.companions.nadia.present, false);
  assert.equal(state.companions.finch.trust, before - 1, '한 사람을 잃었는데 아무도 흔들리지 않는다');

  // 배신으로 조용히 떠난 것은 남은 사람들에게 같은 무게가 아니다.
  const t = state.companions.finch.trust;
  applyEffects(state, { companion: { id: 'finch', present: false } });
  applyEffects(state, { companion: { id: 'finch', present: true } });
  assert.equal(state.companions.finch.trust, t);
});

test('가장 흔들리는 사람부터 떠난다', () => {
  const state = createState({ professionId: 'archaeologist', seed: 5 });
  applyEffects(state, { companions: ['nadia', 'finch'] });
  Object.assign(state.companions.nadia, { trust: 1, affinity: 1 });
  Object.assign(state.companions.finch, { trust: 0, affinity: 0 });

  const b = checkBetrayal(state, always, MOMENT.CHAPTER);
  assert.equal(b.companion.id, 'finch');
});
