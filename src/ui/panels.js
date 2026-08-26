// 보조 메뉴 — 상태 / 소지품 / 기록(로그북) / 동행.
// 전부 하단 시트 하나를 재사용한다. 한 손으로 열고 닫을 수 있어야 한다.

import { STATS } from '../content/stats.js';
import { ITEMS } from '../content/items.js';
import { CLUES } from '../content/clues.js';
import { COMPANIONS } from '../content/companions.js';
import { ENCOUNTERS } from '../content/encounters.js';
import { ENDINGS } from '../content/endings.js';
import { PROFESSIONS } from '../content/professions.js';
import { EPISODES } from '../content/episodes/index.js';
import { getDifficulty, DIFFICULTIES } from '../content/difficulty.js';
import { conditionPenalty, dangerLabel, formatClock } from '../engine/state.js';
import { progress } from '../engine/archive.js';
import { isShaky, warnings } from '../engine/betrayal.js';

const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
};

function pips(value, max = 5) {
  const wrap = el('span', 'pips');
  for (let i = 0; i < max; i++) wrap.appendChild(el('i', `pip${i < value ? ' on' : ''}`));
  return wrap;
}

function item(name, meta, desc, bonus) {
  const li = el('div', 'list-item');
  const top = el('div', 'li-top');
  top.appendChild(el('span', 'li-name', name));
  if (meta) top.appendChild(el('span', 'li-meta', meta));
  li.appendChild(top);
  if (desc) li.appendChild(el('p', 'li-desc', desc));
  if (bonus) li.appendChild(el('p', 'li-bonus', bonus));
  return li;
}

export function statusPanel(state) {
  const frag = document.createDocumentFragment();
  const clock = formatClock(state.tick);

  const diff = getDifficulty(state.difficulty);
  frag.appendChild(
    item(
      state.char.name,
      state.char.profession,
      state.char.perk,
      `${clock.date} ${clock.time} · 위험도 ${state.danger} (${dangerLabel(state.danger)})`,
    ),
  );

  const diffLine = el('div', 'list-item');
  diffLine.appendChild(el('p', 'li-desc', `난이도 — ${diff.name}`));
  diffLine.appendChild(
    el(
      'p',
      'li-bonus',
      diff.targetShift === 0 && diff.damageScale === 1
        ? '규칙 그대로.'
        : `모든 판정 목표값 ${diff.targetShift >= 0 ? '+' : ''}${diff.targetShift} · 받는 피해 ×${diff.damageScale}`,
    ),
  );
  frag.appendChild(diffLine);

  frag.appendChild(el('p', 'type-head', '능력치'));
  const grid = el('div', 'stat-grid');
  for (const s of STATS) {
    const row = el('div', 'stat-row');
    row.appendChild(el('span', 'name', s.id));
    row.appendChild(pips(state.char.stats[s.id]));
    grid.appendChild(row);
  }
  frag.appendChild(grid);

  frag.appendChild(el('p', 'type-head', '상태'));
  const cond = conditionPenalty(state);
  const body = el('div', 'list-item');
  body.appendChild(
    el('p', 'li-desc', `체력 ${state.hp}/${state.maxHp} · 정신력 ${state.san}/${state.maxSan}`),
  );
  body.appendChild(
    el(
      'p',
      cond.value ? 'li-bonus' : 'li-desc',
      cond.value
        ? `${cond.reasons.join(' · ')} — 모든 판정 ${cond.value}`
        : '판정에 영향을 주는 이상 없음.',
    ),
  );
  frag.appendChild(body);

  if (state.rolls.length) {
    frag.appendChild(el('p', 'type-head', '최근 판정'));
    for (const r of state.rolls.slice(-5).reverse()) {
      frag.appendChild(
        item(r.label, `${r.natural} → ${r.total}/${r.target}`, null, null),
      );
    }
  }
  return frag;
}

const TYPE_LABEL = {
  gear: '일반 장비',
  supply: '소모품',
  relic: '유적 유물',
  special: '특별',
};

export function inventoryPanel(state, onUse) {
  const frag = document.createDocumentFragment();
  if (!state.inventory.length) {
    frag.appendChild(el('p', 'empty', '가방은 비어 있다.'));
    return frag;
  }

  const groups = { gear: [], supply: [], relic: [], special: [] };
  for (const inv of state.inventory) {
    const def = ITEMS[inv.name];
    (groups[def?.type || 'gear'] || groups.gear).push({ inv, def });
  }

  for (const [type, list] of Object.entries(groups)) {
    if (!list.length) continue;
    frag.appendChild(el('p', 'type-head', TYPE_LABEL[type]));
    for (const { inv, def } of list) {
      const meta = inv.uses === null ? '' : `남은 사용 ${inv.uses}`;
      const bonus = def?.bonus
        ? `${def.bonus.tags.join('·')} 판정 +${def.bonus.value}`
        : def?.note || '';
      const node = item(inv.name, meta, def?.desc, bonus);
      if (def?.use && onUse) {
        const btn = el('button', 'btn', `사용하기`);
        btn.style.marginTop = '10px';
        btn.addEventListener('click', () => onUse(inv.name));
        node.appendChild(btn);
      }
      frag.appendChild(node);
    }
  }
  return frag;
}

