// 캠페인 — 에피소드 사이를 잇는 층.
//
// 한 지역이 끝나도 탐사자는 초기화되지 않는다. 몸도 마음도 짐도 그대로 다음 배에 오른다.
// 넘어가지 않는 것은 그 지역의 위험도뿐이다. 유적은 두고 왔으니까.

import { getEpisode, nextEpisodeId } from '../content/episodes/index.js';
import { applyEffects } from './state.js';

/**
 * 다음 에피소드로 넘어간다.
 * 상태는 유지하고, 지역에 매인 것만 정리한다.
 *
 * @returns {{ ok: boolean, episode?: object, notes?: Array }}
 */
export function advanceEpisode(state) {
  const nextId = nextEpisodeId(state.episode);
  if (!nextId) return { ok: false };

  const next = getEpisode(nextId);

  if (!state.visitedEpisodes) state.visitedEpisodes = [];
  if (state.episode && !state.visitedEpisodes.includes(state.episode)) {
    state.visitedEpisodes.push(state.episode);
  }

  // 지역에 매인 것들
  state.danger = 0;
  state.ended = null;
  state.episode = nextId;
  state.scene = next.start;

  // 여정 자체의 효과 — 이동에 걸린 시간과 회복.
  const notes = applyEffects(state, next.arrival || {});

  return { ok: true, episode: next, notes };
}

/** 이 상태에서 다음 장으로 갈 수 있는가. */
export function hasNextEpisode(state) {
  return !!nextEpisodeId(state.episode);
}

/** 캠페인 전체에서 몇 번째 장인가. */
export function chapterNumber(state) {
  return (state.visitedEpisodes?.length || 0) + 1;
}
