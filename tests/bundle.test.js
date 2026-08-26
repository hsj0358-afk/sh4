// 단일 파일 빌드.
//
// 번들러는 정규식으로 import/export 를 바꾼다. 코드베이스가 쓰는 형태가
// 늘어나면 조용히 깨지므로, 여기서 그 형태를 고정하고 결과를 검사한다.

import test from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, statSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { bundle, buildPage } from '../tools/bundle.js';

const SRC = new URL('../src/', import.meta.url).pathname;

function allJs(dir, out = []) {
  for (const n of readdirSync(dir)) {
    const p = join(dir, n);
    statSync(p).isDirectory() ? allJs(p, out) : p.endsWith('.js') && out.push(p);
  }
  return out;
}

test('번들이 문법적으로 올바르다', () => {
  const js = bundle();
  assert.doesNotThrow(() => new Function(js), '번들에 문법 오류가 있다');
});

test('모든 모듈이 번들에 들어간다', () => {
  const js = bundle();
  for (const f of allJs(SRC)) {
    const id = f.slice(SRC.length);
    assert.ok(js.includes(`__mod['${id}']`), `${id} 가 번들에서 빠졌다`);
  }
});

test('변환하지 못한 import/export 가 남지 않는다', () => {
  const js = bundle();
  assert.ok(!/^\s*import\s/m.test(js), '처리하지 못한 import 가 남았다');
  assert.ok(!/^\s*export\s/m.test(js), '처리하지 못한 export 가 남았다');
});

test('페이지가 자립형이다 — 글꼴 말고는 외부를 부르지 않는다', () => {
  const page = buildPage();
  const urls = [...page.matchAll(/(?:src|href)="(https?:\/\/[^"]+)"/g)].map((m) => m[1]);
  const outside = urls.filter((u) => !u.startsWith('https://fonts.g'));
  assert.deepEqual(outside, [], `외부 요청이 남았다: ${outside.join(', ')}`);
  assert.ok(!/(?:src|href)="\.\//.test(page), '상대 경로 참조가 남았다');
});

test('페이지에 화면과 스타일과 코드가 다 들어 있다', () => {
  const page = buildPage();
  for (const id of ['screen-title', 'screen-create', 'screen-play', 'dice-overlay', 'sheet']) {
    assert.ok(page.includes(`id="${id}"`), `${id} 가 없다`);
  }
  assert.ok(page.includes('--paper: #14110d'), '스타일이 안 들어갔다');
  assert.ok(page.includes("__req('ui/main.js')"), '진입점 호출이 없다');
});

test('본문 전용 출력은 문서 뼈대를 스스로 만들지 않는다', () => {
  const body = buildPage({ bodyOnly: true });
  assert.ok(!body.includes('<!doctype'), '아티팩트 skeleton 과 겹친다');
  assert.ok(!body.includes('<body>'));
  assert.ok(body.includes('<title>잃어버린 세계의 지도</title>'));
});

test('index.html 이 부르는 스타일시트가 번들에 실린다', () => {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  assert.ok(html.includes('./src/ui/styles.css'), 'index.html 의 스타일 경로가 바뀌었다');
  assert.ok(buildPage().includes('<style>'), '스타일이 인라인되지 않았다');
});
