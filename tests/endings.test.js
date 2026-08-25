// 결말 — 세 대륙을 지나온 상태가 마지막 문장을 고른다.

import test from 'node:test';
import assert from 'node:assert/strict';
import { ENDINGS, resolveEnding, endingCoda } from '../src/content/endings.js';
import { createState, applyEffects } from '../src/engine/state.js';
import { createGM } from '../src/engine/gm.js';
import { advanceEpisode } from '../src/engine/campaign.js';
import { EPISODES } from '../src/content/episodes/index.js';

const fresh = () => createState({ professionId: 'archaeologist', seed: 7 });

test('모든 결말이 제목과 본문과 조건을 갖는다', () => {
  for (const e of ENDINGS) {
    assert.ok(e.id, '결말에 id 가 없다');
    assert.ok(e.title, `${e.id}: 제목 없음`);
    assert.ok(e.text?.length > 50, `${e.id}: 본문이 너무 짧다`);
    assert.equal(typeof e.when, 'function', `${e.id}: 조건 없음`);
  }
});

test('마지막 결말은 무조건 맞는 그물이다', () => {
  // 아무 조건도 못 맞춘 플레이어에게도 결말이 있어야 한다.
  const last = ENDINGS[ENDINGS.length - 1];
  assert.equal(last.when(fresh()), true, '기본 결말이 조건을 건다');
  assert.equal(resolveEnding(fresh()).id, last.id);
});

test('문을 봉인하면 봉인 결말이 나온다', () => {
  const s = fresh();
  applyEffects(s, { flags: { gateSealed: true } });
  assert.equal(resolveEnding(s).id, 'sealed');
});

test('문을 열면 다른 결말이 나온다', () => {
  const s = fresh();
  applyEffects(s, { flags: { gateOpened: true } });
  assert.equal(resolveEnding(s).id, 'opened');
});

test('봉인이 개방보다 우선한다', () => {
  // 둘 다 서 있을 수는 없다. 그래도 데이터상 가능하니 순서로 정해 둔다.
  const s = fresh();
  applyEffects(s, { flags: { gateSealed: true, gateOpened: true } });
  assert.equal(resolveEnding(s).id, 'sealed');
});

test('공개 결말은 증거가 있어야 한다', () => {
  const bare = fresh();
  applyEffects(bare, { flags: { wentPublic: true } });
  assert.notEqual(resolveEnding(bare).id, 'exposed', '증거 없이 공개 결말이 나온다');

  const proven = fresh();
  applyEffects(proven, {
    flags: { wentPublic: true },
    clues: ['first_civilization', 'third_record'],
  });
  assert.equal(resolveEnding(proven).id, 'exposed');
});

test('증거만 있고 공개하지 않으면 보관 결말이 나온다', () => {
  const s = fresh();
  applyEffects(s, { clues: ['third_record'] });
  assert.equal(resolveEnding(s).id, 'kept');
});

test('다섯 결말이 전부 도달 가능하다', () => {
  const cases = {
    sealed: { flags: { gateSealed: true } },
    opened: { flags: { gateOpened: true } },
    exposed: { flags: { wentPublic: true }, clues: ['first_civilization', 'third_record'] },
    kept: { clues: ['first_civilization'] },
    walked_away: {},
  };
  for (const [id, effect] of Object.entries(cases)) {
    const s = fresh();
    applyEffects(s, effect);
    assert.equal(resolveEnding(s).id, id, `${id} 결말에 도달할 수 없다`);
  }
  assert.equal(Object.keys(cases).length, ENDINGS.length, '검사되지 않은 결말이 있다');
});

// ── 후일담 ──────────────────────────────────────────────────────

test('혼자 나온 사람과 셋이 나온 사람은 다르게 끝난다', () => {
  const alone = endingCoda(fresh()).join('\n');
  assert.match(alone, /혼자였다/);

  const party = fresh();
  applyEffects(party, { companions: ['sokha', 'crane', 'seraphina'] });
  const together = endingCoda(party).join('\n');
  assert.match(together, /3명 전부/);
  assert.notEqual(alone, together);
});

test('후일담은 남은 사람 수를 정확히 센다', () => {
  // 한때 다섯 명을 나열해 놓고 "셋 다 걸어서 나왔다" 라고 적었다.
  const five = fresh();
  applyEffects(five, { companions: ['nadia', 'finch', 'seraphina', 'sokha', 'crane'] });
  assert.match(endingCoda(five).join('\n'), /5명 전부/);

  const two = fresh();
  applyEffects(two, { companions: ['nadia', 'finch'] });
  const coda = endingCoda(two).join('\n');
  assert.match(coda, /나디아 하룬과 올리버 핀치가 함께 나왔다/);
  assert.doesNotMatch(coda, /명 전부/);
});

test('돌아오지 못한 사람은 이름으로 남는다', () => {
  const s = fresh();
  applyEffects(s, { companions: ['sokha', 'crane'] });
  applyEffects(s, { companion: { id: 'crane', present: false } });
  const coda = endingCoda(s).join('\n');
  assert.match(coda, /아셔 크레인/);
  assert.match(coda, /돌아오지 못한/);
});

