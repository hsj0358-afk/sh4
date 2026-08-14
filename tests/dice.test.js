import test from 'node:test';
import assert from 'node:assert/strict';
import { resolve, rollCheck, selectBranch, OUTCOME, PARTIAL_MARGIN } from '../src/engine/dice.js';
import { createRng } from '../src/engine/rng.js';

test('자연 20은 목표값과 무관하게 대성공', () => {
  assert.equal(resolve(20, -5, 30).outcome, OUTCOME.CRIT);
});

test('자연 1은 보정이 아무리 높아도 대실패', () => {
  assert.equal(resolve(1, 20, 5).outcome, OUTCOME.FUMBLE);
});

test('총합이 목표값 이상이면 성공', () => {
  const r = resolve(11, 3, 14);
  assert.equal(r.total, 14);
  assert.equal(r.outcome, OUTCOME.SUCCESS);
  assert.equal(r.ok, true);
});

test('목표값에서 3 이내로 모자라면 부분 성공', () => {
  assert.equal(resolve(10, 0, 13).outcome, OUTCOME.PARTIAL);
  assert.equal(resolve(10, 0, 13 + PARTIAL_MARGIN).outcome, OUTCOME.FAIL);
});

test('그보다 더 모자라면 실패', () => {
  const r = resolve(4, 1, 15);
  assert.equal(r.outcome, OUTCOME.FAIL);
  assert.equal(r.ok, false);
});

test('rollCheck 는 항상 1~20 사이의 눈을 낸다', () => {
  const rng = createRng(12345);
  for (let i = 0; i < 2000; i++) {
    const r = rollCheck(rng, { modifier: 2, target: 12 });
    assert.ok(r.natural >= 1 && r.natural <= 20, `범위 밖: ${r.natural}`);
    assert.equal(r.total, r.natural + 2);
  }
});

test('d20 분포가 균일한 편이다', () => {
  const rng = createRng('lost-world');
  const counts = new Array(21).fill(0);
  const N = 40000;
  for (let i = 0; i < N; i++) counts[rng.int(1, 20)]++;
  const expected = N / 20;
  for (let face = 1; face <= 20; face++) {
    const drift = Math.abs(counts[face] - expected) / expected;
    assert.ok(drift < 0.12, `${face} 눈이 치우침: ${counts[face]}`);
  }
});

test('같은 시드는 같은 결과를 낸다', () => {
  const a = createRng(777);
  const b = createRng(777);
  for (let i = 0; i < 50; i++) assert.equal(a.int(1, 20), b.int(1, 20));
});

test('분기 테이블이 비어 있으면 가장 가까운 구간으로 대체된다', () => {
  const branches = { success: { text: ['성공'] }, fail: { text: ['실패'] } };
  assert.equal(selectBranch(branches, OUTCOME.CRIT).text[0], '성공');
  assert.equal(selectBranch(branches, OUTCOME.FUMBLE).text[0], '실패');
  assert.equal(selectBranch(branches, OUTCOME.PARTIAL).text[0], '성공');
  assert.equal(selectBranch(null, OUTCOME.SUCCESS), null);
});
