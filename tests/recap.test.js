// 줄거리 요약.
//
// 며칠 만에 돌아온 사람에게 "지금 어디까지 왔는가" 를 몇 줄로 알려 준다.
// 장면마다 요약문을 적어 두지 않고 상태에서 만든다 — 그래야 어긋나지 않는다.

import test from 'node:test';
import assert from 'node:assert/strict';
import { recap } from '../src/engine/recap.js';
import { createState, applyEffects } from '../src/engine/state.js';
import { EPISODES } from '../src/content/episodes/index.js';

const fresh = (over = {}) => {
  const s = createState({ professionId: 'archaeologist', seed: 3 });
  s.episode = 'luxor';
  return Object.assign(s, over);
};

test('상태가 없으면 아무 줄도 만들지 않는다', () => {
  assert.deepEqual(recap(null, EPISODES.luxor), []);
});

test('첫 장에서는 지나온 곳을 말하지 않는다', () => {
  const lines = recap(fresh(), EPISODES.luxor).join('\n');
  assert.match(lines, /제 1 장/);
  assert.ok(!lines.includes('지나왔다'), '아직 지나온 곳이 없는데 지나왔다고 한다');
});

test('장이 넘어가면 지나온 곳을 센다', () => {
  const s = fresh({ episode: 'angkor', visitedEpisodes: ['luxor', 'mesopotamia'] });
  const lines = recap(s, EPISODES.angkor).join('\n');
  assert.match(lines, /제 3 장/);
  assert.match(lines, /지나왔다/);
  assert.match(lines, /이집트의 검은 태양과 두 강 사이의 문을 지나왔다/);
});

test('제목에서 「에피소드 N —」 은 떼고 지명만 남긴다', () => {
  const lines = recap(fresh(), EPISODES.luxor).join('\n');
  assert.ok(!lines.includes('에피소드'), '요약에 에피소드 번호가 그대로 남았다');
});

test('곁에 있는 사람과 잃은 사람을 구별한다', () => {
  const s = fresh();
  applyEffects(s, { companions: ['nadia', 'finch'] });
  applyEffects(s, { companion: { id: 'finch', present: false } });
  const lines = recap(s, EPISODES.luxor).join('\n');
  assert.match(lines, /곁에는 나디아 하룬이 있다/);
  assert.match(lines, /돌아오지 못한 사람 — 올리버 핀치/);
});

test('혼자면 혼자라고 한다', () => {
  assert.match(recap(fresh(), EPISODES.luxor).join('\n'), /지금은 혼자다/);
});

test('여러 사람은 이름을 이어 붙이고 조사는 마지막을 따라간다', () => {
  const s = fresh();
  applyEffects(s, { companions: ['nadia', 'finch'] });
  // 하룬(받침) 과 핀치(받침 없음) — 마지막이 핀치이므로 '가'
  assert.match(recap(s, EPISODES.luxor).join('\n'), /나디아 하룬과 올리버 핀치가 있다/);
});

test('가방에는 유물만 올린다 — 횃불은 줄거리가 아니다', () => {
  const s = fresh();
  applyEffects(s, { items: ['횃불', '조각난 석판', '검은 태양의 열쇠'] });
  const lines = recap(s, EPISODES.luxor).join('\n');
  assert.ok(!lines.includes('횃불'), '일반 장비가 요약에 올라왔다');
  assert.match(lines, /조각난 석판과 검은 태양의 열쇠가 있다/);
});

test('마지막으로 적은 단서 하나만 보여준다', () => {
  const s = fresh();
  applyEffects(s, { clues: ['black_sun', 'sealed_by_locals'] });
  const lines = recap(s, EPISODES.luxor).join('\n');
  assert.match(lines, /마지막으로 적은 것 — 「봉해진 입」/);
  assert.equal((lines.match(/마지막으로 적은 것/g) || []).length, 1);
});

test('몸 상태는 성치 않을 때만 말한다', () => {
  const well = recap(fresh(), EPISODES.luxor).join('\n');
  assert.ok(!well.includes('상처'), '멀쩡한데 상처를 말한다');

  const hurt = fresh();
  hurt.hp = 2;
  assert.match(recap(hurt, EPISODES.luxor).join('\n'), /상처가 아물지 않았다/);

  const both = fresh();
  both.hp = 2;
  both.san = 2;
  assert.match(recap(both, EPISODES.luxor).join('\n'), /몸도 정신도/);
});

test('요약은 짧다 — 어떤 상태에서도 여덟 줄을 넘지 않는다', () => {
  const s = fresh({ episode: 'angkor', visitedEpisodes: ['luxor', 'mesopotamia'] });
  applyEffects(s, {
    companions: ['nadia', 'finch', 'seraphina', 'basim', 'sokha', 'crane'],
    items: ['조각난 석판', '별자리 기호판', '검은 태양의 열쇠', '문의 각인', '점토 원통'],
    clues: ['black_sun', 'same_hand', 'first_civilization'],
  });
  applyEffects(s, { companion: { id: 'crane', present: false } });
  s.hp = 1;
  s.san = 1;
  const lines = recap(s, EPISODES.angkor);
  assert.ok(lines.length <= 8, `요약이 ${lines.length}줄이다 — 요약이 아니다`);
});

test('날짜는 하루 미만이어도 1일째로 센다', () => {
  const s = fresh();
  s.tick = 4;
  assert.match(recap(s, EPISODES.luxor).join('\n'), /1일째/);
});

test('첫 줄이 누구의 판인지 말한다', () => {
  // 칸이 셋이라 「어디까지 왔나」보다 「어느 판인가」가 먼저 궁금하다.
  const s = fresh();
  s.char.name = '에드워드 몰리';
  const lines = recap(s, EPISODES.luxor);
  assert.match(lines[0], /에드워드 몰리/);
  assert.match(lines[0], new RegExp(s.char.profession));
});