export function codexPanel(state) {
  const frag = document.createDocumentFragment();
  if (!state.clues.length) {
    frag.appendChild(el('p', 'empty', '아직 적어둔 것이 없다.\n전부 머릿속에만 있다.'));
    return frag;
  }
  const tiers = [
    ['core', '중심 미스터리'],
    ['field', '현장 단서'],
    ['lead', '다음 행선지'],
  ];
  for (const [tier, label] of tiers) {
    const list = state.clues.filter((id) => CLUES[id]?.tier === tier);
    if (!list.length) continue;
    frag.appendChild(el('p', 'type-head', label));
    for (const id of list) {
      frag.appendChild(item(CLUES[id].title, null, CLUES[id].text));
    }
  }
  return frag;
}

/**
 * 관계 상태를 한 줄로 읽는다.
 * 수치를 그대로 보여주는 것만으로는 그 숫자가 무슨 뜻인지 알 수 없다.
 */
function relationLine(c) {
  if (!c.present) return { text: '더 이상 곁에 없다.', cls: 'li-bonus' };
  if (isShaky(c)) return { text: '언제 등을 돌려도 이상하지 않다.', cls: 'li-warn' };
  if (c.trust >= 4 && c.affinity >= 4) {
    return { text: '이 사람은 당신을 위해 남는다. 이유를 묻지 않고.', cls: 'li-bonus' };
  }
  if (c.trust <= 1) return { text: '당신의 판단을 믿지 않는다. 아직 따라올 뿐이다.', cls: 'li-warn' };
  if (c.affinity <= 1) return { text: '일로 만난 사이다. 그 이상은 아니다.', cls: 'li-desc' };
  return { text: '함께 걷는 데 무리가 없다.', cls: 'li-desc' };
}

export function partyPanel(state) {
  const frag = document.createDocumentFragment();
  const list = Object.values(state.companions);
  if (!list.length) {
    frag.appendChild(el('p', 'empty', '당신은 혼자다.'));
    return frag;
  }

  // 뒤통수를 치지 않는다. 흔들리는 사람이 있으면 먼저 말해 준다.
  const warn = warnings(state);
  if (warn.length) {
    frag.appendChild(el('p', 'type-head', '관계 경고'));
    for (const w of warn) {
      const node = el('div', 'list-item warn');
      node.appendChild(el('p', 'li-warn', w.text));
      node.appendChild(
        el('p', 'li-desc', '신뢰도나 호감도를 올리면 되돌릴 수 있다. 떠나기 전까지는.'),
      );
      frag.appendChild(node);
    }
  }

  frag.appendChild(el('p', 'type-head', '동행'));
  for (const c of list) {
    const base = COMPANIONS[c.id];
    const node = item(
      c.name,
      c.present ? `체력 ${c.hp}/${c.maxHp}` : '이탈',
      base?.desc,
      base?.skill,
    );
    const rel = el('div', 'rel-bars');
    const a = el('span', 'rel');
    a.appendChild(el('span', null, '호감도'));
    a.appendChild(pips(c.affinity));
    const t = el('span', 'rel');
    t.appendChild(el('span', null, '신뢰도'));
    t.appendChild(pips(c.trust));
    rel.appendChild(a);
    rel.appendChild(t);
    node.appendChild(rel);

    const line = relationLine(c);
    node.appendChild(el('p', line.cls, line.text));
    if (c.injured) node.appendChild(el('p', 'li-bonus', '부상 — 지원 보정 감소'));
    frag.appendChild(node);
  }
  return frag;
}

// ── 도감 ─────────────────────────────────────────────────────────
//
// 한 판에서 볼 수 있는 것은 전체의 일부다. 세 대륙을 다 도는 회차라도
// 고르지 않은 항로, 열지 않은 문, 만나지 않은 사람이 남는다.
// 도감은 그 남은 것의 윤곽을 보여준다 — 내용은 감추고, 자리만.

const RELIC_TYPES = ['relic', 'special'];

export const ARCHIVE_TOTALS = {
  clues: Object.keys(CLUES).length,
  items: Object.keys(ITEMS).length,
  endings: ENDINGS.length,
  companions: Object.keys(COMPANIONS).length,
  encounters: Object.keys(ENCOUNTERS).length,
  professions: PROFESSIONS.length,
};

function progressRow(label, p) {
  const row = el('div', 'arc-row');
  const head = el('div', 'arc-head');
  head.appendChild(el('span', 'arc-name', label));
  head.appendChild(el('span', 'arc-count', `${p.have}/${p.all}`));
  row.appendChild(head);
  const bar = el('div', 'bar');
  const fill = el('i');
  fill.style.width = `${p.pct}%`;
  bar.appendChild(fill);
  row.appendChild(bar);
  return row;
}

/**
 * 본 것은 제목과 내용을, 못 본 것은 숫자로만 남긴다.
 *
 * 처음에는 못 본 항목도 한 줄씩 자리를 잡아 두었는데, 단서 24개 중 20개가
 * 똑같은 회색 줄로 늘어서니 도감이 아니라 빈칸 목록이었다.
 * 남은 것이 몇 개인지만 알면 그 다음은 플레이어가 알아서 찾는다.
 */
