// 전투 — 규칙과 조우 콘텐츠.

import test from 'node:test';
import assert from 'node:assert/strict';
import {
  survivable,
  startCombat,
  combatActions,
  buildAction,
  applyAction,
  applyAlly,
  enemyTurn,
  checkExit,
  parleyReady,
  actionNarration,
  ACTIONS,
  EXIT,
  ESCAPE_NEEDED,
} from '../src/engine/combat.js';
import { ENCOUNTERS, getEncounter } from '../src/content/encounters.js';
import { createState, applyEffects } from '../src/engine/state.js';
import { createGM } from '../src/engine/gm.js';
import { EPISODES } from '../src/content/episodes/index.js';

const enc = ENCOUNTERS.crane_corridor;
const fresh = (prof = 'soldier') => createState({ professionId: prof, seed: 3 });

// ── 규칙 ────────────────────────────────────────────────────────

test('전투는 두 개의 시계로 시작한다', () => {
  const c = startCombat(enc);
  assert.equal(c.resolve, enc.resolve);
  assert.equal(c.pressure, 0);
  assert.equal(c.escape, 0);
  assert.equal(c.exit, null);
  assert.equal(c.round, 1);
});

test('공격은 전의를 깎고 압박을 올린다', () => {
  const c = startCombat(enc);
  applyAction(c, enc, 'attack', 'success');
  assert.equal(c.resolve, enc.resolve - 2);
  assert.equal(c.pressure, 1);
});

test('엄폐는 압박을 내리지만 전의는 그대로다', () => {
  const c = startCombat(enc);
  c.pressure = 6;
  applyAction(c, enc, 'cover', 'success');
  assert.equal(c.pressure, 2);
  assert.equal(c.resolve, enc.resolve);
});

test('공격만 반복하면 압박이 먼저 찬다', () => {
  // 이 게임의 전투가 말하려는 것 — 때리기만 해서는 못 나간다.
  const c = startCombat(enc);
  let rounds = 0;
  while (!checkExit(c) && rounds < 20) {
    applyAction(c, enc, 'attack', 'success');
    if (checkExit(c)) break;
    enemyTurn(c, enc);
    rounds++;
  }
  assert.equal(c.exit, EXIT.OVERRUN, '공격만으로 이겨버린다면 엄폐가 의미 없다');
});

test('엄폐를 섞으면 이길 수 있다', () => {
  const c = startCombat(enc);
  let rounds = 0;
  while (!checkExit(c) && rounds < 30) {
    applyAction(c, enc, c.pressure >= 5 ? 'cover' : 'attack', 'success');
    if (checkExit(c)) break;
    enemyTurn(c, enc);
    rounds++;
  }
  assert.equal(c.exit, EXIT.WIN);
});

test('실패한 공격은 맞는 것으로 돌아온다', () => {
  const c = startCombat(enc);
  const { effects } = applyAction(c, enc, 'attack', 'fail');
  assert.ok(effects.hp < 0);
  assert.equal(c.resolve, enc.resolve, '실패했는데 전의가 깎였다');
});

test('협상은 전의가 꺾이기 전에는 끝내지 못한다', () => {
  const c = startCombat(enc);
  assert.equal(parleyReady(c), false);
  applyAction(c, enc, 'parley', 'success');
  assert.equal(c.exit, null, '전의가 남았는데 말로 끝났다');

  c.resolve = 3;
  assert.equal(parleyReady(c), true);
  applyAction(c, enc, 'parley', 'crit');
  assert.equal(c.exit, EXIT.PARLEY);
});

test('협상이 꺾인 전의 앞에서는 쉬워진다', () => {
  const state = fresh();
  const ready = startCombat(enc);
  ready.resolve = 2;
  const notReady = startCombat(enc);

  const a = buildAction(ready, state, enc, 'parley');
  const b = buildAction(notReady, state, enc, 'parley');
  assert.equal(a.check.bonus, 3);
  assert.equal(b.check.bonus, 0);
});

test('도주는 두 번 성공해야 한다', () => {
  const c = startCombat(enc);
  applyAction(c, enc, 'flee', 'success');
  assert.equal(c.escape, 1);
  assert.equal(checkExit(c), null, '한 번에 벗어나면 도주가 너무 싸다');
  applyAction(c, enc, 'flee', 'success');
  assert.equal(checkExit(c), EXIT.ESCAPE);
});

