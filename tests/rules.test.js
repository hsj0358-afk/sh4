import { resolve } from '../src/engine/dice.js';
import { itemMattered } from '../src/engine/gm.js';
import test from 'node:test';
import assert from 'node:assert/strict';
import { createState, applyEffects } from '../src/engine/state.js';
import { hasLight, buildCheck, difficultyLabel } from '../src/engine/rules.js';
import { companionAssist } from '../src/content/companions.js';

const scholar = () => createState({ name: '몰리', professionId: 'archaeologist', seed: 2 });

test('능력치가 보정에 그대로 들어간다', () => {
  const s = scholar();
  const b = buildCheck(s, { stat: '지식', tags: [], target: 12 });
  assert.equal(b.breakdown[0].label, '지식');
  assert.equal(b.breakdown[0].value, 5);
});

test('직업 태그가 걸리면 전문 보정이 붙는다', () => {
  const s = scholar();
  const withPerk = buildCheck(s, { stat: '지식', tags: ['해독'], target: 12 });
  const without = buildCheck(s, { stat: '지식', tags: ['전투'], target: 12 });
  assert.ok(withPerk.modifier >= without.modifier + 2);
  assert.ok(withPerk.breakdown.some((x) => x.label.includes('전문')));
});

test('장비는 가장 잘 맞는 하나만 적용된다', () => {
  const s = scholar();
  applyEffects(s, { items: ['탁본 도구'] }); // 해독 +2, 확대경도 해독 +2
  const b = buildCheck(s, { stat: '지식', tags: ['해독'], target: 12 });
  const itemChips = b.breakdown.filter((x) => x.item);
  assert.equal(itemChips.length, 1);
});

test('사용 횟수가 떨어진 장비는 보정을 주지 않는다', () => {
  const s = scholar();
  applyEffects(s, { items: ['횃불'] });
  const before = buildCheck(s, { stat: '관찰', tags: ['암흑'], target: 12 }).modifier;
  applyEffects(s, { spend: { 횃불: 6 } });
  const after = buildCheck(s, { stat: '관찰', tags: ['암흑'], target: 12 }).modifier;
  assert.equal(before - after, 2);
});

test('동료는 신뢰도가 낮으면 덜 돕는다', () => {
  const s = scholar();
  applyEffects(s, { companions: ['nadia'] });
  const normal = companionAssist(s.companions.nadia, ['사교']);
  applyEffects(s, { companion: { id: 'nadia', trust: -2 } });
  const distrust = companionAssist(s.companions.nadia, ['사교']);
  assert.equal(normal, 2);
  assert.equal(distrust, 1);
});

test('이탈한 동료는 보정을 주지 않는다', () => {
  const s = scholar();
  applyEffects(s, { companions: ['finch'] });
  applyEffects(s, { companion: { id: 'finch', present: false } });
  assert.equal(companionAssist(s.companions.finch, ['완력']), 0);
});

test('위험도는 능력이 아니라 목표값을 올린다', () => {
  const s = scholar();
  const calm = buildCheck(s, { stat: '관찰', tags: [], target: 12 });
  applyEffects(s, { danger: 14 });
  const dire = buildCheck(s, { stat: '관찰', tags: [], target: 12 });
  assert.equal(calm.target, 12);
  assert.equal(dire.target, 14);
  assert.equal(calm.modifier, dire.modifier);
});

test('부상과 공황은 보정을 깎는다', () => {
  const s = scholar();
  const healthy = buildCheck(s, { stat: '관찰', tags: [], target: 12 }).modifier;
  applyEffects(s, { hp: -(s.maxHp - 1), san: -(s.maxSan - 1) });
  const wrecked = buildCheck(s, { stat: '관찰', tags: [], target: 12 }).modifier;
  assert.equal(healthy - wrecked, 4);
});

test('난이도 표시', () => {
  assert.equal(difficultyLabel(8), '쉬움');
  assert.equal(difficultyLabel(12), '보통');
  assert.equal(difficultyLabel(15), '어려움');
  assert.equal(difficultyLabel(19), '지극히 어려움');
});

