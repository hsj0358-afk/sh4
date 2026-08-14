import test from 'node:test';
import assert from 'node:assert/strict';
import { createState, applyEffects } from '../src/engine/state.js';
import { createGM, meets } from '../src/engine/gm.js';
import episode from '../src/content/episodes/luxor.js';

function session(opts = {}) {
  const state = createState({
    name: '몰리',
    professionId: opts.professionId || 'archaeologist',
    seed: opts.seed ?? 42,
  });
  const gm = createGM({ state, episode });
  gm.start();
  return { state, gm };
}

const types = (events) => events.map((e) => e.type);

test('세션을 시작하면 장면 머리말과 서술이 나온다', () => {
  const state = createState({ professionId: 'explorer', seed: 7 });
  const gm = createGM({ state, episode });
  const events = gm.start();
  assert.equal(events[0].type, 'scene');
  assert.ok(events.some((e) => e.type === 'narration'));
  assert.equal(state.scene, episode.start);
});

test('도착 장면에서 나디아가 합류한다', () => {
  const { state } = session();
  assert.ok(state.companions.nadia);
});

test('판정 선택지는 주사위를 요구하고, 굴리기 전까지 다른 행동을 막는다', () => {
  const { gm } = session();
  const events = gm.act('ask_nadia');
  assert.ok(types(events).includes('checkRequest'));
  assert.ok(gm.pending);
  assert.deepEqual(gm.choices(), []);
  assert.deepEqual(gm.act('inspect_dock'), []);
});

test('주사위를 굴리면 결과와 서사 분기가 이어진다', () => {
  const { state, gm } = session();
  gm.act('ask_nadia');
  const events = gm.roll();
  const roll = events.find((e) => e.type === 'roll');
  assert.ok(roll);
  assert.ok(roll.result.natural >= 1 && roll.result.natural <= 20);
  assert.ok(events.some((e) => e.type === 'narration'));
  assert.equal(gm.pending, null);
  assert.equal(state.rolls.length, 1);
});

test('다섯 구간 어느 결과가 나와도 서술은 반드시 이어진다', () => {
  const seen = new Set();
  // 보정이 낮은 직업으로 굴려야 다섯 구간이 고르게 나온다.
  for (let seed = 0; seed < 800 && seen.size < 5; seed++) {
    const state = createState({ professionId: 'soldier', seed });
    const gm = createGM({ state, episode });
    gm.start();
    gm.act('inspect_dock');
    const events = gm.roll();
    const roll = events.find((e) => e.type === 'roll');
    seen.add(roll.result.outcome);
    assert.ok(
      events.some((e) => e.type === 'narration'),
      `${roll.result.outcome} 결과에 서술이 없다`,
    );
  }
  assert.equal(seen.size, 5, `관측된 구간: ${[...seen].join(', ')}`);
});

test('goto 가 있으면 장면이 바뀐다', () => {
  const { state, gm } = session();
  gm.act('go_market');
  assert.equal(state.scene, 'market');
  assert.equal(gm.scene().location, '룩소르 · 옛 시장 골목');
});

test('once 선택지는 한 번 쓰면 사라진다', () => {
  const { gm } = session();
  assert.ok(gm.choices().some((c) => c.id === 'ask_nadia'));
  gm.act('ask_nadia');
  gm.roll();
  assert.ok(!gm.choices().some((c) => c.id === 'ask_nadia'));
});

test('조건을 만족하지 못하는 선택지는 목록에 없다', () => {
  const { state, gm } = session();
  gm.act('go_valley');
  assert.equal(state.scene, 'camp');
  assert.ok(!gm.choices().some((c) => c.id === 'enter_temple'));
  applyEffects(state, { flags: { foundEntrance: true } });
  assert.ok(gm.choices().some((c) => c.id === 'enter_temple'));
});

test('meets 는 부족한 조건의 이유를 알려준다', () => {
  const state = createState({ professionId: 'soldier', seed: 3 });
  assert.equal(meets(state, { items: ['별자리 기호판'] }).ok, false);
  assert.equal(meets(state, { tags: ['전투'] }).ok, true);
  assert.equal(meets(state, { tags: ['신비'] }).ok, false);
  assert.match(meets(state, { tags: ['신비'] }).reason, /신비/);
});

test('체력이 0이 되면 세션이 종료된다', () => {
  const { state, gm } = session();
  applyEffects(state, { hp: -state.hp });
  const events = gm.act('go_market');
  assert.ok(state.ended);
  assert.equal(state.ended.type, 'death');
  assert.ok(events.some((e) => e.type === 'end'));
  assert.deepEqual(gm.choices(), []);
});

test('정신력이 0이 되면 다른 결말로 끝난다', () => {
  const { state, gm } = session();
  applyEffects(state, { san: -state.san });
  gm.act('go_market');
  assert.equal(state.ended.type, 'broken');
});

test('자유 입력이 선택지로 연결된다', () => {
  const { gm } = session();
  const events = gm.freeAct('시장에 가 본다');
  assert.equal(events[0].type, 'player');
  assert.ok(types(events).includes('scene'));
});

test('해석되지 않는 입력도 세계관 안에서 대답한다', () => {
  const { gm } = session();
  const events = gm.freeAct('우주선을 부른다');
  const narration = events.find((e) => e.type === 'narration');
  assert.ok(narration);
  assert.ok(narration.text.join(' ').length > 10);
});

test('판정 중에는 자유 입력이 무시된다', () => {
  const { gm } = session();
  gm.act('ask_nadia');
  assert.deepEqual(gm.freeAct('도망친다'), []);
});

test('세이브 상태만으로 세션을 복원할 수 있다', () => {
  const { state, gm } = session();
  gm.act('go_market');
  gm.act('buy_supplies');
  const snapshot = JSON.parse(JSON.stringify(state));

  const restored = createGM({ state: snapshot, episode });
  assert.equal(restored.scene().id, 'market');
  assert.ok(restored.choices().length > 0);
  assert.ok(snapshot.inventory.some((i) => i.name === '횃불'));
});

test('위험도가 높아도 목표값만 오르고 판정은 계속 가능하다', () => {
  const { state, gm } = session();
  applyEffects(state, { danger: 10 });
  const events = gm.act('inspect_dock');
  const req = events.find((e) => e.type === 'checkRequest');
  assert.equal(req.pressure, 2);
  assert.ok(req.target > 12);
});
