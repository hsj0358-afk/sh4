import test from 'node:test';
import assert from 'node:assert/strict';
import { interpret, detectVerb, hallucination } from '../src/engine/freeform.js';
import { createState, applyEffects } from '../src/engine/state.js';
import { getItem } from '../src/content/items.js';
import { createRng } from '../src/engine/rng.js';
import episode from '../src/content/episodes/luxor.js';

const ctx = (state, sceneId = 'arrival') => ({
  state,
  scene: episode.scenes[sceneId],
  getItemDef: getItem,
  clueTitles: episode.clueTitles,
});

const fresh = () => createState({ professionId: 'explorer', seed: 5 });

test('동사를 알아본다', () => {
  assert.equal(detectVerb('벽화를 자세히 살펴본다'), '조사');
  assert.equal(detectVerb('나디아에게 묻는다'), '대화');
  assert.equal(detectVerb('벽을 힘껏 민다'), '완력');
  assert.equal(detectVerb('여기서 잠깐 쉰다'), '휴식');
  assert.equal(detectVerb('ㅁㄴㅇㄹ'), null);
});

test('선택지를 말로 부르면 그 선택지로 연결된다', () => {
  const a = interpret('시장에 들러본다', ctx(fresh()));
  assert.equal(a.kind, 'choice');
  assert.equal(a.choice.id, 'go_market');
});

test('장면 고유 해석기가 선택지보다 우선한다', () => {
  const a = interpret('강물을 본다', ctx(fresh()));
  assert.equal(a.kind, 'narration');
  assert.match(a.text.join(' '), /나일/);
});

test('동료 이름을 부르면 관계 장면이 열린다', () => {
  const s = fresh();
  applyEffects(s, { companions: ['nadia'] });
  // 갱도 장면에는 이름을 가로챌 선택지가 없다 — 동료 대화로 흘러야 한다.
  const a = interpret('나디아에게 고맙다고 말한다', ctx(s, 'shaft'));
  assert.equal(a.effects.companion.id, 'nadia');
  assert.equal(a.effects.companion.affinity, 1);
});

test('소지품을 쓰면 실제로 소모된다', () => {
  const s = fresh();
  applyEffects(s, { items: ['의료 키트'] });
  const a = interpret('의료 키트를 쓴다', ctx(s));
  assert.ok(a.effects.hp > 0);
  assert.equal(a.effects.spend['의료 키트'], 1);
});

test('가지고 있지 않은 물건은 쓸 수 없다', () => {
  const a = interpret('의료 키트를 쓴다', ctx(fresh()));
  assert.notEqual(a.kind, 'narration');
  assert.equal(a.kind, 'unknown');
});

test('휴식은 시간을 쓰고, 위험한 곳에서는 대가가 다르다', () => {
  const calm = interpret('잠시 쉰다', ctx(fresh()));
  assert.ok(calm.effects.time >= 2);
  assert.equal(calm.effects.danger, 0);

  const s = fresh();
  applyEffects(s, { danger: 7 });
  const risky = interpret('잠시 쉰다', ctx(s));
  assert.equal(risky.effects.danger, 1);
});

test('소리치면 위험도가 오른다', () => {
  const a = interpret('큰 소리를 지른다', ctx(fresh()));
  assert.equal(a.effects.danger, 2);
});

test('수첩을 열면 지금까지의 단서를 읽어준다', () => {
  const s = fresh();
  applyEffects(s, { clues: ['black_sun'] });
  const a = interpret('수첩을 펴본다', ctx(s));
  assert.match(a.text.join(' '), /검은 태양/);
});

test('막연한 조사는 장면의 기본 판정으로 넘어간다', () => {
  const a = interpret('주변을 살펴본다', ctx(fresh()));
  assert.equal(a.kind, 'check');
  assert.equal(a.check.stat, '관찰');
});

test('불가능한 행동은 거절이 아니라 서술로 처리된다', () => {
  const a = interpret('전화를 건다', ctx(fresh()));
  assert.equal(a.kind, 'unknown');
  assert.ok(a.text.length >= 2);
  assert.ok(!a.text.join(' ').includes('할 수 없습니다'));
});

test('빈 입력도 깨지지 않는다', () => {
  const a = interpret('   ', ctx(fresh()));
  assert.equal(a.kind, 'unknown');
});

test('정신력이 충분하면 환각은 일어나지 않는다', () => {
  const s = fresh();
  const rng = createRng(1);
  for (let i = 0; i < 50; i++) assert.equal(hallucination(s, rng), null);
});

test('정신력이 바닥나면 가끔 오독이 끼어든다', () => {
  const s = fresh();
  applyEffects(s, { san: -(s.maxSan - 1) });
  const rng = createRng(1);
  let count = 0;
  for (let i = 0; i < 200; i++) if (hallucination(s, rng)) count++;
  assert.ok(count > 10, `환각이 너무 드물다: ${count}`);
  assert.ok(count < 190, `환각이 너무 잦다: ${count}`);
});
