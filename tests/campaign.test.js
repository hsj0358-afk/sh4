// 캠페인 — 에피소드 사이에서 무엇이 넘어가고 무엇이 정리되는가.

import test from 'node:test';
import assert from 'node:assert/strict';
import { createState, applyEffects } from '../src/engine/state.js';
import { createGM } from '../src/engine/gm.js';
import { advanceEpisode, hasNextEpisode, chapterNumber } from '../src/engine/campaign.js';
import { EPISODES, EPISODE_ORDER, getEpisode, nextEpisodeId } from '../src/content/episodes/index.js';

function afterEpisodeOne() {
  const state = createState({ professionId: 'archaeologist', seed: 9 });
  const gm = createGM({ state, episode: EPISODES.luxor });
  gm.start();
  return state;
}

test('에피소드 순서와 다음 장 조회', () => {
  assert.equal(EPISODE_ORDER[0], 'luxor');
  assert.equal(nextEpisodeId('luxor'), 'mesopotamia');
  assert.equal(nextEpisodeId('mesopotamia'), null);
  assert.equal(getEpisode('없는거').id, 'luxor');
});

test('다음 장으로 넘어가면 장면과 에피소드가 바뀐다', () => {
  const state = afterEpisodeOne();
  assert.equal(hasNextEpisode(state), true);

  const moved = advanceEpisode(state);
  assert.equal(moved.ok, true);
  assert.equal(state.episode, 'mesopotamia');
  assert.equal(state.scene, EPISODES.mesopotamia.start);
  assert.deepEqual(state.visitedEpisodes, ['luxor']);
  assert.equal(chapterNumber(state), 2);
});

test('마지막 장에서는 더 갈 곳이 없다', () => {
  const state = afterEpisodeOne();
  advanceEpisode(state);
  assert.equal(hasNextEpisode(state), false);
  assert.equal(advanceEpisode(state).ok, false);
});

test('단서 · 소지품 · 동료는 그대로 넘어간다', () => {
  const state = afterEpisodeOne();
  applyEffects(state, {
    clues: ['black_sun', 'not_first', 'mesopotamia_lead'],
    items: ['별자리 기호판'],
    companions: ['finch'],
    flags: { craneAlly: true },
  });

  advanceEpisode(state);

  assert.ok(state.clues.includes('not_first'));
  assert.ok(state.inventory.some((i) => i.name === '별자리 기호판'));
  assert.ok(state.companions.finch);
  assert.equal(state.flags.craneAlly, true);
});

test('위험도와 종료 상태는 지역에 두고 온다', () => {
  const state = afterEpisodeOne();
  applyEffects(state, { danger: 8 });
  state.ended = { type: 'chapter', title: '끝', text: '' };

  advanceEpisode(state);

  assert.equal(state.danger, 0);
  assert.equal(state.ended, null);
});

test('여정은 시간을 쓰고 몸을 회복시킨다', () => {
  const state = afterEpisodeOne();
  applyEffects(state, { hp: -6, san: -5 });
  const hp = state.hp;
  const san = state.san;
  const tick = state.tick;

  advanceEpisode(state);

  assert.ok(state.tick > tick, '여정에 시간이 걸리지 않았다');
  assert.ok(state.hp > hp, '여정 중 회복이 없었다');
  assert.ok(state.san > san);
});

test('2장의 GM 이 1장의 상태 위에서 시작된다', () => {
  const state = afterEpisodeOne();
  applyEffects(state, { clues: ['not_first'], companions: ['finch'] });
  const moved = advanceEpisode(state);

  const gm = createGM({ state, episode: moved.episode });
  const events = gm.start();

  assert.equal(events[0].type, 'scene');
  assert.match(events[0].location, /바스라/);
  assert.ok(state.companions.seraphina, '세라피나가 합류하지 않았다');
  assert.ok(state.companions.finch, '핀치가 사라졌다');
  assert.ok(gm.choices().length >= 3);
});

test('호감도가 높은 나디아만 두 강까지 따라온다', () => {
  for (const [affinity, expected] of [
    [5, true],
    [1, false],
  ]) {
    const state = afterEpisodeOne();
    state.companions.nadia.affinity = affinity;
    const moved = advanceEpisode(state);
    createGM({ state, episode: moved.episode }).start();
    assert.equal(
      state.companions.nadia.present,
      expected,
      `호감도 ${affinity} 에서 동행 여부가 틀렸다`,
    );
  }
});

test('두 지역의 단서가 만나야 열리는 결론이 있다', () => {
  const state = afterEpisodeOne();
  const moved = advanceEpisode(state);
  const gm = createGM({ state, episode: moved.episode });

  gm.enterScene('zigg_archive', []);
  const locked = gm.choices().find((c) => c.id === 'combine_clues');
  assert.equal(locked, undefined, '단서 없이 조합 선택지가 보인다');

  applyEffects(state, { clues: ['not_first', 'sumerian_list'] });
  const open = gm.choices().find((c) => c.id === 'combine_clues');
  assert.ok(open, '두 단서를 다 가져도 조합 선택지가 없다');
});

test('두 유물이 만나야 열리는 선택지가 있다', () => {
  const state = afterEpisodeOne();
  const moved = advanceEpisode(state);
  const gm = createGM({ state, episode: moved.episode });

  gm.enterScene('gate_chamber', []);
  assert.equal(gm.choices().some((c) => c.id === 'match_key'), false);

  applyEffects(state, { items: ['문의 각인', '검은 태양의 열쇠'] });
  assert.equal(gm.choices().some((c) => c.id === 'match_key'), true);
});

test('세이브를 통째로 직렬화해도 캠페인이 복원된다', () => {
  const state = afterEpisodeOne();
  applyEffects(state, { clues: ['not_first'] });
  advanceEpisode(state);

  const restored = JSON.parse(JSON.stringify(state));
  const gm = createGM({ state: restored, episode: getEpisode(restored.episode) });

  assert.equal(gm.scene().id, EPISODES.mesopotamia.start);
  assert.deepEqual(restored.visitedEpisodes, ['luxor']);
  assert.ok(restored.clues.includes('not_first'));
});
