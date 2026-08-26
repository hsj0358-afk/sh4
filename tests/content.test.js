// 콘텐츠 무결성 검사.
// 손으로 쓰는 시나리오에서 가장 자주 깨지는 것은 오타난 참조다.
// 장면 이동, 아이템 이름, 단서 id, 동료 id 를 전부 대조한다.

import test from 'node:test';
import assert from 'node:assert/strict';
import { EPISODES, EPISODE_ORDER } from '../src/content/episodes/index.js';
import { ITEMS } from '../src/content/items.js';
import { CLUES } from '../src/content/clues.js';
import { COMPANIONS } from '../src/content/companions.js';
import { PROFESSIONS } from '../src/content/professions.js';
import { STAT_IDS } from '../src/content/stats.js';
import { ENCOUNTERS } from '../src/content/encounters.js';
import { createState } from '../src/engine/state.js';

const probe = createState({ professionId: 'archaeologist', seed: 1 });

/** 모든 에피소드의 모든 장면. */
function* allScenes() {
  for (const ep of Object.values(EPISODES)) {
    for (const [id, scene] of Object.entries(ep.scenes)) yield { ep, id, scene };
  }
}

/** 장면 안의 모든 결과 노드(선택지·판정 분기·자유입력)를 훑는다. */
function* results() {
  for (const { scene } of allScenes()) {
    const sources = [
      ...(scene.choices || []),
      ...(scene.freeform || []),
      ...(scene.ambientCheck ? [scene.ambientCheck] : []),
    ];
    for (const src of sources) {
      yield { scene, node: src };
      for (const branch of Object.values(src.outcomes || {})) {
        yield { scene, node: branch };
      }
    }
  }
  for (const ep of Object.values(EPISODES)) {
    for (const ev of ep.pressureEvents || []) {
      yield { scene: { id: `${ep.id}/pressure:${ev.id}` }, node: ev };
    }
  }
}

test('모든 장면 이동 대상이 존재한다', () => {
  const allIds = new Set();
  for (const { id } of allScenes()) allIds.add(id);
  for (const { scene, node } of results()) {
    const goto = node.goto || node.effects?.goto;
    if (!goto) continue;
    assert.ok(allIds.has(goto), `${scene.id} → 없는 장면 '${goto}'`);
  }
});

test('장면 id 가 에피소드끼리 겹치지 않는다', () => {
  // state.visited 는 장면 id 로만 키를 만든다. 겹치면 방문 기록이 섞인다.
  const seen = new Map();
  for (const { ep, id } of allScenes()) {
    assert.ok(!seen.has(id), `'${id}' 가 ${seen.get(id)} 와 ${ep.id} 에서 중복`);
    seen.set(id, ep.id);
  }
});

test('효과에 등장하는 아이템은 전부 정의되어 있다', () => {
  for (const { scene, node } of results()) {
    const eff = node.effects || {};
    const names = [
      ...(eff.items || []),
      ...(eff.removeItems || []),
      ...Object.keys(eff.spend || {}),
      ...(node.requires?.items || []),
    ];
    for (const n of names) assert.ok(ITEMS[n], `${scene.id}: 없는 아이템 '${n}'`);
  }
});

test('조건으로 요구하는 물건은 어딘가에서 얻을 수 있다', () => {
  // 정의만 되어 있고 아무도 주지 않는 아이템은, 그것을 요구하는 선택지를 영영 잠근다.
  // 이 검사가 없어서 '검은 태양의 열쇠' 가 세 커밋 동안 못 얻는 물건이었다.
  const obtainable = new Set();
  for (const p of PROFESSIONS) for (const n of p.items) obtainable.add(n);
  for (const { node } of results()) {
    for (const n of node.effects?.items || []) obtainable.add(n);
  }
  for (const e of Object.values(ENCOUNTERS)) {
    for (const x of Object.values(e.exits || {})) {
      for (const n of x.effects?.items || []) obtainable.add(n);
    }
  }

  const required = new Map();
  for (const { scene, node } of results()) {
    for (const n of node.requires?.items || []) required.set(n, scene.id);
  }
  for (const { scene } of allScenes()) {
    for (const c of scene.choices || []) {
      for (const n of c.requires?.items || []) required.set(n, scene.id);
    }
  }

  for (const [name, where] of required) {
    assert.ok(obtainable.has(name), `${where}: '${name}' 을 요구하는데 아무도 주지 않는다`);
  }
});

// 콘텐츠가 아니라 엔진이 쥐여 주는 것들. 여기 적힌 것만 예외로 둔다.
const GRANTED_BY_ENGINE = ['동행의 등불'];