test('대성공 도주는 한 번에 벗어난다', () => {
  const c = startCombat(enc);
  applyAction(c, enc, 'flee', 'crit');
  assert.equal(c.escape, ESCAPE_NEEDED);
  assert.equal(checkExit(c), EXIT.ESCAPE);
});

test('압박이 높으면 도주가 어려워진다', () => {
  const state = fresh();
  const calm = startCombat(enc);
  const cornered = startCombat(enc);
  cornered.pressure = 8;
  assert.equal(buildAction(calm, state, enc, 'flee').check.bonus, 0);
  assert.equal(buildAction(cornered, state, enc, 'flee').check.bonus, -2);
});

test('지형은 한 번뿐이다', () => {
  const state = fresh();
  const c = startCombat(enc);
  assert.ok(combatActions(c, state, enc).some((a) => a.action === 'terrain'));
  applyAction(c, enc, 'terrain', 'success');
  assert.ok(!combatActions(c, state, enc).some((a) => a.action === 'terrain'));
});

test('지형이 통하면 판이 크게 바뀐다', () => {
  const c = startCombat(enc);
  c.pressure = 5;
  applyAction(c, enc, 'terrain', 'success');
  assert.equal(c.resolve, enc.resolve - 4);
  assert.equal(c.pressure, 3);
});

test('동료 지원은 굴리지 않지만 동료가 대신 다친다', () => {
  const state = fresh();
  applyEffects(state, { companions: ['finch'] });
  const c = startCombat(enc);
  c.pressure = 7;

  const { effects, injured } = applyAlly(c, state, 'finch');
  assert.equal(injured, true);
  assert.ok(effects.companion.hp < 0);
  assert.equal(c.resolve, enc.resolve - 2);
  assert.equal(c.pressure, 5);
});

test('동료 지원은 한 사람당 한 번뿐이다', () => {
  const state = fresh();
  applyEffects(state, { companions: ['finch'] });
  const c = startCombat(enc);
  assert.ok(combatActions(c, state, enc).some((a) => a.action === 'ally'));
  applyAlly(c, state, 'finch');
  assert.ok(!combatActions(c, state, enc).some((a) => a.action === 'ally'));
});

test('이탈한 동료에게는 지원을 청할 수 없다', () => {
  const state = fresh();
  applyEffects(state, { companions: ['finch'] });
  applyEffects(state, { companion: { id: 'finch', present: false } });
  const c = startCombat(enc);
  assert.ok(!combatActions(c, state, enc).some((a) => a.action === 'ally'));
});

test('상대의 차례는 압박을 올리고, 높으면 때린다', () => {
  const c = startCombat(enc);
  const quiet = enemyTurn(c, enc);
  assert.equal(quiet.tier, 'low');
  assert.equal(quiet.effects.hp, undefined);

  c.pressure = 7; // 9 → 한계(10)의 90%
  const loud = enemyTurn(c, enc);
  assert.equal(loud.tier, 'high');
  assert.ok(loud.effects.hp < 0);
});

test('언제나 세 가지 이상의 행동이 열려 있다', () => {
  const state = fresh();
  for (const encounter of Object.values(ENCOUNTERS)) {
    const c = startCombat(encounter);
    assert.ok(
      combatActions(c, state, encounter).length >= 3,
      `${encounter.id}: 행동이 부족하다`,
    );
    // 지형을 다 쓴 뒤에도
    c.used.terrain = true;
    assert.ok(
      combatActions(c, state, encounter).length >= 3,
      `${encounter.id}: 지형을 쓰고 나면 행동이 부족하다`,
    );
  }
});

test('제압당하는 것으로는 죽지 않는다', () => {
  // 출구 서술은 "깨어났을 때 가방이 열려 있었다"라고 말한다.
  // 그 직후에 죽으면 게임이 방금 한 말을 스스로 뒤집는다.
  const state = fresh();
  state.hp = 2;
  const safe = survivable({ hp: -4, removeItems: ['별자리 기호판'] }, state);
  assert.equal(safe.hp, -1);
  assert.deepEqual(safe.removeItems, ['별자리 기호판'], '잃는 물건까지 깎이면 안 된다');
});