test('맞물린 두 유물은 후일담에 남는다', () => {
  const s = fresh();
  applyEffects(s, { items: ['검은 태양의 열쇠', '문의 각인'] });
  assert.match(endingCoda(s).join('\n'), /두 조각/);
});

test('후일담은 단서 수를 센다', () => {
  const s = fresh();
  applyEffects(s, { clues: ['black_sun', 'not_first'] });
  assert.match(endingCoda(s).join('\n'), /단서 2개/);
});

// ── GM 통합 ─────────────────────────────────────────────────────

function atAngkor() {
  const state = createState({ professionId: 'occultist', seed: 4 });
  createGM({ state, episode: EPISODES.luxor }).start();
  advanceEpisode(state);
  createGM({ state, episode: EPISODES.mesopotamia }).start();
  advanceEpisode(state);
  const gm = createGM({ state, episode: EPISODES.angkor });
  gm.start();
  return { state, gm };
}

test('결말 장면에 들어가면 상태에 맞는 결말이 붙는다', () => {
  const { state, gm } = atAngkor();
  applyEffects(state, { flags: { gateSealed: true } });

  const events = gm.enterScene('angkor_epilogue', []);

  assert.ok(state.ended, '결말이 설정되지 않았다');
  assert.equal(state.ended.type, 'finale');
  assert.equal(state.ended.ending, 'sealed');
  assert.match(state.ended.title, /닫힌 채로/);
  assert.ok(events.some((e) => e.type === 'end'));
});

test('결말 본문에 후일담이 이어 붙는다', () => {
  const { state, gm } = atAngkor();
  applyEffects(state, { clues: ['third_record'] });
  gm.enterScene('angkor_epilogue', []);
  assert.match(state.ended.text, /단서 \d+개/, '후일담이 붙지 않았다');
});

test('마지막 장에서는 다음 장 버튼이 뜨지 않는다', () => {
  const { state, gm } = atAngkor();
  gm.enterScene('angkor_epilogue', []);
  assert.equal(state.ended.type, 'finale', 'chapter 로 끝나면 다음 장을 찾는다');
});

test('3장에서 크레인은 관계에 따라 합류한다', () => {
  for (const [flags, expected] of [
    [{ craneAlly: true }, true],
    [{ craneHasTablet: true }, false],
  ]) {
    const state = createState({ professionId: 'soldier', seed: 2 });
    createGM({ state, episode: EPISODES.luxor }).start();
    applyEffects(state, { flags });
    advanceEpisode(state);
    createGM({ state, episode: EPISODES.mesopotamia }).start();
    advanceEpisode(state);
    createGM({ state, episode: EPISODES.angkor }).start();

    assert.equal(
      !!state.companions.crane?.present,
      expected,
      `${JSON.stringify(flags)} 에서 크레인 동행 여부가 틀렸다`,
    );
  }
});

test('세 대륙의 기록이 모여야 마지막 추론이 열린다', () => {
  const { state, gm } = atAngkor();
  gm.enterScene('star_chamber', []);
  assert.equal(gm.choices().some((c) => c.id === 'read_third'), false);

  applyEffects(state, { clues: ['first_civilization'] });
  assert.equal(gm.choices().some((c) => c.id === 'read_third'), true);
});

test('문을 건드리지 않고 공개하는 길이 실제로 걸어진다', () => {
  // resolveEnding 만 통과하는 것으로는 부족하다. '검은 태양의 열쇠' 가 세 커밋 동안
  // 아무도 주지 않는 물건이었던 것처럼, 조건은 맞는데 길이 없을 수 있다.
  const { state, gm } = atAngkor();
  applyEffects(state, { clues: ['first_civilization', 'third_record'] });

  gm.enterScene('the_door', []);
  const away = gm.choices().find((c) => c.id === 'walk_away');
  assert.ok(away, '문 앞에서 돌아설 수가 없다');
  gm.act('walk_away');
  assert.equal(state.scene, 'angkor_finale');

  const publish = gm.choices().find((c) => c.id === 'go_public');
  assert.ok(publish, '증거를 다 가졌는데 공개할 수가 없다');
  gm.act('go_public');
  assert.equal(state.flags.wentPublic, true);

  gm.act('end_campaign');
  assert.equal(state.ended?.ending, 'exposed', `실제로 나온 결말: ${state.ended?.ending}`);
});

test('문을 봉인한 사람은 공개했어도 봉인 결말로 끝난다', () => {
  // 문에 한 일이 더 결정적이다. 순서로 그것을 정해 두었다.
  const s = fresh();
  applyEffects(s, {
    flags: { gateSealed: true, wentPublic: true },
    clues: ['first_civilization', 'third_record'],
  });
  assert.equal(resolveEnding(s).id, 'sealed');
});

test('두 조각이 있어야 문을 봉인할 수 있다', () => {
  const { state, gm } = atAngkor();
  gm.enterScene('the_door', []);
  assert.equal(gm.choices().some((c) => c.id === 'seal_gate'), false);

  applyEffects(state, { items: ['검은 태양의 열쇠', '문의 각인'] });
  assert.equal(gm.choices().some((c) => c.id === 'seal_gate'), true);
});