// ── 장비는 결과를 바꿨을 때만 닳는다 ─────────────────────────────
//
// 실제 플레이에서 걸린 것. 목표값 11 짜리 잡담 판정에 보정이 +12 였는데도
// 한 장뿐인 「위조 소개장」이 통째로 소모됐다. 있으나 없으나 결과가 같았는데.

test('없어도 성공했을 판정에서는 장비가 닳지 않는다', () => {
  const built = {
    breakdown: [{ label: '설득', value: 5 }, { label: '위조 소개장', value: 3, item: '위조 소개장' }],
  };
  const result = resolve(18, 8, 11); // 18+8=26, 3을 빼도 23 ≥ 11
  assert.equal(itemMattered(built, result), false);
});

test('장비가 결과 구간을 올렸으면 닳는다', () => {
  const built = { breakdown: [{ label: '확대경', value: 3, item: '확대경' }] };
  // 10+3=13 성공 / 장비를 빼면 10, 목표 13 에 3 모자라 부분 성공
  const result = resolve(10, 3, 13);
  assert.equal(result.outcome, 'success');
  assert.equal(itemMattered(built, result), true);
});

test('장비를 빼도 결과가 같으면 닳지 않는다 — 실패해도 마찬가지', () => {
  const built = { breakdown: [{ label: '확대경', value: 2, item: '확대경' }] };
  const result = resolve(2, 2, 18); // 4 든 2 든 실패
  assert.equal(itemMattered(built, result), false);
});

test('보정을 준 장비가 없으면 닳을 것도 없다', () => {
  assert.equal(itemMattered({ breakdown: [{ label: '설득', value: 4 }] }, resolve(10, 4, 12)), false);
});

// ── 빛 ──────────────────────────────────────────────────────────
//
// 유적 안의 서술은 전부 램프가 있다는 전제로 쓰여 있다. 그것이 맞다 —
// 아무도 빛 없이 무덤에 들어가지 않는다. 규칙에 그 전제가 없어서
// 성냥 한 개비로 쐐기문자를 읽는 사람이 나왔다.

test('빛을 내는 물건을 알아본다', () => {
  assert.equal(hasLight({ inventory: [{ name: '횃불', uses: 3 }] }), true);
  assert.equal(hasLight({ inventory: [{ name: '역청 램프', uses: 8 }] }), true);
  assert.equal(hasLight({ inventory: [{ name: '동행의 등불', uses: 1 }] }), true);
  assert.equal(hasLight({ inventory: [{ name: '나침반', uses: null }] }), false);
  assert.equal(hasLight({ inventory: [{ name: '횃불', uses: 0 }] }), false, '다 쓴 횃불');
  assert.equal(hasLight({ inventory: [] }), false);
});

test('어두운 곳에서 빛이 없으면 판정이 어려워진다', () => {
  const state = createState({ professionId: 'journalist', seed: 3 });
  state.inventory = state.inventory.filter((i) => i.name !== '횃불');

  const lit = buildCheck(state, { stat: '관찰', target: 12 }, { dark: false });
  const dark = buildCheck(state, { stat: '관찰', target: 12 }, { dark: true });
  assert.equal(dark.modifier, lit.modifier - 2);
  assert.ok(dark.breakdown.some((b) => b.label === '빛이 없다'), '왜 어려운지 적히지 않았다');
});

test('빛을 들고 있으면 어두운 곳에서도 대가가 없다', () => {
  const state = createState({ professionId: 'journalist', seed: 3 });
  state.inventory.push({ name: '횃불', uses: 6 });
  const dark = buildCheck(state, { stat: '관찰', target: 12 }, { dark: true });
  assert.ok(!dark.breakdown.some((b) => b.label === '빛이 없다'));
});

test('밝은 곳에서는 빛을 따지지 않는다', () => {
  const state = createState({ professionId: 'journalist', seed: 3 });
  state.inventory = [];
  const day = buildCheck(state, { stat: '관찰', target: 12 });
  assert.ok(!day.breakdown.some((b) => b.label === '빛이 없다'));
});
