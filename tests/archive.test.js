// 회차 계승 — 한 판이 끝나도 무엇이 남는가 (기획서 18절).

import test from 'node:test';
import assert from 'node:assert/strict';
import {
  emptyArchive,
  record,
  countRun,
  progress,
  loadArchive,
  saveArchive,
} from '../src/engine/archive.js';
import { createState, applyEffects } from '../src/engine/state.js';

function run(seed = 1) {
  const state = createState({ professionId: 'archaeologist', seed });
  state.episode = 'luxor';
  return state;
}

test('빈 아카이브는 전부 0에서 시작한다', () => {
  const a = emptyArchive();
  assert.equal(a.runs, 0);
  assert.equal(a.finished, 0);
  assert.deepEqual(a.clues, []);
  assert.deepEqual(a.runLog, []);
});

test('본 것이 아카이브에 쌓이고, 처음 본 것만 firsts 로 나온다', () => {
  const state = run();
  applyEffects(state, { clues: ['black_sun'], companions: ['nadia'] });

  const first = record(emptyArchive(), state);
  assert.ok(first.archive.clues.includes('black_sun'));
  assert.ok(first.archive.companions.includes('nadia'));
  assert.deepEqual(first.firsts.clues, ['black_sun']);
  assert.deepEqual(first.firsts.companions, ['nadia']);

  // 같은 것을 다시 기록해도 늘지 않고, 이번엔 '처음'이 아니다.
  const second = record(first.archive, state);
  assert.equal(second.archive.clues.length, first.archive.clues.length);
  assert.deepEqual(second.firsts.clues, []);
  assert.deepEqual(second.firsts.companions, []);
});

test('회차 카운터와 완주 카운터는 다른 것을 센다', () => {
  let a = countRun(emptyArchive());
  assert.equal(a.runs, 1);

  const died = run();
  died.ended = { type: 'death', title: '기록은 여기서 끊긴다' };
  a = record(a, died, { ended: true, completed: false }).archive;
  assert.equal(a.finished, 0, '죽은 회차가 완주로 세어졌다');
  assert.equal(a.runLog.length, 1, '죽은 회차도 로그북에는 남아야 한다');
  assert.equal(a.runLog[0].outcome, 'death');

  a = countRun(a);
  const won = run(2);
  won.ended = { type: 'finale', ending: 'sealed', title: '여덟 번째 문은 닫힌 채로 남았다' };
  a = record(a, won, { ended: true, completed: true }).archive;
  assert.equal(a.finished, 1);
  assert.equal(a.runs, 2);
  assert.deepEqual(a.endings, ['sealed']);
  assert.equal(a.runLog[0].n, 2, '최근 회차가 로그북 맨 위에 온다');
});

test('중간에 여러 번 기록해도 카운터는 넘긴 만큼만 오른다', () => {
  const state = run();
  let a = emptyArchive();
  a = record(a, state).archive;
  a = record(a, state).archive;
  a = record(a, state).archive;
  assert.equal(a.finished, 0);
  assert.equal(a.runLog.length, 0);
});

test('최다 단서는 회차를 가로질러 갱신된다', () => {
  const many = run();
  applyEffects(many, { clues: ['black_sun', 'first_civilization', 'third_record'] });
  let a = record(emptyArchive(), many).archive;
  assert.equal(a.bestClueCount, 3);

  const few = run(3);
  applyEffects(few, { clues: ['black_sun'] });
  a = record(a, few).archive;
  assert.equal(a.bestClueCount, 3, '더 적은 회차가 기록을 깎았다');
});

test('조우는 encountered: 플래그로 되짚는다', () => {
  const state = run();
  state.flags['encountered:crane_corridor'] = true;
  state.flags['combatDone:some_scene'] = true; // 장면 플래그는 조우가 아니다
  const a = record(emptyArchive(), state).archive;
  assert.deepEqual(a.encounters, ['crane_corridor']);
});

test('진행률은 백분율로 나온다', () => {
  const a = { ...emptyArchive(), clues: ['a', 'b'], endings: ['sealed'] };
  const p = progress(a, { clues: 4, endings: 5, items: 0, companions: 0, encounters: 0, professions: 0 });
  assert.deepEqual(p.clues, { have: 2, all: 4, pct: 50 });
  assert.equal(p.endings.pct, 20);
  assert.equal(p.items.pct, 0, '분모가 0이면 0으로 나눈다');
});

test('저장소가 없는 환경에서도 터지지 않는다', () => {
  // 노드에는 localStorage 가 없다. 조용히 빈 아카이브로 떨어져야 한다.
  assert.deepEqual(loadArchive(), emptyArchive());
  assert.equal(saveArchive(emptyArchive()), false);
});
