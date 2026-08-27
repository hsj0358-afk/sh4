// 경쟁자 시계.
//
// 서사는 다섯 번 말한다 — "크레인이 앞서간다", "물이 빠지는 계절은 짧다",
// "우기까지 열흘". 그런데 규칙에는 그 말이 없었다. state.tick 을 읽는 곳은
// 서술의 톤(아침/밤)을 고르는 세 군데뿐이었고, 시간을 써서 잃는 것은 없었다.
//
// 시간에 값이 없으면 두 가지가 무너진다.
//
//   1. 반복 가능한 판정을 대성공이 나올 때까지 누르는 것이 지배 전략이 된다.
//      실패의 비용이 시간뿐인데 그 시간이 공짜라면, 실패는 비용이 아니다.
//   2. 야영·회복·항로 선택이 판단이 아니라 취향이 된다. 잃는 것이 없으니까.
//
// 그래서 시계를 하나 더 놓는다. 이것은 위험도와 다른 종류의 압박이다 —
// 위험도는 "이 방이 나를 알아챘는가"이고, 이것은 "저 사람이 먼저 도착하는가"다.
// 위험도는 조용히 있으면 식지만, 이것은 식지 않는다.
//
// 한 장에 한 번씩 정산한다. 장이 바뀌면 경주도 다시 시작한다 —
// 같은 문을 향해 두 배가 다시 떠나는 것이므로.

import { getItem } from '../content/items.js';

export const RIVAL_MAX = 100;

/** 이 아래면 아직 여유가 있다. 넘으면 화면에 한 줄 뜬다. */
export const RIVAL_WARN = 45;

/**
 * 이 아래에서는 줄을 아예 그리지 않는다.
 *
 * 출항 30분 만에 「크레인 ─ 소식 없음」이 뜨면, 그것은 압박이 아니라 잡음이다.
 * 비어 있는 게이지는 아무 말도 하지 않으면서 자리만 차지한다.
 * 반나절쯤 지나 그가 실제로 셈에 들어올 때 나타나야 한 줄값을 한다.
 */
export const RIVAL_VISIBLE = 12;

/** 이 위에서 장이 끝나면 그가 먼저 가져간다. */
export const RIVAL_TOLL = 70;

/**
 * 1틱(30분)마다 그가 얼마나 앞서는가.
 *
 * 한 장 안에서 흐르는 시간은 실측 40~69틱(범위 8~147)이다.
 * 0.5 로 잡으면 평균적인 탐사는 20~35 에 머물고, 꼼꼼히 훑는 탐사(140틱 이상)가
 * 문턱에 닿는다. 서두르는 사람에게 상을 주는 것이 아니라,
 * 될 때까지 누르는 사람에게 값을 물리는 눈금이다.
 */
const PER_TICK = 0.5;

/** 하루는 48틱. 항로의 길이 차이를 날수로 옮길 때 쓴다. */
const TICKS_PER_DAY = 48;

/**
 * 지금 경주 중인가.
 *
 * 크레인과 같은 편이 되면 경주가 끝난다. 이것이 협상 노선의 값이다 —
 * 지금까지 협상은 플래그 하나만 남기고 아무것도 바꾸지 않았다.
 */
export function racing(state) {
  return !state.flags?.craneAlly;
}

/** 시간이 흐른 만큼 그가 나아간다. 되돌아오지 않는다. */
export function tickRival(state, ticks) {
  if (!ticks || ticks <= 0 || !racing(state)) return 0;
  const before = state.rival || 0;
  state.rival = Math.min(RIVAL_MAX, before + ticks * PER_TICK);
  return state.rival - before;
}

/**
 * 항로가 정하는 출발선.
 *
 * 가장 빠른 배를 탄 사람이 0 에서 시작하고, 느린 배는 그 차이만큼 뒤에서 시작한다.
 * 8주짜리 런던 경유가 지하 보관고를 보여 주는 대신 무엇을 받아 가는지가
 * 여기서 정해진다. 지금까지 그 선택은 시간을 쓰고도 아무것도 잃지 않았다.
 */
