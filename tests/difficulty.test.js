import test from 'node:test';
import assert from 'node:assert/strict';
import { DIFFICULTIES, getDifficulty, scaleDamage } from '../src/content/difficulty.js';
import { createState, applyEffects } from '../src/engine/state.js';
import { buildCheck } from '../src/engine/rules.js';

const make = (difficulty) =>
  createState({ professionId: 'soldier', difficulty, seed: 11 });

test('난이도를 지정하지 않으면 표준이다', () => {
  assert.equal(createState({ professionId: 'soldier' }).difficulty, 'standard');
  assert.equal(getDifficulty('없는난이도').id, 'standard');
});

test('난이도가 시작 체력과 정신력을 조정한다', () => {
  const gentle = make('gentle');
  const standard = make('standard');
  const harsh = make('harsh');
  assert.equal(gentle.maxHp - standard.maxHp, 3);
  assert.equal(harsh.maxHp - standard.maxHp, -2);
  assert.equal(gentle.maxSan - standard.maxSan, 3);
  assert.equal(harsh.maxSan - standard.maxSan, -2);
  assert.equal(standard.hp, standard.maxHp);
});

test('난이도가 목표값을 옮긴다', () => {
  const check = { stat: '관찰', tags: [], target: 12 };
  assert.equal(buildCheck(make('gentle'), check).target, 11);
  assert.equal(buildCheck(make('standard'), check).target, 12);
  assert.equal(buildCheck(make('harsh'), check).target, 13);
});

test('난이도 보정은 목표값에만 걸리고 보정치는 건드리지 않는다', () => {
  const check = { stat: '관찰', tags: [], target: 12 };
  const a = buildCheck(make('gentle'), check);
  const b = buildCheck(make('harsh'), check);
  assert.equal(a.modifier, b.modifier);
});

test('난이도와 위험도 압박이 함께 적용된다', () => {
  const s = make('harsh');
  applyEffects(s, { danger: 9 });
  const built = buildCheck(s, { stat: '관찰', tags: [], target: 12 });
  assert.equal(built.pressure, 2);
  assert.equal(built.difficultyShift, 1);
  assert.equal(built.target, 15);
});

test('피해량에 난이도 배율이 걸린다', () => {
  const gentle = make('gentle');
  const harsh = make('harsh');
  applyEffects(gentle, { hp: -4 });
  applyEffects(harsh, { hp: -4 });
  assert.equal(gentle.maxHp - gentle.hp, 3); // -4 × 0.7  = -2.8 → -3
  assert.equal(harsh.maxHp - harsh.hp, 5); //  -4 × 1.35 = -5.4 → -5
});

test('회복량에는 배율이 걸리지 않는다', () => {
  const s = make('gentle');
  applyEffects(s, { hp: -8 });
  const before = s.hp;
  applyEffects(s, { hp: 3 });
  assert.equal(s.hp - before, 3);
});

test('아무리 관대해도 피해가 0이 되지는 않는다', () => {
  assert.equal(scaleDamage(-1, 'gentle'), -1);
  assert.equal(scaleDamage(-1, 'harsh'), -1);
  assert.equal(scaleDamage(0, 'gentle'), 0);
  assert.equal(scaleDamage(5, 'harsh'), 5);
});

test('난이도는 세이브에 남는다', () => {
  const s = make('harsh');
  const restored = JSON.parse(JSON.stringify(s));
  assert.equal(restored.difficulty, 'harsh');
  assert.equal(buildCheck(restored, { stat: '관찰', tags: [], target: 12 }).target, 13);
});

test('모든 난이도가 이름과 설명을 갖는다', () => {
  for (const d of Object.values(DIFFICULTIES)) {
    assert.ok(d.name && d.tagline && d.desc, `${d.id}: 설명 누락`);
    assert.equal(typeof d.targetShift, 'number');
    assert.ok(d.damageScale > 0);
  }
});
