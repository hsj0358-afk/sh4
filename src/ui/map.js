// 지도 패널 (기획서 6절의 보조 메뉴, 16절의 빈티지 지도 톤).
//
// 두 겹으로 그린다.
//   현장 지도 — 이번 에피소드의 장소 연결도. 다녀온 곳만 밝혀진다.
//   세계 지도 — 1897년의 세계. 유적 후보지는 소문에서 단서로, 단서에서 발자국으로 승격된다.
//
// 외부 에셋 없이 인라인 SVG 로 그린다.

import { WORLD_SITES, siteState } from '../content/world.js';

const NS = 'http://www.w3.org/2000/svg';

const svgEl = (tag, attrs = {}) => {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v));
  return n;
};

const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
};

/** 장소의 상태: 현재 위치 / 다녀옴 / 이어져 있으나 미탐사 / 모름 */
function nodeState(node, state, links) {
  if (state.scene === node.scene) return 'here';
  if (state.visited[node.scene]) return 'visited';
  const adjacent = links.some(
    ([a, b]) =>
      (a === node.scene && state.visited[b]) || (b === node.scene && state.visited[a]),
  );
  return adjacent ? 'edge' : 'unknown';
}

export function fieldMap(state, episode) {
  const wrap = el('div', 'map-block');
  const map = episode.map;
  if (!map) {
    wrap.appendChild(el('p', 'empty', '이 지역의 도면은 아직 없다.'));
    return wrap;
  }

  wrap.appendChild(el('p', 'type-head', `현장 도면 — ${episode.region}`));

  const byId = Object.fromEntries(map.nodes.map((n) => [n.scene, n]));
  const states = Object.fromEntries(
    map.nodes.map((n) => [n.scene, nodeState(n, state, map.links)]),
  );

  // 도면은 밝혀진 깊이까지만 보여준다. 아직 지상뿐이라면 지하는 한 뼘만 열어 둔다 —
  // 빈 공간이 화면의 절반을 먹지 않으면서도, 아래에 무언가 있다는 것은 남는다.
  const revealedDepth = map.nodes
    .filter((n) => states[n.scene] !== 'unknown')
    .reduce((max, n) => Math.max(max, n.y), 0);
  const height = Math.min(100, Math.max(map.groundY + 16, revealedDepth + 12));

  const svg = svgEl('svg', {
    viewBox: `0 0 100 ${height}`,
    class: 'map-svg',
    role: 'img',
    'aria-label': '현장 지도',
  });

  // 지상과 지하를 가르는 선
  svg.appendChild(
    svgEl('line', {
      x1: 0,
      y1: map.groundY,
      x2: 100,
      y2: map.groundY,
      class: 'map-ground',
    }),
  );
  const surface = svgEl('text', { x: 2, y: map.groundY - 2, class: 'map-axis' });
  surface.textContent = map.surfaceLabel;
  svg.appendChild(surface);
  const depth = svgEl('text', { x: 2, y: map.groundY + 5, class: 'map-axis' });
  depth.textContent = map.depthLabel;
  svg.appendChild(depth);

  // 길 — 양쪽 다 알고 있는 길만 그린다
  for (const [a, b] of map.links) {
    const na = byId[a];
    const nb = byId[b];
    if (!na || !nb) continue;
    const known = states[a] !== 'unknown' && states[b] !== 'unknown';
    if (!known) continue;
    const walked = state.visited[a] && state.visited[b];
    svg.appendChild(
      svgEl('line', {
        x1: na.x,
        y1: na.y,
        x2: nb.x,
        y2: nb.y,
        class: `map-link${walked ? ' walked' : ''}`,
      }),
    );
  }

  // 장소
  for (const n of map.nodes) {
    const st = states[n.scene];
    if (st === 'unknown') continue;

    const g = svgEl('g', { class: `map-node ${st}` });
    if (st === 'here') {
      g.appendChild(svgEl('circle', { cx: n.x, cy: n.y, r: 4.6, class: 'map-halo' }));
    }
    g.appendChild(svgEl('circle', { cx: n.x, cy: n.y, r: st === 'edge' ? 1.6 : 2.4 }));

    const label = svgEl('text', {
      x: n.x,
      y: n.y - 4.2,
      class: 'map-label',
      'text-anchor': n.x > 82 ? 'end' : n.x < 18 ? 'start' : 'middle',
    });
    label.textContent = st === 'edge' ? '미탐사' : n.label;
    g.appendChild(label);
    svg.appendChild(g);
  }

  wrap.appendChild(svg);

  const visitedCount = map.nodes.filter((n) => state.visited[n.scene]).length;
  wrap.appendChild(
    el('p', 'map-caption', `밝혀진 장소 ${visitedCount} / ${map.nodes.length}`),
  );
  return wrap;
}