test('여유가 있으면 제압의 피해는 그대로 들어온다', () => {
  const state = fresh();
  const full = survivable({ hp: -4 }, state);
  assert.equal(full.hp, -4);
});

test('전투에서 제압당해도 탐사는 이어진다', () => {
  for (let seed = 0; seed < 40; seed++) {
    const state = createState({ professionId: 'patron', seed });
    const gm = createGM({ state, episode: EPISODES.luxor });
    gm.start();
    state.hp = 3; // 이미 만신창이인 채로 들어간다
    gm.enterScene('confrontation_fight', []);

    let guard = 0;
    while (state.combat && guard++ < 60) {
      if (gm.pending) gm.roll();
      else {
        const options = gm.choices();
        if (!options.length) break;
        // 일부러 최악의 수 — 계속 공격만 한다
        gm.act(options.find((o) => o.action === 'attack')?.id || options[0].id);
      }
    }
    assert.equal(state.combat, null, `seed ${seed}: 전투가 끝나지 않았다`);
  }
});

// ── 콘텐츠 ──────────────────────────────────────────────────────

test('모든 조우가 네 개의 출구를 전부 갖는다', () => {
  for (const e of Object.values(ENCOUNTERS)) {
    for (const exit of Object.values(EXIT)) {
      const x = e.exits?.[exit];
      assert.ok(x, `${e.id}: '${exit}' 출구 없음`);
      assert.ok(x.text?.length, `${e.id}/${exit}: 서술 없음`);
      assert.ok(x.effects?.goto, `${e.id}/${exit}: 갈 곳이 없다`);
    }
  }
});

test('조우의 출구가 실재하는 장면을 가리킨다', () => {
  const sceneIds = new Set();
  for (const ep of Object.values(EPISODES)) {
    for (const id of Object.keys(ep.scenes)) sceneIds.add(id);
  }
  for (const e of Object.values(ENCOUNTERS)) {
    for (const [exit, x] of Object.entries(e.exits)) {
      assert.ok(sceneIds.has(x.effects.goto), `${e.id}/${exit}: 없는 장면 '${x.effects.goto}'`);
    }
  }
});

test('모든 행동에 세 갈래 서술이 있다', () => {
  for (const e of Object.values(ENCOUNTERS)) {
    for (const key of Object.keys(ACTIONS)) {
      const a = e.actions?.[key];
      assert.ok(a, `${e.id}: '${key}' 서술 없음`);
      for (const tier of ['good', 'mixed', 'bad']) {
        assert.ok(a[tier]?.length, `${e.id}/${key}: '${tier}' 서술 없음`);
      }
    }
  }
});

test('대성공과 대실패는 서술이 한 줄 더 붙는다', () => {
  const good = actionNarration(enc, 'attack', 'success');
  const crit = actionNarration(enc, 'attack', 'crit');
  assert.equal(crit.length, good.length + 1);

  const bad = actionNarration(enc, 'attack', 'fail');
  const fumble = actionNarration(enc, 'attack', 'fumble');
  assert.equal(fumble.length, bad.length + 1);
});

test('조우마다 상대의 차례 서술이 세 단계로 있다', () => {
  for (const e of Object.values(ENCOUNTERS)) {
    for (const tier of ['low', 'mid', 'high']) {
      assert.ok(e.enemyTurn?.[tier]?.length, `${e.id}: '${tier}' 서술 없음`);
    }
  }
});

test('전투 장면이 가리키는 조우가 실재한다', () => {
  for (const ep of Object.values(EPISODES)) {
    for (const [id, scene] of Object.entries(ep.scenes)) {
      if (!scene.combat) continue;
      assert.ok(getEncounter(scene.combat), `${id}: 없는 조우 '${scene.combat}'`);
    }
  }
});

// ── GM 통합 ─────────────────────────────────────────────────────

function combatSession() {
  const state = createState({ professionId: 'soldier', seed: 5 });
  const gm = createGM({ state, episode: EPISODES.luxor });
  gm.start();
  gm.enterScene('confrontation_fight', []);
  return { state, gm };
}

