// 막간 — 장과 장 사이의 항로 선택 (기획서 18절 '분기형 캠페인').
//
// 지역을 통째로 갈라 두 개씩 쓰는 것은 콘텐츠가 두 배로 드는 일이다.
// 대신 캠페인 층에서 가른다. 같은 목적지로 가되 어느 길로 가느냐가
// 시간·돈·몸·아는 것을 서로 다르게 바꾼다.
//
// 각 항로는 조건을 가질 수 있고, 조건이 맞지 않으면 목록에 뜨지 않는다.

export const INTERLUDES = {
  mesopotamia: {
    title: '어느 길로 갈 것인가',
    intro: [
      '알렉산드리아 항. 다음 배는 사흘 뒤에 뜬다.',
      '지도를 펴 놓고 보면 두 강 사이로 가는 길은 하나가 아니다.',
    ],
    routes: [
      {
        id: 'fast',
        label: '홍해 급행 — 빠르지만 비싸고 고되다',
        detail: '3주. 몸이 상하지만 크레인보다 앞선다.',
        text: [
          '증기선 두 척을 갈아타고, 수에즈에서 하루를 자지 못했다.',
          '뱃삯은 신용장 한 장을 통째로 먹었다.',
          '바스라에 닿았을 때 다리가 후들거렸지만, 부두에는 아직 영국 깃발이 없었다.',
        ],
        effects: { time: 24 * 2 * 21, hp: 6, san: 8, flags: { aheadOfCrane: true } },
      },
      {
        id: 'steady',
        label: '정규 항로 — 무난하다',
        detail: '5주. 몸도 마음도 제대로 회복된다.',
        text: [
          '정기선의 삼등 선실은 좁지만 규칙적이다.',
          '아침에 일어나 갑판을 걷고, 낮에는 수첩을 정리하고, 밤에는 잔다.',
          '5주 동안 아무 일도 일어나지 않았다. 그것이 이 항로가 파는 상품이다.',
        ],
        effects: { time: 24 * 2 * 35, hp: 14, san: 12 },
      },
      {
        id: 'london',
        label: '런던을 경유한다 — 보관고에 들른다',
        detail: '8주. 크레인이 앞서지만, 지하 보관고를 볼 수 있다.',
        requires: { clues: ['crane_expedition'] },
        text: [
          '런던은 11월보다 12월이 더 어둡다.',
          '박물관 지하 보관고는 열람 신청을 넣으면 6주가 걸리고, 옆문으로 들어가면 하루가 걸린다.',
          '반출 기록 대장에는 존재하지 않는 물건들의 반출 기록이 있었다.',
          '그중 셋은 두 강 사이에서 나온 것으로 적혀 있었다. 발굴된 적 없는 유적에서.',
        ],
        effects: {
          time: 24 * 2 * 56,
          hp: 12,
          san: 10,
          clues: ['the_sealers'],
          items: ['프랑스 측량도'],
          flags: { sawLondonVault: true, craneAhead: true },
        },
      },
    ],
  },

  angkor: {
    title: '동쪽으로 가는 길',
    intro: [
      '바스라에서 인도양을 건너야 한다. 그리고 인도양을 건너는 방법은 몇 가지가 있다.',
    ],
    routes: [
      {
        id: 'mail',
        label: '우편선에 편승한다 — 가장 빠르다',
        detail: '5주. 쉴 틈이 없고, 크레인의 전보보다 먼저 도착한다.',
        text: [
          '우편선은 사람을 태우려고 다니는 배가 아니다. 그래서 빠르고, 그래서 불편하다.',
          '해먹 하나와 하루 두 끼. 5주 동안 같은 벽을 봤다.',
          '사이공에 내렸을 때, 항구 게시판의 전보 목록에 당신의 이름은 없었다.',
        ],
        effects: { time: 24 * 2 * 35, hp: 9, san: 6, flags: { aheadOfCrane: true } },
      },
      {
        id: 'liner',
        label: '정기 여객선 — 회복하며 간다',
        detail: '7주. 몸과 마음이 거의 돌아온다.',
        text: [
          '일등 선실은 아니지만 창이 있는 방이다.',
          '7주 동안 탁본을 말리고, 순서대로 묶고, 세 대륙의 문체를 나란히 놓아 보았다.',
          '세라피나가 있었다면 더 빨랐을 것이다. 없었다면 더 느렸을 것이고.',
        ],
        effects: { time: 24 * 2 * 49, hp: 14, san: 14 },
      },
      {
        id: 'crane_ship',
        label: '크레인이 낸 배를 탄다',
        detail: '6주. 빠르고 편하지만, 그는 당신이 아는 것을 전부 본다.',
        requires: { flags: { craneAlly: true } },
        text: [
          '크레인의 배는 화물선이고, 화물은 발굴 장비다.',
          '선실은 넓고 식사는 제때 나온다. 그리고 그의 사람들이 당신의 수첩을 볼 수 있는 거리에 늘 있다.',
          '"보라고 두는 겁니다." 그가 말한다. "숨기면 서로 피곤해지니까."',
          '6주 동안 두 사람은 서로의 기록을 읽었다. 어느 쪽이 더 많이 얻었는지는 모른다.',
        ],
        effects: {
          time: 24 * 2 * 42,
          hp: 12,
          san: 10,
          clues: ['eighth_gate'],
          flags: { craneKnowsAll: true },
          companionChanges: [{ id: 'crane', trust: 1, affinity: 1 }],
        },
      },
    ],
  },
};

export function getInterlude(episodeId) {
  return INTERLUDES[episodeId] || null;
}

/** 지금 고를 수 있는 항로. 조건을 못 채운 것은 아예 보이지 않는다. */
export function availableRoutes(interlude, state) {
  return (interlude.routes || []).filter((r) => {
    if (!r.requires) return true;
    for (const c of r.requires.clues || []) if (!state.clues.includes(c)) return false;
    for (const [k, v] of Object.entries(r.requires.flags || {})) {
      if (state.flags[k] !== v) return false;
    }
    for (const id of r.requires.companions || []) {
      if (!state.companions[id]?.present) return false;
    }
    return true;
  });
}