const WORLD_STATE_LABEL = {
  visited: '다녀옴',
  known: '단서 확보',
  rumor: '소문',
  unknown: '미상',
};

/** 이름을 밝혀도 되는 상태인가. */
const named = (st) => st === 'visited' || st === 'known';

export function worldMap(state) {
  const wrap = el('div', 'map-block');
  wrap.appendChild(el('p', 'type-head', '세계 — 1897'));

  const svg = svgEl('svg', {
    viewBox: '0 0 100 100',
    class: 'map-svg world',
    role: 'img',
    'aria-label': '세계 지도',
  });

  // 위경선 격자. 진짜 대륙 대신 좌표계만 그린다 —
  // 이 시대의 탐사 도면이 실제로 그렇게 생겼다.
  for (let i = 1; i < 6; i++) {
    svg.appendChild(
      svgEl('line', { x1: 0, y1: i * 16.6, x2: 100, y2: i * 16.6, class: 'map-grid' }),
    );
    svg.appendChild(
      svgEl('line', { x1: i * 16.6, y1: 0, x2: i * 16.6, y2: 100, class: 'map-grid' }),
    );
  }
  svg.appendChild(svgEl('line', { x1: 0, y1: 50, x2: 100, y2: 50, class: 'map-equator' }));
  const eq = svgEl('text', { x: 1.5, y: 48.5, class: 'map-axis' });
  eq.textContent = '적도';
  svg.appendChild(eq);

  const known = [];
  for (const site of WORLD_SITES) {
    const st = siteState(site, state);
    known.push({ site, st });

    const g = svgEl('g', { class: `map-node world-${st}` });
    if (st === 'visited') {
      g.appendChild(svgEl('circle', { cx: site.x, cy: site.y, r: 4.4, class: 'map-halo' }));
      g.appendChild(svgEl('circle', { cx: site.x, cy: site.y, r: 2.2 }));
    } else if (st === 'known') {
      g.appendChild(
        svgEl('circle', { cx: site.x, cy: site.y, r: 2.6, class: 'map-target' }),
      );
      g.appendChild(svgEl('circle', { cx: site.x, cy: site.y, r: 0.9 }));
    } else {
      g.appendChild(svgEl('circle', { cx: site.x, cy: site.y, r: 1.4 }));
    }

    const label = svgEl('text', {
      x: site.x,
      y: site.y - 5,
      class: 'map-label',
      'text-anchor': site.x > 70 ? 'end' : site.x < 30 ? 'start' : 'middle',
    });
    // 소문이든 미상이든, 아직 짚어내지 못한 곳은 이름을 갖지 않는다.
    label.textContent = named(st) ? site.short || site.name : '?';
    g.appendChild(label);
    svg.appendChild(g);
  }

  wrap.appendChild(svg);

  // 지도 아래의 목록 — 좌표만으로는 읽히지 않는 것을 글로 적는다.
  const order = { visited: 0, known: 1, rumor: 2, unknown: 3 };
  known.sort((a, b) => order[a.st] - order[b.st]);
  for (const { site, st } of known) {
    const li = el('div', `list-item site-${st}`);
    const top = el('div', 'li-top');
    top.appendChild(el('span', 'li-name', named(st) ? site.name : '이름 없는 지점'));
    top.appendChild(el('span', 'li-meta', WORLD_STATE_LABEL[st]));
    li.appendChild(top);
    li.appendChild(
      el(
        'p',
        'li-desc',
        named(st) ? site.note : st === 'rumor' ? '아직 소문뿐이다.' : '지도 위의 좌표 하나. 그뿐이다.',
      ),
    );
    wrap.appendChild(li);
  }

  return wrap;
}

export function mapPanel(state, episode) {
  const frag = document.createDocumentFragment();
  frag.appendChild(fieldMap(state, episode));
  frag.appendChild(worldMap(state));
  return frag;
}