test('정의된 아이템 중 아무도 주지 않는 것이 없다', () => {
  const obtainable = new Set(GRANTED_BY_ENGINE);
  for (const p of PROFESSIONS) for (const n of p.items) obtainable.add(n);
  for (const { node } of results()) {
    for (const n of node.effects?.items || []) obtainable.add(n);
  }
  for (const e of Object.values(ENCOUNTERS)) {
    for (const x of Object.values(e.exits || {})) {
      for (const n of x.effects?.items || []) obtainable.add(n);
    }
  }
  const orphans = Object.keys(ITEMS).filter((n) => !obtainable.has(n));
  assert.deepEqual(orphans, [], `얻을 수 없는 아이템: ${orphans.join(', ')}`);
});

test('직업 시작 장비도 전부 정의되어 있다', () => {
  for (const p of PROFESSIONS) {
    for (const n of p.items) assert.ok(ITEMS[n], `${p.name}: 없는 시작 장비 '${n}'`);
  }
});

test('단서 id 는 전부 도감에 있다', () => {
  for (const { scene, node } of results()) {
    for (const c of node.effects?.clues || []) {
      assert.ok(CLUES[c], `${scene.id}: 없는 단서 '${c}'`);
    }
    for (const c of node.requires?.clues || []) {
      assert.ok(CLUES[c], `${scene.id}: 없는 단서 조건 '${c}'`);
    }
  }
});

test('동료 id 는 전부 정의되어 있다', () => {
  for (const { scene, node } of results()) {
    for (const id of node.effects?.companions || []) {
      assert.ok(COMPANIONS[id], `${scene.id}: 없는 동료 '${id}'`);
    }
    const changes = [
      ...(node.effects?.companion ? [node.effects.companion] : []),
      ...(node.effects?.companionChanges || []),
    ];
    for (const ce of changes) assert.ok(COMPANIONS[ce.id], `${scene.id}: 없는 동료 '${ce.id}'`);
    for (const id of node.requires?.companions || []) {
      assert.ok(COMPANIONS[id], `${scene.id}: 없는 동료 조건 '${id}'`);
    }
  }
});

test('판정은 실재하는 능력치를 쓰고 목표값을 갖는다', () => {
  for (const { scene, node } of results()) {
    if (!node.check) continue;
    assert.ok(STAT_IDS.includes(node.check.stat), `${scene.id}: 없는 능력치 '${node.check.stat}'`);
    assert.equal(typeof node.check.target, 'number', `${scene.id}: 목표값 누락`);
    assert.ok(node.check.target >= 8 && node.check.target <= 20, `${scene.id}: 목표값이 범위 밖`);
  }
});

test('모든 판정에 최소한 성공과 실패 서술이 있다', () => {
  for (const { scene } of allScenes()) {
    const sources = [
      ...(scene.choices || []),
      ...(scene.freeform || []),
      ...(scene.ambientCheck ? [scene.ambientCheck] : []),
    ];
    for (const src of sources) {
      if (!src.check) continue;
      const o = src.outcomes || {};
      assert.ok(o.success || o.crit, `${scene.id}/${src.id}: 성공 분기 없음`);
      assert.ok(o.fail || o.fumble, `${scene.id}/${src.id}: 실패 분기 없음`);
      for (const [key, branch] of Object.entries(o)) {
        const text = typeof branch.text === 'function' ? branch.text(probe) : branch.text;
        assert.ok(text && text.length, `${scene.id}/${src.id}/${key}: 서술 없음`);
      }
    }
  }
});

test('실패 분기가 길을 완전히 막지 않는다', () => {
  // 실패해도 서술은 남고, 대부분은 다른 결과(대가·단서·이동)를 동반해야 한다.
  let failWithConsequence = 0;
  let failTotal = 0;
  for (const { scene } of allScenes()) {
    for (const src of scene.choices || []) {
      if (!src.check) continue;
      for (const key of ['fail', 'fumble']) {
        const b = src.outcomes?.[key];
        if (!b) continue;
        failTotal++;
        const eff = b.effects || {};
        const consequence =
          eff.goto ||
          b.goto ||
          eff.hp ||
          eff.san ||
          eff.danger ||
          (eff.clues || []).length ||
          (eff.items || []).length ||
          (eff.removeItems || []).length ||
          eff.flags ||
          eff.time;
        if (consequence) failWithConsequence++;
      }
    }
  }
  assert.ok(failTotal > 0);
  assert.equal(failWithConsequence, failTotal, '대가 없는 실패 분기가 있다');
});

