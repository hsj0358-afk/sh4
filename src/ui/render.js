// 이벤트 → DOM. GM 엔진이 뱉은 이벤트를 로그에 그린다.

import { CLUES } from '../content/clues.js';
import { OUTCOME_LABEL } from '../engine/dice.js';
import { dangerLabel } from '../engine/state.js';

const EXIT_LABEL = {
  win: '상대가 물러났다',
  parley: '말이 통했다',
  escape: '빠져나왔다',
  overrun: '제압당했다',
};

const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
};

function paragraphs(container, lines, stagger = true) {
  lines.forEach((line, i) => {
    const p = el('p', null, String(line));
    if (stagger) p.style.animationDelay = `${Math.min(i * 110, 550)}ms`;
    container.appendChild(p);
  });
}

function sceneMark(ev) {
  const wrap = el('div', 'scene-mark');
  const rule = el('div', 'rule');
  rule.appendChild(el('span', 'place', ev.location));
  wrap.appendChild(rule);
  wrap.appendChild(
    el('div', 'when', `${ev.date} · ${ev.time} · 위험 ${dangerLabel(ev.danger)}`),
  );
  return wrap;
}

/**
 * 장면 하나를 접을 수 있는 블록으로 만든다 (기획서 15절 "로그는 접기 기능").
 * 머리말을 누르면 그 장면의 기록이 통째로 접힌다.
 */
export function createSceneBlock(ev) {
  const section = el('section', 'scene-block');
  section.dataset.scene = ev.id;

  const head = el('button', 'block-head');
  head.type = 'button';
  head.setAttribute('aria-expanded', 'true');
  head.appendChild(sceneMark(ev));

  const summary = el('span', 'block-summary');
  head.appendChild(summary);
  section.appendChild(head);

  const body = el('div', 'block-body');
  section.appendChild(body);

  const setCollapsed = (collapsed) => {
    section.dataset.collapsed = String(collapsed);
    head.setAttribute('aria-expanded', String(!collapsed));
    const count = body.childElementCount;
    summary.textContent = collapsed ? `기록 ${count}개 — 눌러서 펼치기` : '';
  };

  head.addEventListener('click', () => {
    setCollapsed(section.dataset.collapsed !== 'true');
  });

  setCollapsed(false);
  return { section, body, setCollapsed };
}

export function renderEvent(log, ev) {
  const node = build(ev);
  if (!node) return null;
  node.classList.add('entry');
  log.appendChild(node);
  return node;
}

function build(ev) {
  switch (ev.type) {
    case 'scene':
      return sceneMark(ev);

    case 'narration': {
      const wrap = el('div', `narration${ev.tone ? ` ${ev.tone}` : ''}`);
      paragraphs(wrap, ev.text);
      return wrap;
    }

    case 'player': {
      const wrap = el('div', 'player-act');
      wrap.appendChild(el('span', 'who', ev.free ? '당신의 행동' : '선택'));
      wrap.appendChild(document.createTextNode(ev.text));
      return wrap;
    }

    case 'pressure': {
      const wrap = el('div', 'pressure');
      wrap.appendChild(el('span', 'tag', '상황 변화'));
      paragraphs(wrap, ev.text);
      return wrap;
    }

    case 'checkRequest': {
      const card = el('div', 'check-card');
      const head = el('div', 'ct-head');
      head.appendChild(el('span', 'ct-name', `${ev.label}`));
      head.appendChild(el('span', 'ct-diff', ev.difficulty));
      card.appendChild(head);

      const bd = el('div', 'breakdown');
      for (const b of ev.breakdown) {
        const sign = b.value >= 0 ? '+' : '';
        bd.appendChild(
          el('span', `chip ${b.value < 0 ? 'minus' : 'plus'}`, `${b.label} ${sign}${b.value}`),
        );
      }
      if (!ev.breakdown.length) bd.appendChild(el('span', 'chip', '보정 없음'));
      card.appendChild(bd);

      const mod = ev.modifier >= 0 ? `+${ev.modifier}` : `${ev.modifier}`;
      const t = el('div', 'ct-target');
      t.innerHTML = `1D20 ${mod} · 목표값 <b>${ev.target}</b>`;
      card.appendChild(t);

      const adjust = [];
      if (ev.pressure > 0) adjust.push(`위험도 압박 +${ev.pressure}`);
      if (ev.difficultyShift) {
        adjust.push(`난이도 ${ev.difficultyShift > 0 ? '+' : ''}${ev.difficultyShift}`);
      }
      if (adjust.length) {
        card.appendChild(el('div', 'ct-pressure', `목표값 조정 — ${adjust.join(' · ')}`));
      }
      return card;
    }

    case 'roll': {
      const r = ev.result;
      const card = el('div', 'roll-card');
      card.dataset.outcome = r.outcome;
      const mod = r.modifier >= 0 ? `+ ${r.modifier}` : `− ${Math.abs(r.modifier)}`;
      card.appendChild(el('div', 'rc-eq', `🎲 ${ev.label}`));
      card.appendChild(el('span', 'rc-nat', String(r.natural)));
      card.appendChild(
        el('div', 'rc-eq', `${r.natural} ${mod} = ${r.total}　/　목표 ${r.target}`),
      );
      card.appendChild(el('div', null, '')).appendChild(
        el('span', 'rc-outcome', OUTCOME_LABEL[r.outcome]),
      );
      return card;
    }

    case 'notes': {
      if (!ev.notes.length) return null;
      const wrap = el('div', 'notes');
      ev.notes.forEach((n, i) => {
        const label = n.kind === 'clue' && n.clue ? `단서: ${CLUES[n.clue]?.title || n.clue}` : n.text;
        const chip = el('span', `note ${n.kind}`, label);
        chip.style.animationDelay = `${i * 70}ms`;
        wrap.appendChild(chip);
      });
      return wrap;
    }

    case 'clue': {
      const c = CLUES[ev.clue];
      if (!c) return null;
      const card = el('div', 'clue-card');
      card.appendChild(el('span', 'cl-tag', '수첩에 기록됨'));
      card.appendChild(el('h4', null, c.title));
      card.appendChild(el('p', null, c.text));
      return card;
    }

    case 'combatStart': {
      const wrap = el('div', 'combat-mark');
      wrap.appendChild(el('span', 'cm-label', '조우'));
      wrap.appendChild(el('div', 'cm-sub', `${ev.status.name} · ${ev.status.subtitle}`));
      return wrap;
    }

    case 'combatEnd': {
      const wrap = el('div', 'combat-mark end');
      wrap.appendChild(el('span', 'cm-label', EXIT_LABEL[ev.exit] || '전투 종료'));
      wrap.appendChild(el('div', 'cm-sub', `${ev.status.round}라운드 만에`));
      return wrap;
    }

    case 'combatRound':
      return null; // 상태는 하단 바가 보여준다. 로그에는 남기지 않는다.

    case 'end': {
      const card = el('div', 'end-card');
      card.appendChild(el('h3', null, ev.end.title));
      card.appendChild(el('p', null, ev.end.text));
      return card;
    }

    default:
      return null;
  }
}

/** 단서 획득 알림에는 카드도 함께 띄운다. */
export function clueCardsFor(notes) {
  return (notes || []).filter((n) => n.kind === 'clue' && n.clue).map((n) => n.clue);
}