function collectedList(entries, known, unseenText) {
  const frag = document.createDocumentFragment();
  const seen = entries.filter((e) => known.includes(e.id));

  for (const e of seen) frag.appendChild(item(e.title, e.meta, e.text));

  const left = entries.length - seen.length;
  if (left) {
    const node = el('div', 'list-item locked');
    node.appendChild(el('span', 'li-name', `─ ─ ─  ${left}`));
    node.appendChild(el('p', 'li-desc', unseenText));
    frag.appendChild(node);
  }
  return frag;
}

export function archivePanel(archive) {
  const frag = document.createDocumentFragment();
  const p = progress(archive, ARCHIVE_TOTALS);

  const head = el('div', 'list-item');
  head.appendChild(
    el(
      'p',
      'li-desc',
      archive.runs
        ? `탐사 ${archive.runs}회 · 끝까지 간 것 ${archive.finished}회 · 한 회차 최다 단서 ${archive.bestClueCount}개`
        : '아직 아무 기록도 없다. 첫 배를 타면 여기부터 채워진다.',
    ),
  );
  frag.appendChild(head);

  const relics = Object.entries(ITEMS).filter(([, def]) => RELIC_TYPES.includes(def.type));
  const foundRelics = archive.items.filter((n) => RELIC_TYPES.includes(ITEMS[n]?.type));

  frag.appendChild(el('p', 'type-head', '수집 진행률'));
  const bars = el('div', 'arc-bars');
  bars.appendChild(progressRow('단서', p.clues));
  bars.appendChild(
    progressRow('유물', {
      have: foundRelics.length,
      all: relics.length,
      pct: Math.round((foundRelics.length / relics.length) * 100),
    }),
  );
  bars.appendChild(progressRow('소지품 전체', p.items));
  bars.appendChild(progressRow('결말', p.endings));
  bars.appendChild(progressRow('동행', p.companions));
  bars.appendChild(progressRow('조우', p.encounters));
  bars.appendChild(progressRow('직업', p.professions));
  frag.appendChild(bars);

  // 유물 도감 — 유적에서 나온 것만. 일반 장비는 소지품 패널의 몫이다.
  frag.appendChild(el('p', 'type-head', '유물 도감'));
  frag.appendChild(
    collectedList(
      relics.map(([name, def]) => ({
        id: name,
        title: name,
        meta: TYPE_LABEL[def.type],
        text: def.desc,
      })),
      archive.items,
      '아직 어느 유적엔가 놓여 있다.',
    ),
  );

  frag.appendChild(el('p', 'type-head', '결말'));
  frag.appendChild(
    collectedList(
      ENDINGS.map((e) => ({ id: e.id, title: e.title, text: e.text.split('\n')[0] })),
      archive.endings,
      '아직 도달하지 않은 끝.',
    ),
  );

  frag.appendChild(el('p', 'type-head', '동행'));
  frag.appendChild(
    collectedList(
      Object.values(COMPANIONS).map((c) => ({
        id: c.id,
        title: c.name,
        meta: c.role,
        text: c.desc,
      })),
      archive.companions,
      '아직 만나지 않은 사람.',
    ),
  );

  frag.appendChild(el('p', 'type-head', '조우'));
  frag.appendChild(
    collectedList(
      Object.entries(ENCOUNTERS).map(([id, e]) => ({
        id,
        title: e.name,
        meta: e.subtitle,
        text: e.desc || e.subtitle,
      })),
      archive.encounters,
      '아직 마주치지 않은 상대.',
    ),
  );

  frag.appendChild(el('p', 'type-head', '단서'));
  frag.appendChild(
    collectedList(
      Object.entries(CLUES).map(([id, c]) => ({ id, title: c.title, text: c.text })),
      archive.clues,
      '아직 모르는 것.',
    ),
  );

  frag.appendChild(el('p', 'type-head', '지역'));
  frag.appendChild(
    collectedList(
      Object.values(EPISODES).map((e) => ({ id: e.id, title: e.title, text: e.subtitle || '' })),
      archive.episodes,
      '아직 밟지 않은 땅.',
    ),
  );

  // ── 로그북 ────────────────────────────────────────────────
  frag.appendChild(el('p', 'type-head', '로그북'));
  if (!archive.runLog.length) {
    frag.appendChild(el('p', 'empty', '아직 끝난 탐사가 없다.'));
  } else {
    for (const r of archive.runLog) {
      frag.appendChild(
        item(
          `${r.n}회차 — ${r.name}`,
          `${r.chapters}장 · 단서 ${r.clues}`,
          r.title,
          `${r.profession} · ${DIFFICULTIES[r.difficulty]?.name || r.difficulty}`,
        ),
      );
    }
  }

  return frag;
}

export const PANEL_TITLES = {
  status: '탐사자 기록',
  inventory: '소지품',
  codex: '수첩',
  party: '동행',
  map: '지도',
  archive: '도감',
  menu: '메뉴',
};
