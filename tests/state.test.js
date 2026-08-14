import test from 'node:test';
import assert from 'node:assert/strict';
import {
  createState,
  applyEffects,
  conditionPenalty,
  dangerPressure,
  hasItem,
  findItem,
  formatClock,
  MAX_DANGER,
} from '../src/engine/state.js';

const fresh = () => createState({ name: '몰리', professionId: 'archaeologist', seed: 1 });

test('캐릭터 생성 시 직업 능력치와 장비를 물려받는다', () => {
  const s = fresh();
  assert.equal(s.char.profession, '고고학자');
  assert.equal(s.char.stats['지식'], 5);
  assert.ok(hasItem(s, '확대경'));
  assert.equal(s.hp, s.maxHp);
});

test('체력과 정신력은 0과 최대치 사이로 묶인다', () => {
  const s = fresh();
  applyEffects(s, { hp: -999 });
  assert.equal(s.hp, 0);
  applyEffects(s, { hp: 999 });
  assert.equal(s.hp, s.maxHp);
});

test('위험도는 0~10 범위를 벗어나지 않는다', () => {
  const s = fresh();
  applyEffects(s, { danger: 99 });
  assert.equal(s.danger, MAX_DANGER);
  applyEffects(s, { danger: -99 });
  assert.equal(s.danger, 0);
});

test('아이템 획득과 소모', () => {
  const s = fresh();
  applyEffects(s, { items: ['횃불'] });
  assert.equal(findItem(s, '횃불').uses, 6);
  applyEffects(s, { spend: { 횃불: 6 } });
  assert.equal(hasItem(s, '횃불'), false);
});

test('중복 획득은 개수를 늘리지 않고 사용 횟수를 보충한다', () => {
  const s = fresh();
  applyEffects(s, { items: ['횃불'] });
  applyEffects(s, { spend: { 횃불: 3 } });
  applyEffects(s, { items: ['횃불'] });
  assert.equal(s.inventory.filter((i) => i.name === '횃불').length, 1);
  assert.equal(findItem(s, '횃불').uses, 9);
});

test('단서는 중복 기록되지 않는다', () => {
  const s = fresh();
  const first = applyEffects(s, { clues: ['black_sun'] });
  const second = applyEffects(s, { clues: ['black_sun'] });
  assert.equal(first.length, 1);
  assert.equal(second.length, 0);
  assert.deepEqual(s.clues, ['black_sun']);
});

test('동료 합류와 관계 변화', () => {
  const s = fresh();
  applyEffects(s, { companions: ['nadia'] });
  assert.equal(s.companions.nadia.name, '나디아 하룬');
  applyEffects(s, { companion: { id: 'nadia', trust: 2, affinity: 1 } });
  assert.equal(s.companions.nadia.trust, 4);
  assert.equal(s.companions.nadia.affinity, 3);
});

test('동료의 체력이 0이 되면 이탈한다', () => {
  const s = fresh();
  applyEffects(s, { companions: ['finch'] });
  applyEffects(s, { companion: { id: 'finch', hp: -99 } });
  assert.equal(s.companions.finch.present, false);
});

test('상태가 나쁘면 판정 페널티가 붙는다', () => {
  const s = fresh();
  assert.equal(conditionPenalty(s).value, 0);
  applyEffects(s, { hp: -(s.maxHp - 1) });
  assert.ok(conditionPenalty(s).value <= -2);
  assert.ok(conditionPenalty(s).reasons.includes('중상'));
});

test('위험도가 높으면 목표값 압박이 생긴다', () => {
  assert.equal(dangerPressure(0), 0);
  assert.equal(dangerPressure(5), 1);
  assert.equal(dangerPressure(9), 2);
});

test('시계는 30분 단위로 흐르고 날짜를 넘긴다', () => {
  assert.equal(formatClock(0).time, '오전 8시');
  assert.equal(formatClock(2).time, '오전 9시');
  const next = formatClock(2 * 24); // 24시간 뒤
  assert.equal(next.date, '1897년 11월 4일');
});

test('알림에는 변화의 방향이 담긴다', () => {
  const s = fresh();
  const notes = applyEffects(s, { hp: -2, danger: 1, items: ['횃불'] });
  assert.ok(notes.some((n) => n.kind === 'bad' && n.text.includes('체력')));
  assert.ok(notes.some((n) => n.kind === 'bad' && n.text.includes('위험도')));
  assert.ok(notes.some((n) => n.kind === 'good' && n.text.includes('횃불')));
});
