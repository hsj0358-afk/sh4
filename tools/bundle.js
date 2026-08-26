// 단일 파일 빌드.
//
// 이 게임은 빌드 도구 없이 돌아간다 — 브라우저가 ES 모듈을 그대로 읽는다.
// 그래서 개발 중에는 번들러가 필요 없다. 필요한 건 배포할 때뿐이다:
// 정적 호스팅 한 곳에 올리거나, 파일 하나로 건네주거나, 오프라인으로 열 때.
//
// 모듈 전부를 순서대로 감싸 넣고 index.html 과 styles.css 를 합쳐
// 자립형 HTML 한 장을 만든다. 남는 외부 요청은 Google Fonts 하나뿐이고,
// 그것도 못 받으면 시스템 한글 글꼴로 조용히 떨어진다.
//
//   node tools/bundle.js [출력경로]        기본값: dist/lost-world-map.html
//   node tools/bundle.js --body out.html   <body> 안쪽만 (아티팩트용)
//
// 정규식으로 import/export 를 바꾼다. 일반적인 번들러라면 파서를 써야 하지만,
// 이 코드베이스가 쓰는 형태는 아래 다섯 가지뿐이고 테스트가 그것을 강제한다.

import { readFileSync, writeFileSync, mkdirSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, resolve, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const SRC = join(ROOT, 'src');
const ENTRY = join(SRC, 'ui', 'main.js');

// ── 모듈 수집 ────────────────────────────────────────────────────

function allModules(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) allModules(p, out);
    else if (p.endsWith('.js')) out.push(p);
  }
  return out;
}

const id = (abs) => relative(SRC, abs).split('\\').join('/');

/** 이 모듈이 무엇을 불러오는가. */
function importsOf(file, code) {
  const deps = [];
  for (const m of code.matchAll(/from\s+'([^']+)'/g)) {
    deps.push(resolve(dirname(file), m[1]));
  }
  return deps;
}

// ── 변환 ─────────────────────────────────────────────────────────

/**
 * ES 모듈 하나를 함수 본문으로 바꾼다.
 * import 는 __req 호출로, export 는 __exp 대입으로.
 */
function transform(file, code) {
  const names = new Set();
  let out = code;

  // import { a, b as c } from './x.js';  (여러 줄 가능)
  out = out.replace(
    /^import\s*\{([\s\S]*?)\}\s*from\s*'([^']+)';?$/gm,
    (_, spec, path) => {
      const binds = spec
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
        .map((s) => {
          const [from, to] = s.split(/\s+as\s+/).map((x) => x.trim());
          return to ? `${from}: ${to}` : from;
        })
        .join(', ');
      return `const { ${binds} } = __req('${id(resolve(dirname(file), path))}');`;
    },
  );

  // import * as ns from './x.js';
  out = out.replace(
    /^import\s*\*\s*as\s+(\w+)\s*from\s*'([^']+)';?$/gm,
    (_, ns, path) => `const ${ns} = __req('${id(resolve(dirname(file), path))}');`,
  );

  // import X from './x.js';
  out = out.replace(
    /^import\s+(\w+)\s*from\s*'([^']+)';?$/gm,
    (_, name, path) =>
      `const ${name} = __req('${id(resolve(dirname(file), path))}').default;`,
  );

  // export default X;
  out = out.replace(/^export\s+default\s+([\s\S]*?);?$/gm, (_, expr) => {
    return `__exp.default = ${expr.replace(/;$/, '')};`;
  });

  // export { a, b };  — 이미 선언된 것을 내보내기만 한다
  out = out.replace(/^export\s*\{([^}]*)\}\s*;?$/gm, (_, spec) => {
    for (const s of spec.split(',').map((x) => x.trim()).filter(Boolean)) {
      names.add(s.split(/\s+as\s+/).pop().trim());
    }
    return '';
  });

  // export const NAME / export function NAME / export class NAME
  out = out.replace(
    /^export\s+(const|let|var|function|class)\s+(\*?\s*)?(\w+)/gm,
    (_, kind, star, name) => {
      names.add(name);
      return `${kind} ${star || ''}${name}`;
    },
  );

  if (out.includes('export ')) {
    const stray = out.match(/^.*\bexport\b.*$/m);
    throw new Error(`${id(file)}: 처리하지 못한 export 가 남았다 — ${stray?.[0].trim()}`);
  }

  const tail = names.size
    ? `\nObject.assign(__exp, { ${[...names].join(', ')} });`
    : '';
  return `${out}${tail}`;
}