test('모든 장면에 위치와 본문이 있다', () => {
  for (const { id, scene } of allScenes()) {
    assert.equal(scene.id, id, `장면 id 불일치: ${id}`);
    assert.ok(scene.location, `${id}: 위치 없음`);
    const body = typeof scene.body === 'function' ? scene.body(probe) : scene.body;
    assert.ok(body && body.length, `${id}: 본문 없음`);
  }
});

test('막다른 장면은 종료 처리를 갖는다', () => {
  for (const { id, scene } of allScenes()) {
    if ((scene.choices || []).length) continue;
    assert.ok(scene.end || scene.ending, `${id}: 선택지도 결말도 없는 막다른 장면`);
  }
});

test('각 에피소드는 시작부터 결말까지 도달 가능하다', () => {
  for (const ep of Object.values(EPISODES)) {
    const scenes = ep.scenes;
    const seen = new Set();
    const queue = [ep.start];
    while (queue.length) {
      const id = queue.shift();
      if (seen.has(id) || !scenes[id]) continue;
      seen.add(id);
      for (const src of scenes[id].choices || []) {
        const targets = [
          src.goto,
          src.effects?.goto,
          ...Object.values(src.outcomes || {}).flatMap((b) => [b.goto, b.effects?.goto]),
        ].filter(Boolean);
        queue.push(...targets);
      }
    }
    for (const id of Object.keys(scenes)) {
      assert.ok(seen.has(id), `${ep.id}/${id}: 어디에서도 도달할 수 없는 장면`);
    }
    const ended = Object.values(scenes).some((s) => (s.end || s.ending) && seen.has(s.id));
    assert.ok(ended, `${ep.id}: 결말에 도달할 수 없다`);
  }
});

test('마지막을 뺀 모든 에피소드가 다음 장을 가리킨다', () => {
  for (const id of EPISODE_ORDER.slice(0, -1)) {
    const ep = EPISODES[id];
    const nexts = Object.values(ep.scenes)
      .map((s) => s.end?.next)
      .filter(Boolean);
    assert.ok(nexts.length, `${id}: 다음 장으로 가는 결말이 없다`);
    for (const n of nexts) assert.ok(EPISODES[n], `${id}: 없는 다음 장 '${n}'`);
  }
});

test('선택지는 장면마다 3개 이상 제시된다 (결말·전투 장면 제외)', () => {
  for (const { id, scene } of allScenes()) {
    // 전투 장면은 조우가 행동을 내준다. 아래 전투 검사가 따로 본다.
    if (scene.combat) continue;
    if (scene.end || scene.ending || !(scene.choices || []).length) continue;
    assert.ok(scene.choices.length >= 3, `${id}: 선택지가 ${scene.choices.length}개뿐`);
    assert.ok(scene.choices.length <= 6, `${id}: 선택지가 너무 많다`);
  }
});

// ── 캠페인 층이 정하는 것을 장면이 다시 못 박지 않는다 ────────────
//
// 실제 플레이에서 걸린 것. 8주짜리 런던 경유를 고르고 도착했더니
// 에피소드 2 의 첫 문장이 「3주. 홍해를 내려가…」였다. 여정의 길이는
// 막간에서 고른 항로가 정하므로, 도착 장면이 그것을 다시 적으면 어긋난다.

test('장 첫 장면은 여정의 길이를 못 박지 않는다', () => {
  for (const ep of Object.values(EPISODES)) {
    const scene = ep.scenes[ep.start];
    const body = [].concat(
      typeof scene.body === 'function' ? scene.body(probe) : scene.body || [],
    ).join(' ');
    assert.ok(
      !/\d+\s*주[.\s]/.test(body),
      `${ep.id} 의 도착 장면이 여정 기간을 직접 적는다 — 항로 선택과 어긋난다`,
    );
  }
});

// 시간을 말하는 문장은 시계를 봐야 한다. 고정 문구는 오후 열 시 반에 일출을 만든다.
test('본문이 시각을 단정하지 않는다', () => {
  const FIXED = [/해가 능선 위로 올라오고 있다\./, /아침 빛을 받아/, /밤을 하나 통째로/];
  for (const { ep, id, scene } of allScenes()) {
    const body = [].concat(
      typeof scene.body === 'function' ? scene.body(probe) : scene.body || [],
    ).join(' ');
    for (const pat of FIXED) {
      assert.ok(!pat.test(body), `${ep.id}/${id} 에 시각을 단정하는 문장이 남아 있다: ${pat}`);
    }
  }
});
