// 지도 데이터 검사. 지도는 콘텐츠를 참조하므로 오타가 조용히 숨는다.

import test from 'node:test';
import assert from 'node:assert/strict';
import { EPISODES } from '../src/content/episodes/index.js';
import { WORLD_SITES, siteState } from '../src/content/world.js';
import { CLUES } from '../src/content/clues.js';
import { createState, applyEffects } from '../src/engine/state.js';

const episodes = Object.values(EPISODES);

test('모든 에피소드에 현장 도면이 있다', () => {
  for (const ep of episodes) {
    assert.ok(ep.map, `${ep.id}: 지도 정의 없음`);
    assert.ok(ep.map.nodes.length, `${ep.id}: 지도 노드 없음`);
  }
});

test('지도의 모든 노드가 실재하는 장면을 가리킨다', () => {
  for (const ep of episodes) {
    for (const n of ep.map.nodes) {
      assert.ok(ep.scenes[n.scene], `${ep.id}: 지도에 없는 장면 '${n.scene}'`);
      assert.ok(n.label, `${ep.id}/${n.scene}: 라벨 없음`);
    }
  }
});

test('모든 장면이 지도에 올라와 있다', () => {
  for (const ep of episodes) {
    const mapped = new Set(ep.map.nodes.map((n) => n.scene));
    for (const id of Object.keys(ep.scenes)) {
      assert.ok(mapped.has(id), `${ep.id}/${id}: 지도에 없는 장면`);
    }
  }
});

test('지도의 길은 실재하는 노드끼리 잇는다', () => {
  for (const ep of episodes) {
    const ids = new Set(ep.map.nodes.map((n) => n.scene));
    for (const [a, b] of ep.map.links) {
      assert.ok(ids.has(a), `${ep.id}: 없는 노드 '${a}'`);
      assert.ok(ids.has(b), `${ep.id}: 없는 노드 '${b}'`);
      assert.notEqual(a, b, `${ep.id}: 자기 자신으로 이어진 길`);
    }
  }
});

test('좌표가 도면 안에 있다', () => {
  for (const ep of episodes) {
    for (const n of ep.map.nodes) {
      assert.ok(n.x >= 0 && n.x <= 100, `${ep.id}/${n.scene}: x 범위 밖`);
      assert.ok(n.y >= 0 && n.y <= 100, `${ep.id}/${n.scene}: y 범위 밖`);
    }
  }
  for (const s of WORLD_SITES) {
    assert.ok(s.x >= 0 && s.x <= 100, `${s.id}: x 범위 밖`);
    assert.ok(s.y >= 0 && s.y <= 100, `${s.id}: y 범위 밖`);
  }
});

test('지상과 지하가 나뉘어 있다', () => {
  for (const ep of episodes) {
    const above = ep.map.nodes.filter((n) => n.y < ep.map.groundY);
    const below = ep.map.nodes.filter((n) => n.y >= ep.map.groundY);
    assert.ok(above.length, `${ep.id}: 지상 장소가 없다`);
    assert.ok(below.length, `${ep.id}: 지하 장소가 없다`);
  }
});

test('세계 지도의 단서 참조가 유효하다', () => {
  for (const s of WORLD_SITES) {
    if (s.revealedBy) assert.ok(CLUES[s.revealedBy], `${s.id}: 없는 단서 '${s.revealedBy}'`);
    assert.ok(s.name && s.note, `${s.id}: 설명 누락`);
  }
});

test('에피소드가 걸린 지역은 실제 에피소드 id 를 쓴다', () => {
  const withEpisode = WORLD_SITES.filter((s) => s.episode);
  assert.ok(withEpisode.length, '에피소드가 걸린 지역이 없다');
  for (const s of withEpisode) {
    assert.ok(EPISODES[s.episode], `${s.id}: 없는 에피소드 '${s.episode}'`);
  }
});

test('플레이 가능한 모든 에피소드가 세계 지도에 있다', () => {
  const mapped = new Set(WORLD_SITES.map((s) => s.episode).filter(Boolean));
  for (const ep of episodes) {
    assert.ok(mapped.has(ep.id), `${ep.id}: 세계 지도에 지점이 없다`);
  }
});

test('단서를 얻으면 다음 행선지가 소문에서 좌표로 승격된다', () => {
  const s = createState({ professionId: 'explorer', seed: 4 });
  s.episode = 'luxor';
  const meso = WORLD_SITES.find((x) => x.id === 'mesopotamia');
  assert.equal(siteState(meso, s), 'unknown');
  applyEffects(s, { clues: ['mesopotamia_lead'] });
  assert.equal(siteState(meso, s), 'known');
});

test('현재 에피소드의 지역은 다녀온 곳으로 표시된다', () => {
  const s = createState({ professionId: 'explorer', seed: 4 });
  s.episode = 'luxor';
  const luxor = WORLD_SITES.find((x) => x.id === 'luxor');
  assert.equal(siteState(luxor, s), 'visited');
});

test('소문뿐인 지역은 소문으로 남는다', () => {
  const s = createState({ professionId: 'explorer', seed: 4 });
  const angkor = WORLD_SITES.find((x) => x.id === 'angkor');
  assert.equal(siteState(angkor, s), 'rumor');
});