// ── 의존 순서 ────────────────────────────────────────────────────

function order(entry, graph) {
  const seen = new Set();
  const sorted = [];
  const visiting = new Set();
  (function visit(f) {
    if (seen.has(f)) return;
    if (visiting.has(f)) throw new Error(`순환 참조: ${id(f)}`);
    visiting.add(f);
    for (const d of graph.get(f) || []) visit(d);
    visiting.delete(f);
    seen.add(f);
    sorted.push(f);
  })(entry);
  return sorted;
}

// ── 빌드 ─────────────────────────────────────────────────────────

export function bundle() {
  const files = allModules(SRC);
  const code = new Map(files.map((f) => [f, readFileSync(f, 'utf8')]));
  const graph = new Map(files.map((f) => [f, importsOf(f, code.get(f))]));

  const sorted = order(ENTRY, graph);
  const modules = sorted
    .map((f) => `__mod['${id(f)}'] = function (__exp, __req) {\n${transform(f, code.get(f))}\n};`)
    .join('\n\n');

  return `const __mod = {};
const __cache = {};
function __req(name) {
  if (__cache[name]) return __cache[name];
  const exp = (__cache[name] = {});
  if (!__mod[name]) throw new Error('없는 모듈: ' + name);
  __mod[name](exp, __req);
  return exp;
}

${modules}

__req('${id(ENTRY)}');`;
}

/** index.html 에서 <body> 안쪽만 꺼낸다. */
function bodyOf(html) {
  return html.slice(html.indexOf('<body>') + 6, html.lastIndexOf('</body>')).trim();
}

// 스타일시트가 이름만 부르고 불러오지는 않던 글꼴. 아티팩트 CSP 가 허용하는
// 유일한 외부 호스트가 Google Fonts 라, 여기만 외부 요청이 하나 남는다.
const FONT_LINKS =
  '<link rel="preconnect" href="https://fonts.googleapis.com">' +
  '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>' +
  '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?' +
  'family=Nanum+Myeongjo:wght@400;700&family=Noto+Sans+KR:wght@400;500;700&display=swap">';

export function buildPage({ bodyOnly = false } = {}) {
  const html = readFileSync(join(ROOT, 'index.html'), 'utf8');
  const css = readFileSync(join(SRC, 'ui', 'styles.css'), 'utf8');
  const js = bundle();

  const body = bodyOf(html).replace(/<script type="module"[^>]*><\/script>/, '');
  const inner = `<style>\n${css}\n</style>\n${body}\n<script type="module">\n${js}\n</script>`;

  // 아티팩트 skeleton 이 <head> 를 대신 써 주므로 링크를 본문 맨 앞에 둔다.
  if (bodyOnly) return `<title>잃어버린 세계의 지도</title>\n${FONT_LINKS}\n${inner}\n`;

  return `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, maximum-scale=1" />
<meta name="theme-color" content="#14110d" />
<meta name="description" content="1897년, 잊힌 문명을 추적하는 모바일 텍스트 TRPG" />
<title>잃어버린 세계의 지도</title>
${FONT_LINKS}
</head>
<body>
${inner}
</body>
</html>
`;
}

// CLI
if (process.argv[1] && process.argv[1].endsWith('bundle.js')) {
  const args = process.argv.slice(2);
  const bodyOnly = args.includes('--body');
  const out = args.filter((a) => !a.startsWith('--'))[0]
    || join(ROOT, 'dist', bodyOnly ? 'artifact.html' : 'lost-world-map.html');

  const page = buildPage({ bodyOnly });
  mkdirSync(dirname(out), { recursive: true });
  writeFileSync(out, page);
  const kb = (Buffer.byteLength(page) / 1024).toFixed(0);
  console.log(`${relative(ROOT, out)} — ${kb}KB`);
}
