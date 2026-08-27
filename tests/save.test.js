// 저장 칸.
//
// 칸이 셋이라는 것 자체보다, 칸을 잘못 골랐을 때 한 시간짜리 판이 사라지지
// 않는다는 것이 요점이다. 그래서 여기서 확인하는 것은 세 가지다 —
// 목록이 사실을 말하는가, 빈 칸을 먼저 쓰는가, 옛 세이브를 잃지 않는가.

import test from 'node:test';
import assert from 'node:assert/strict';
import { createState } from '../src/engine/state.js';

// 노드에는 localStorage 가 없다. 저장소를 흉내 내고 나서 모듈을 불러온다 —
// save.js 는 부를 때마다 전역을 다시 보므로 순서만 지키면 된다.
const store = new Map();
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
};

const {
  SLOTS,
  saveGame,
  loadGame,
  clearGame,
  hasAnySave,
  firstEmptySlot,
  slotList,
  migrateLegacy,
} = await import('../src/engine/save.js');

const reset = () => store.clear();

function run(name = '에드워드 몰리') {
  const s = createState({ name, professionId: 'archaeologist', seed: 7 });
  s.episode = 'luxor';
  return s;
}

test('칸이 셋이고, 처음에는 전부 비어 있다', () => {
  reset();
  assert.equal(SLOTS, 3);
  const list = slotList();
  assert.equal(list.length, 3);
  assert.ok(list.every((s) => s.empty));
  assert.equal(hasAnySave(), false);
  assert.equal(firstEmptySlot(), 0);
});

test('한 칸에 저장해도 다른 칸은 건드리지 않는다', () => {
  reset();
  saveGame(run('몰리'), 1);
  const list = slotList();
  assert.equal(list[0].empty, true);
  assert.equal(list[1].empty, false);
  assert.equal(list[2].empty, true);
  assert.equal(list[1].name, '몰리');
  assert.equal(hasAnySave(), true);
  // 빈 칸을 먼저 준다. 차 있는 칸을 넘겨주면 남의 판을 덮는다.
  assert.equal(firstEmptySlot(), 0);
});

test('목록이 판의 사실을 그대로 말한다', () => {
  reset();
  const s = run('나의 탐사자');
  s.clues = ['black_sun', 'not_first'];
  s.hp = 9;
  saveGame(s, 0);
  const info = slotList()[0];
  assert.equal(info.name, '나의 탐사자');
  assert.equal(info.profession, s.char.profession);
  assert.equal(info.clues, 2);
  assert.equal(info.hp, 9);
  assert.equal(info.maxHp, s.maxHp);
  assert.equal(info.episode, 'luxor');
  assert.ok(info.savedAt > 0);
});

test('전부 차면 빈 칸이 없다고 말한다', () => {
  reset();
  for (let i = 0; i < SLOTS; i++) saveGame(run(`탐사자${i}`), i);
  assert.equal(firstEmptySlot(), -1);
  assert.ok(slotList().every((s) => !s.empty));
});

test('덮어쓰면 그 칸만 바뀐다', () => {
  reset();
  saveGame(run('먼저'), 0);
  saveGame(run('나중'), 0);
  saveGame(run('옆 칸'), 1);
  assert.equal(slotList()[0].name, '나중');
  assert.equal(slotList()[1].name, '옆 칸');
});

test('지우면 그 칸만 비고, 되읽으면 없다', () => {
  reset();
  saveGame(run('가'), 0);
  saveGame(run('나'), 2);
  clearGame(0);
  assert.equal(loadGame(0), null);
  assert.equal(slotList()[0].empty, true);
  assert.equal(slotList()[2].name, '나');
});

test('저장한 상태가 그대로 돌아온다', () => {
  reset();
  const s = run();
  s.tick = 42;
  saveGame(s, 1);
  const back = loadGame(1);
  assert.equal(back.state.tick, 42);
  assert.equal(back.state.char.name, s.char.name);
  assert.deepEqual(back.state.inventory, s.inventory);
});

test('칸이 하나뿐이던 시절의 세이브를 1번으로 옮긴다', () => {
  reset();
  // 옛 키에 직접 적어 둔다 — 업데이트 직전의 상태를 흉내 낸다.
  store.set(
    'lostworldmap.save.v1',
    JSON.stringify({ savedAt: Date.now(), state: run('옛 판') }),
  );
  assert.equal(migrateLegacy(), true);
  assert.equal(slotList()[0].name, '옛 판');
  assert.equal(store.has('lostworldmap.save.v1'), false);
  // 두 번 불러도 문제가 없어야 한다. 앱을 켤 때마다 부르기 때문이다.
  assert.equal(migrateLegacy(), false);
  assert.equal(slotList()[0].name, '옛 판');
});

test('1번이 이미 차 있으면 옛 세이브가 그것을 덮지 않는다', () => {
  reset();
  saveGame(run('지금 판'), 0);
  store.set(
    'lostworldmap.save.v1',
    JSON.stringify({ savedAt: Date.now(), state: run('옛 판') }),
  );
  migrateLegacy();
  assert.equal(slotList()[0].name, '지금 판');
});

test('저장소가 망가져 있어도 넘어간다', () => {
  reset();
  store.set('lostworldmap.slot.v1.0', '{ 이건 JSON 이 아니다');
  assert.equal(loadGame(0), null);
  assert.equal(slotList()[0].empty, true);
});
