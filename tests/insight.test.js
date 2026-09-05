// 통찰 — 이 게임의 성장 (content/insight.js, 자가진단 ④).
//
// 능력치는 한 판 내내 불변이고 그것이 맞다. 자라야 할 것은 앎이다.
// 그래서 여기서 확인하는 것은 네 가지다.
//
//   1. 단서 둘이 만나면 성립하고, 하나만으로는 안 된다
//   2. 판정에 실제로 붙는다 — 다만 관계있는 태그에만
//   3. 천장이 있다 — 성장을 넣은 대가로 긴장을 잃지 않는다
//   4. 알아채는 순간 화면에 한 번 뜬다

import test from 'node:test';
import assert from 'node:assert/strict';
import { createState } from '../src/engine/state.js';
import { createGM } from '../src/engine/gm.js';
import { buildCheck, MAX_INSIGHT } from '../src/engine/rules.js';
import { INSIGHTS, heldInsights, insightsFor, getInsight } from '../src/content/insight.js';
import { CLUES } from '../src/content/clues.js';
import { EPISODES } from '../src/content/episodes/index.js';
import episode from '../src/content/episodes/luxor.js';

const blank = (clues = []) => {
  const s = createState({ professionId: 'archaeologist', seed: 4 });
  s.episode = 'luxor';
  s.clues = [...clues];
  return s;
};

test('통찰이 참조하는 단서가 전부 실재한다', () => {
  for (const i of INSIGHTS) {
    for (const c of i.need) {
      assert.ok(CLUES[c], `${i.id} 가 없는 단서 ${c} 를 참조한다`);
    }
    assert.ok(i.need.length >= 2, `${i.id} 는 단서 하나로 성립한다 — 그건 조합이 아니다`);
    assert.ok(i.tags.length, `${i.id} 에 붙을 태그가 없다`);
    assert.ok(i.value > 0, `${i.id} 의 값이 0 이다`);
    assert.ok(i.text?.length > 20, `${i.id} 에 설명이 없다`);
  }
});

test('id 와 제목이 겹치지 않는다', () => {
  assert.equal(new Set(INSIGHTS.map((i) => i.id)).size, INSIGHTS.length);
  assert.equal(new Set(INSIGHTS.map((i) => i.title)).size, INSIGHTS.length);
});

test('단서가 다 모여야 성립한다', () => {
  const ins = INSIGHTS[0];
  assert.deepEqual(heldInsights(blank([])), []);
  assert.deepEqual(heldInsights(blank([ins.need[0]])), [], '단서 하나로 성립했다');
  assert.deepEqual(
    heldInsights(blank(ins.need)).map((i) => i.id),
    [ins.id],
  );
});

test('관계있는 태그에만 붙는다', () => {
  const ins = getInsight('black_disc'); // 신비·공포
  const s = blank(ins.need);
  assert.equal(insightsFor(s, ['신비']).length, 1);
  assert.equal(insightsFor(s, ['공포', '해독']).length, 1);
  assert.equal(insightsFor(s, ['등반', '이동']).length, 0, '무관한 판정에 붙었다');
});

test('판정 보정에 실제로 들어간다', () => {
  const ins = getInsight('same_hand'); // 해독·기록 +1
  const chk = { stat: '지식', tags: ['해독'], target: 13 };
  const before = buildCheck(blank([]), chk);
  const after = buildCheck(blank(ins.need), chk);
  assert.equal(after.modifier - before.modifier, ins.value);
  assert.ok(
    after.breakdown.some((b) => b.insight),
    '보정에는 들어갔는데 근거 목록에 안 뜬다 — 왜 그 숫자인지 알 수 없다',
  );
});

test('여러 개가 겹쳐도 천장을 넘지 않는다', () => {
  // 불이익에 천장이 있으면 이익에도 천장이 있어야 한다.
  const chk = { stat: '지식', tags: ['해독', '신비', '기록', '사교', '정보', '공포'], target: 13 };
  const all = blank(INSIGHTS.flatMap((i) => i.need));
  const held = insightsFor(all, chk.tags);
  assert.ok(held.length >= 3, '이 검사가 의미가 있으려면 셋 이상 걸려야 한다');
  assert.ok(
    held.reduce((s, i) => s + i.value, 0) > MAX_INSIGHT,
    '합이 천장보다 작으면 천장을 시험하지 못한다',
  );

  const entry = buildCheck(all, chk).breakdown.find((b) => b.insight);
  assert.equal(entry.value, MAX_INSIGHT, '천장을 넘었다');
});

