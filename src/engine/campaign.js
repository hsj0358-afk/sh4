// 캠페인 — 에피소드 사이를 잇는 층.
//
// 한 지역이 끝나도 탐사자는 초기화되지 않는다. 몸도 마음도 짐도 그대로 다음 배에 오른다.
// 넘어가지 않는 것은 그 지역의 위험도뿐이다. 유적은 두고 왔으니까.
//
// 장과 장 사이에는 막간이 있다. 어느 항로로 갈 것인가 — 그것이 시간과 몸과
// 아는 것을 서로 다르게 바꾼다(기획서 18절 '분기형 캠페인').

import { getEpisode, nextEpisodeId } from '../content/episodes/index.js';
import { getInterlude, availableRoutes } from '../content/interludes.js';
import { applyEffects } from './state.js';
import { createRng } from './rng.js';
import { checkBetrayal, MOMENT } from './betrayal.js';

/** 이 상태에서 다음 장으로 갈 수 있는가. */
export function hasNextEpisode(state) {
  return !!nextEpisodeId(state.episode);
}

/** 캠페인 전체에서 몇 번째 장인가. */
export function chapterNumber(state) {
  return (state.visitedEpisodes?.length || 0) + 1;
}

/**
 * 다음 장으로 떠나기 전의 막간.
 * @returns {{ title, intro, routes } | null} 고를 것이 없으면 null
 */
export function interludeFor(state) {
  const nextId = nextEpisodeId(state.episode);
  if (!nextId) return null;
  const interlude = getInterlude(nextId);
  if (!interlude) return null;

  const routes = availableRoutes(interlude, state);
  if (routes.length < 2) return null; // 고를 것이 하나뿐이면 선택이 아니다

  return { episodeId: nextId, title: interlude.title, intro: interlude.intro, routes };
}

/**
 * 다음 에피소드로 넘어간다.
 * 상태는 유지하고, 지역에 매인 것만 정리한다.
 *
 * @param {object} state
 * @param {object} [opts]
 * @param {string} [opts.routeId] 막간에서 고른 항로
 * @returns {{ ok, episode?, notes?, route?, betrayal? }}
 */
export function advanceEpisode(state, opts = {}) {
  const nextId = nextEpisodeId(state.episode);
  if (!nextId) return { ok: false };

  const next = getEpisode(nextId);

  // 판정에 쓰는 난수는 세이브에 실려 있는 그 줄기여야 한다. 이어하기가 같은 판이 되도록.
  const rng = createRng(state.seed);
  if (state.rngState !== undefined) rng.setState(state.rngState);

  if (!state.visitedEpisodes) state.visitedEpisodes = [];
  if (state.episode && !state.visitedEpisodes.includes(state.episode)) {
    state.visitedEpisodes.push(state.episode);
  }

  // 지역에 매인 것들
  state.danger = 0;
  state.calm = 0;
  state.ended = null;
  state.episode = nextId;
  state.scene = next.start;

  // 떠나기 전이 등을 돌리기 가장 쉬운 때다. 짐을 싸는 사람은 티가 나지 않는다.
  const betrayal = checkBetrayal(state, rng, MOMENT.CHAPTER);
  const betrayalNotes = betrayal ? applyEffects(state, betrayal.effects) : [];

  // 항로를 골랐으면 그 효과가 여정을 대신한다. 아니면 에피소드의 기본 여정.
  const interlude = getInterlude(nextId);
  const route = opts.routeId
    ? (interlude?.routes || []).find((r) => r.id === opts.routeId)
    : null;

  const notes = applyEffects(state, route ? route.effects : next.arrival || {});

  state.rngState = rng.getState();
  return { ok: true, episode: next, notes: [...betrayalNotes, ...notes], route, betrayal };
}
