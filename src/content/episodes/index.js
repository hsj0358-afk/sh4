// 에피소드 등록소.
//
// 캠페인은 이 순서대로 흐른다. 각 에피소드는 끝에서 다음 에피소드를 가리키고,
// 플레이어의 상태(단서 · 동료 · 소지품 · 관계 플래그)는 그대로 넘어간다.

import luxor from './luxor.js';
import mesopotamia from './mesopotamia.js';

export const EPISODES = {
  [luxor.id]: luxor,
  [mesopotamia.id]: mesopotamia,
};

export const EPISODE_ORDER = [luxor.id, mesopotamia.id];

export const FIRST_EPISODE = EPISODE_ORDER[0];

export function getEpisode(id) {
  return EPISODES[id] || EPISODES[FIRST_EPISODE];
}

/** 이 에피소드 다음은 무엇인가. 마지막이면 null. */
export function nextEpisodeId(id) {
  const i = EPISODE_ORDER.indexOf(id);
  return i >= 0 && i < EPISODE_ORDER.length - 1 ? EPISODE_ORDER[i + 1] : null;
}
