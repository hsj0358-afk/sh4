// 줄거리 요약.
//
// 며칠 만에 돌아온 사람은 자기가 어디까지 왔는지 모른다. 이어하기를 누르면
// 장면 서술이 다시 나오는데, 그 서술은 "지금 이 방"만 말한다 — 왜 이 방에
// 있는지는 말하지 않는다.
//
// 그래서 다섯 줄쯤을 만든다. 요약은 짧아야 한다. 길면 그것도 읽을 것이 되고,
// 읽을 것을 하나 더 만들자고 요약을 붙이는 게 아니다.
//
// 원칙: **상태에서 만든다.** 장면마다 요약문을 적어 두면 콘텐츠가 두 배가 되고
// 그중 절반은 곧 상태와 어긋난다.

import { CLUES } from '../content/clues.js';
import { EPISODES } from '../content/episodes/index.js';
import { getItem } from '../content/items.js';
import { hoursSince } from '../clock.js';
import { subj, obj, and } from '../korean.js';

/** 요약에 이름을 올릴 만한 물건. 횃불은 줄거리가 아니다. */
const WORTH_NAMING = ['relic', 'special'];

/** 지역 이름에서 장 번호를 뗀다 — 「에피소드 2 — 두 강 사이의 문」 → 「두 강 사이의 문」 */
function placeName(id) {
  const t = EPISODES[id]?.title || '';
  return t.replace(/^에피소드\s*\d+\s*—\s*/, '') || id;
}

/**
 * 이름을 늘어놓고 마지막에 조사를 붙인다.
 *   ['나디아 하룬', '올리버 핀치'] + subj  →  '나디아 하룬과 올리버 핀치가'
 * 조사는 마지막 이름을 따라간다. 그래서 붙이는 일도 마지막에 한 번만 한다.
 */
function listWith(names, particle) {
  if (!names.length) return '';
  const head = names.slice(0, -1).map((n) => and(n));
  const tail = particle(names[names.length - 1]);
  return [...head, tail].join(' ');
}

/**
 * 지금까지의 줄거리를 몇 줄로.
 *
 * @param {object} state
 * @param {object} episode 지금 장
 * @returns {string[]} 없으면 빈 배열
 */
export function recap(state, episode) {
  if (!state) return [];
  const lines = [];

  // 1. 언제, 몇 번째 장인가
  const days = Math.max(1, Math.round(hoursSince(state.tick) / 24));
  const chapter = (state.visitedEpisodes?.length || 0) + 1;
  const here = placeName(state.episode || episode?.id);
  // 며칠 만에 돌아온 사람은 자기가 어느 판을 열었는지도 헷갈린다.
  // 슬롯이 셋이면 더 그렇다. 그래서 첫 줄에 이름과 직업을 적는다.
  const who = state.char?.name;
  if (who) lines.push(`${who}, ${state.char.profession}.`);
  lines.push(`제 ${chapter} 장 「${here}」. 런던을 떠난 지 ${days}일째.`);

  // 2. 어디를 지나왔나 — 두 번째 장부터만 의미가 있다
  const past = (state.visitedEpisodes || []).map(placeName);
  if (past.length) lines.push(`${listWith(past, obj)} 지나왔다.`);

  // 3. 누가 곁에 있나
  const with_ = Object.values(state.companions || {}).filter((c) => c.present);
  const lost = Object.values(state.companions || {}).filter((c) => !c.present);
  lines.push(
    with_.length ? `곁에는 ${listWith(with_.map((c) => c.name), subj)} 있다.` : '지금은 혼자다.',
  );
  if (lost.length) {
    lines.push(`돌아오지 못한 사람 — ${lost.map((c) => c.name).join(', ')}.`);
  }

  // 4. 손에 쥔 것 중 이야기가 되는 것
  const relics = (state.inventory || [])
    .map((i) => i.name)
    .filter((n) => WORTH_NAMING.includes(getItem(n)?.type));
  if (relics.length) lines.push(`가방에는 ${listWith(relics, subj)} 있다.`);

  // 5. 마지막으로 수첩에 적은 것
  const last = state.clues?.[state.clues.length - 1];
  if (last && CLUES[last]) {
    lines.push(`마지막으로 적은 것 — 「${CLUES[last].title}」.`);
  }

  // 6. 몸이 성치 않으면 그것도 알려 준다
  const hurt = state.hp <= Math.ceil(state.maxHp * 0.5);
  const shaken = state.san <= Math.ceil(state.maxSan * 0.5);
  if (hurt && shaken) lines.push('몸도 정신도 절반 아래다. 무리하면 돌아오지 못한다.');
  else if (hurt) lines.push('상처가 아물지 않았다.');
  else if (shaken) lines.push('본 것이 아직 가라앉지 않았다.');

  return lines;
}