export function rivalStart(interlude, route, state) {
  if (!racing(state) || !route?.effects?.time) return 0;
  const times = (interlude?.routes || []).map((r) => r.effects?.time || 0).filter(Boolean);
  if (!times.length) return 0;
  const behind = (route.effects.time - Math.min(...times)) / TICKS_PER_DAY;
  return Math.min(RIVAL_MAX, Math.round(behind));
}

/** 지금 그가 어디쯤인가. UI 와 콘텐츠가 같은 말을 쓰도록 여기서 정한다. */
export function rivalLabel(v = 0) {
  if (v < 20) return '소식 없음';
  if (v < RIVAL_WARN) return '같은 강 위';
  if (v < RIVAL_TOLL) return '하루 앞';
  if (v < RIVAL_MAX) return '이미 안에';
  return '늦었다';
}

/** 색과 경고를 고르는 데 쓴다. */
export function rivalStage(v = 0) {
  if (v >= RIVAL_TOLL) return 'lost';
  if (v >= RIVAL_WARN) return 'near';
  return 'calm';
}

/**
 * 문턱을 넘는 순간의 한 줄.
 *
 * 배신과 같은 원칙이다 — 예고된다. 장이 끝나고 나서야 "빼앗겼습니다"라고
 * 말하면 그것은 결과가 아니라 함정이다. 넘어가는 순간에 알려 주고,
 * 알려 준 뒤에는 서두를 시간을 남겨 둔다.
 */
export function rivalCrossing(state) {
  if (!racing(state)) return null;
  const v = state.rival || 0;
  const stage = rivalStage(v);
  if (stage === 'calm') return null;

  const key = `rivalWarned:${stage}`;
  if (state.flags[key]) return null;
  state.flags[key] = true;

  return stage === 'near'
    ? [
        '능선 위로 등불 행렬이 지나간다. 일정한 간격, 훈련된 걸음.',
        '그들은 자지 않는다. 당신이 여기서 보낸 시간만큼 그들은 걸었다.',
      ]
    : [
        '앞선 야영지의 재가 아직 따뜻하다.',
        '크레인은 이미 안에 있다. 지금부터 당신이 찾는 것은, 그가 두고 간 것뿐이다.',
      ];
}

/** 그가 가져갈 만한 것. 유적에서 나온 것만 노린다. */
const WORTH_TAKING = ['relic', 'special'];

/**
 * 장이 끝날 때의 정산.
 *
 * 앞선 채로 장을 마치면 그가 먼저 손을 댄다. 빼앗기는 것이 아니라 늦은 것이고,
 * 그래서 서술도 싸움이 아니라 전보 한 줄로 온다.
 *
 * @returns {{ text:string[], effects:object } | null}
 */
export function rivalToll(state) {
  if (!racing(state) || (state.rival || 0) < RIVAL_TOLL) return null;

  const prize = state.inventory.find((i) => WORTH_TAKING.includes(getItem(i.name)?.type));
  if (!prize) {
    return {
      text: [
        '항구의 게시판에 전보 목록이 붙어 있다. 그중 하나가 당신의 이름을 지나간다.',
        '크레인의 배가 먼저 떠났다. 이번에는 당신이 가진 것이 없어서 잃을 것도 없었다.',
        '다음에도 그러리라는 보장은 없다.',
      ],
      effects: { flags: { craneAhead: true }, san: -1 },
    };
  }

  return {
    text: [
      '항구의 게시판에 전보 목록이 붙어 있다. 그중 하나가 당신의 이름을 지나간다.',
      `크레인의 사람들이 먼저 닿았다. ${prize.name}은(는) 이제 그의 가방에 있다.`,
      '빼앗긴 것이 아니다. 늦은 것이다. 그 차이가 더 오래 남는다.',
    ],
    effects: {
      removeItems: [prize.name],
      flags: { craneAhead: true, craneTookPrize: true },
      san: -2,
    },
  };
}