test('전투 장면에 들어가면 전투가 시작된다', () => {
  const { state, gm } = combatSession();
  assert.ok(state.combat, '전투가 시작되지 않았다');
  assert.ok(gm.combat);
  assert.equal(gm.combat.name, '크레인의 사람들');
});

test('전투 중에는 장면 선택지 대신 전투 행동이 나온다', () => {
  const { gm } = combatSession();
  const ids = gm.choices().map((c) => c.id);
  assert.ok(ids.every((id) => id.startsWith('combat:')), ids.join(', '));
  assert.ok(ids.includes('combat:attack'));
  assert.ok(ids.includes('combat:flee'));
});

test('전투 행동은 판정을 요구하고, 굴리면 라운드가 넘어간다', () => {
  const { state, gm } = combatSession();
  const before = state.combat.round;

  const req = gm.act('combat:attack');
  assert.ok(req.some((e) => e.type === 'checkRequest'));
  assert.ok(gm.pending);

  const events = gm.roll();
  assert.ok(events.some((e) => e.type === 'roll'));
  assert.ok(events.some((e) => e.type === 'narration'));
  assert.ok(state.ended || state.combat === null || state.combat.round > before);
});

test('전투가 끝나면 출구의 결과가 적용되고 장면이 옮겨진다', () => {
  const { state, gm } = combatSession();
  state.combat.resolve = 1;
  gm.act('combat:attack');
  // 결과와 무관하게 몇 라운드 안에 끝난다
  for (let i = 0; i < 30 && state.combat; i++) {
    if (gm.pending) gm.roll();
    else if (gm.choices().length) gm.act(gm.choices()[0].id);
    else break;
  }
  assert.equal(state.combat, null, '전투가 끝나지 않았다');
  assert.ok(['finale', 'confrontation_fight'].includes(state.scene) || state.ended);
});

test('전투 중 자유 입력은 소지품 사용만 받는다', () => {
  const { state, gm } = combatSession();
  applyEffects(state, { items: ['의료 키트'], hp: -5 });
  const hp = state.hp;

  const used = gm.freeAct('의료 키트 사용');
  assert.ok(state.hp > hp, '전투 중에 약을 못 쓴다');

  const refused = gm.freeAct('벽화를 감상한다');
  const text = refused
    .filter((e) => e.type === 'narration')
    .flatMap((e) => e.text)
    .join(' ');
  assert.match(text, /시간이 없다/);
});

test('어떤 시드로도 전투는 반드시 끝난다', () => {
  for (let seed = 0; seed < 60; seed++) {
    const state = createState({ professionId: 'journalist', seed });
    const gm = createGM({ state, episode: EPISODES.luxor });
    gm.start();
    gm.enterScene('confrontation_fight', []);

    let guard = 0;
    while (state.combat && guard < 60) {
      guard++;
      if (gm.pending) gm.roll();
      else {
        const options = gm.choices();
        if (!options.length) break;
        gm.act(options[guard % options.length].id);
      }
    }
    assert.equal(state.combat, null, `seed ${seed}: 전투가 끝나지 않았다`);
  }
});

// ── 부르는 때가 곧 판단이다 ──────────────────────────────────────
//
// 지원 요청이 늘 신뢰 +1 이었을 때는, 동료를 다치게 하면서 신뢰를 버는
// 공짜 수단이었다. 이제 언제 부르느냐가 그 사람이 당신을 어떻게 보는지를 정한다.

test('압박이 낮을 때 부르면 신뢰가 오른다', () => {
  const state = fresh();
  applyEffects(state, { companions: ['finch'] });
  const c = startCombat(enc);
  c.pressure = 2;

  const { effects, injured } = applyAlly(c, state, 'finch');
  assert.equal(injured, false);
  assert.equal(effects.companion.trust, 1);
  assert.equal(effects.companion.hp, -1);
});

test('무너지는 판에 부르면 방패로 쓴 것이 된다', () => {
  const state = fresh();
  applyEffects(state, { companions: ['finch'] });
  const c = startCombat(enc);
  c.pressure = 8;

  const { effects, injured } = applyAlly(c, state, 'finch');
  assert.equal(injured, true);
  assert.equal(effects.companion.trust, -1, '방패로 쓰고도 신뢰를 벌었다');
  assert.ok(effects.companion.hp <= -3);
});
