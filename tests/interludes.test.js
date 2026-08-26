// 막간 — 장과 장 사이의 항로 선택 (기획서 18절 '분기형 캠페인').

import test from 'node:test';
import assert from 'node:assert/strict';
import { INTERLUDES, getInterlude, availableRoutes } from '../src/content/interludes.js';
import { interludeFor, advanceEpisode } from '../src/engine/campaign.js';
import { createState, applyEffects } from '../src/engine/state.js';
import { EPISODE_ORDER } from '../src/content/episodes/index.js';

function atEndOf(episodeId) {
  const state = createState({ professionId: 'archaeologist', seed: 11 });
  state.episode = episodeId;
  return state;
}

test('첫 장에는 막간이 없다 — 이미 그 배를 탔다', () => {
  assert.equal(getInterlude(EPISODE_ORDER[0]), null);
});

test('두 번째 장부터는 항로를 고른다', () => {
  for (const id of EPISODE_ORDER.slice(1)) {
    const inter = getInterlude(id);
    assert.ok(inter, `${id} 로 가는 막간이 없다`);
    assert.ok(inter.routes.length >= 2, `${id} 막간에 고를 것이 하나뿐이다`);
    assert.ok(inter.intro.length, `${id} 막간에 서술이 없다`);
  }
});

test('모든 항로는 시간과 서술과 효과를 갖는다', () => {
  for (const [id, inter] of Object.entries(INTERLUDES)) {
    for (const r of inter.routes) {
      assert.ok(r.label, `${id}/${r.id} 에 이름이 없다`);
      assert.ok(r.detail, `${id}/${r.id} 에 무엇을 치르는지 적혀 있지 않다`);
      assert.ok(r.text?.length, `${id}/${r.id} 에 여정 서술이 없다`);
      assert.ok(r.effects.time > 0, `${id}/${r.id} 가 시간을 쓰지 않는다`);
    }
  }
});

test('빠른 길과 느린 길은 시간과 회복을 맞바꾼다', () => {
  const { routes } = INTERLUDES.mesopotamia;
  const fast = routes.find((r) => r.id === 'fast');
  const steady = routes.find((r) => r.id === 'steady');

  assert.ok(fast.effects.time < steady.effects.time, '빠른 길이 더 오래 걸린다');
  assert.ok(fast.effects.hp < steady.effects.hp, '빠른 길이 더 잘 쉬어진다');
  assert.ok(fast.effects.flags.aheadOfCrane, '서둘러도 앞서지 못하면 고를 이유가 없다');
});

test('조건이 안 맞는 항로는 아예 보이지 않는다', () => {
  const state = atEndOf('luxor');
  const inter = getInterlude('mesopotamia');

  const before = availableRoutes(inter, state).map((r) => r.id);
  assert.equal(before.includes('london'), false, '단서 없이 런던 항로가 떴다');

  applyEffects(state, { clues: ['crane_expedition'] });
  const after = availableRoutes(inter, state).map((r) => r.id);
  assert.ok(after.includes('london'), '단서를 얻어도 런던 항로가 안 뜬다');
});

test('막간은 다음 장의 것이지 지금 장의 것이 아니다', () => {
  const state = atEndOf('luxor');
  const inter = interludeFor(state);
  assert.equal(inter.episodeId, 'mesopotamia');
  assert.equal(inter.title, INTERLUDES.mesopotamia.title);
});

test('마지막 장 뒤에는 막간이 없다', () => {
  assert.equal(interludeFor(atEndOf('angkor')), null);
});

test('고른 항로의 효과가 기본 여정을 대신한다', () => {
  const slow = atEndOf('luxor');
  const fast = atEndOf('luxor');

  const a = advanceEpisode(slow, { routeId: 'steady' });
  const b = advanceEpisode(fast, { routeId: 'fast' });

  assert.equal(a.route.id, 'steady');
  assert.equal(b.route.id, 'fast');
  assert.ok(slow.tick > fast.tick, '느린 항로가 더 빨리 도착했다');
  assert.ok(slow.hp >= fast.hp, '느린 항로가 덜 회복됐다');
  assert.equal(fast.flags.aheadOfCrane, true);
  assert.equal(a.episode.id, 'mesopotamia');
});

test('항로를 고르지 않으면 에피소드의 기본 여정으로 넘어간다', () => {
  const state = atEndOf('luxor');
  const moved = advanceEpisode(state);
  assert.equal(moved.ok, true);
  assert.equal(moved.route, null);
  assert.equal(state.episode, 'mesopotamia');
});

test('없는 항로 id 를 넘기면 기본 여정으로 떨어진다', () => {
  const state = atEndOf('luxor');
  const moved = advanceEpisode(state, { routeId: '없는항로' });
  assert.equal(moved.ok, true);
  assert.equal(moved.route, undefined);
  assert.equal(state.episode, 'mesopotamia');
});