test('알아채는 순간 한 번만 알려 준다', () => {
  const ins = getInsight('black_disc');
  const state = createState({ professionId: 'archaeologist', seed: 9 });
  const gm = createGM({ state, episode });
  gm.start();

  state.clues.push(...ins.need);

  // 판정이 걸린 선택지는 결과가 나올 때 알린다. 여기서는 곧장 결과가 나오는
  // 선택지를 골라, 통찰이 성립한 그 턴에 뜨는지를 본다.
  const plain = gm.choices().find((c) => !c.isCheck && !c.locked);
  assert.ok(plain, '판정 없는 선택지가 있어야 이 검사가 성립한다');
  const first = gm.act(plain.id);
  const found = first.filter((e) => e.type === 'insight');
  assert.equal(found.length, 1, '통찰이 성립했는데 알려 주지 않았다');
  assert.equal(found[0].id, ins.id);
  assert.equal(found[0].title, ins.title);

  const next = gm.choices().find((c) => !c.isCheck && !c.locked) || gm.choices()[0];
  const second = gm.pending ? gm.roll() : gm.act(next.id);
  assert.equal(second.filter((e) => e.type === 'insight').length, 0, '같은 통찰을 두 번 알렸다');
});

test('단서가 없으면 아무 말도 하지 않는다', () => {
  const state = createState({ professionId: 'archaeologist', seed: 9 });
  const gm = createGM({ state, episode });
  const events = gm.start();
  assert.equal(events.filter((e) => e.type === 'insight').length, 0);
});

// ── 도달 가능성 ────────────────────────────────────────────────
//
// 아무도 못 만드는 조합은 성장이 아니라 장식이다. 조합이 실제로 열리는지는
// 콘텐츠가 그 단서들을 실제로 내주는지에 달려 있다.

test('모든 통찰의 단서를 콘텐츠가 실제로 내준다', () => {
  const granted = new Set();
  const walk = (o) => {
    if (!o || typeof o !== 'object') return;
    if (Array.isArray(o)) return o.forEach(walk);
    for (const [k, v] of Object.entries(o)) {
      if (k === 'clues' && Array.isArray(v)) v.forEach((c) => granted.add(c));
      else walk(v);
    }
  };
  const probe = createState({ professionId: 'archaeologist', seed: 1 });
  for (const ep of Object.values(EPISODES)) {
    for (const s of Object.values(ep.scenes)) {
      walk(s.choices);
      walk(s.ambientCheck);
      walk(s.freeform);
      walk(ep.pressureEvents);
      // onEnter 와 body 는 함수라 훑을 수 없다. effects 를 직접 부르는 것만 본다.
      if (s.onEnter) walk(s.onEnter(structuredClone(probe), 1));
    }
  }
  for (const i of INSIGHTS) {
    for (const c of i.need) {
      assert.ok(granted.has(c), `${i.title} 이(가) 필요로 하는 「${CLUES[c].title}」 을 아무도 안 준다`);
    }
  }
});

test('통찰마다 다른 태그를 덮는다 — 한 직업만 이득 보지 않게', () => {
  // 판정 63개 중 31개가 지식·관찰이었다(자가진단 ⑤).
  // 통찰까지 해독에만 몰리면 고고학자가 또 혼자 자란다.
  const tally = {};
  for (const i of INSIGHTS) for (const t of i.tags) tally[t] = (tally[t] || 0) + 1;
  assert.ok(Object.keys(tally).length >= 6, `태그가 ${Object.keys(tally).length}종뿐이다`);
  const worst = Math.max(...Object.values(tally));
  assert.ok(worst <= 2, `한 태그(${worst}개)에 통찰이 몰려 있다`);
});
