// 보조 메뉴 — 상태 / 소지품 / 기록(로그북) / 동행.
// 전부 하단 시트 하나를 재사용한다. 한 손으로 열고 닫을 수 있어야 한다.

import { STATS } from '../content/stats.js';
import { ITEMS } from '../content/items.js';
import { CLUES } from '../content/clues.js';
import { COMPANIONS } from '../content/companions.js';
import { conditionPenalty, dangerLabel, formatClock } from '../engine/state.js';

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

  frag.appendChild(
    item(
      state.char.name,
      state.char.profession,
      state.char.perk,
      `${clock.date} ${clock.time} · 위험도 ${state.danger} (${dangerLabel(state.danger)})`,
    ),
  );

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

export function partyPanel(state) {
  const frag = document.createDocumentFragment();
  const list = Object.values(state.companions);
  if (!list.length) {
    frag.appendChild(el('p', 'empty', '당신은 혼자다.'));
    return frag;
  }
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
    if (c.injured) node.appendChild(el('p', 'li-bonus', '부상 — 지원 보정 감소'));
    frag.appendChild(node);
  }
  return frag;
}

export const PANEL_TITLES = {
  status: '탐사자 기록',
  inventory: '소지품',
  codex: '수첩',
  party: '동행',
  menu: '메뉴',
};
