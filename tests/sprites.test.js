// 도트 초상.
//
// 격자를 문자열로 적으므로 오타가 곧 깨진 그림이다. 폭·높이·색인을 검사한다.

import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { COMPANIONS } from '../src/content/companions.js';

const src = readFileSync(new URL('../src/ui/sprites.js', import.meta.url), 'utf8');

/** 소스에서 격자 블록만 뽑는다 (브라우저 API 를 쓰므로 import 는 못 한다). */
function grids() {
  const out = {};
  const re = /^  (?:\/\/[^\n]*\n  )?(\w+): \[\n((?:    '[^']*',\n)+)  \],/gm;
  for (const m of src.matchAll(re)) {
    out[m[1]] = [...m[2].matchAll(/'([^']*)'/g)].map((r) => r[1]);
  }
  return out;
}

test('모든 인물의 격자가 12×14 이다', () => {
  const g = grids();
  assert.ok(Object.keys(g).length >= 6, `격자를 못 읽었다: ${Object.keys(g)}`);
  for (const [id, rows] of Object.entries(g)) {
    assert.equal(rows.length, 14, `${id}: 높이가 14가 아니다`);
    rows.forEach((r, i) => {
      assert.equal(r.length, 12, `${id} ${i}번 줄: 폭이 12가 아니다 — '${r}'`);
    });
  }
});

test('격자에는 정해진 기호만 쓴다', () => {
  for (const [id, rows] of Object.entries(grids())) {
    for (const r of rows) {
      assert.ok(/^[.1-6]+$/.test(r), `${id}: 모르는 기호가 있다 — '${r}'`);
    }
  }
});

test('모든 동료에게 초상이 있다', () => {
  const g = grids();
  for (const id of Object.keys(COMPANIONS)) {
    assert.ok(g[id], `${COMPANIONS[id].name}(${id}) 의 초상이 없다`);
  }
});

test('인물마다 색이 여섯 개씩 정의되어 있다', () => {
  const block = src.slice(src.indexOf('const SKINS'), src.indexOf('const FORMS'));
  for (const id of Object.keys(COMPANIONS)) {
    const m = block.match(new RegExp(`${id}: \\[([^\\]]*)\\]`));
    assert.ok(m, `${id} 의 색이 없다`);
    const colors = m[1].split(',').map((c) => c.trim()).filter(Boolean);
    assert.equal(colors.length, 6, `${id}: 색이 6개가 아니다`);
    for (const c of colors) assert.match(c, /^'#[0-9a-f]{6}'$/, `${id}: 색 형식 — ${c}`);
  }
});

test('얼굴에는 눈이 있다 — 어두운 선(6)을 쓰는 줄이 하나는 있다', () => {
  for (const [id, rows] of Object.entries(grids())) {
    if (id === 'UNKNOWN') continue;
    assert.ok(rows.some((r) => r.includes('6')), `${id}: 눈이 없다`);
  }
});
