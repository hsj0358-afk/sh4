// 통찰 — 이 게임의 '성장'.
//
// 자가진단 ④: applyEffects 에 stats 키가 아예 없다. 능력치는 한 판 내내 불변이고,
// 보정이 자라는 유일한 축은 장비인데 그것도 「가장 큰 하나만」에 상한 +3 이다.
// 3장을 다 돌아도 1장 첫 판정과 성공률이 같았다. 전투-보상-성장 루프에서
// 성장 마디가 통째로 비어 있었다.
//
// 그렇다고 능력치를 올릴 수는 없다. 3주 만에 사람이 똑똑해지지 않는다.
// 이 게임에서 자라야 할 것은 **앎**이다 — 단서 두 개가 만나면 세 번째 것이 보이고,
// 그 보임이 다음 판정에 붙는다.
//
// 그래서 통찰은 얻는 것이 아니라 **알아채는 것**이다. 어디에서도 주지 않는다.
// 수첩에 적힌 두 줄이 만나는 순간 저절로 생긴다.
//
// 설계 규칙 세 가지.
//
//   1. 도달 가능해야 한다. 무작위 400판을 굴려 실제 동시 획득률을 재고 골랐다
//      (18~49%). 아무도 못 만드는 조합은 성장이 아니라 장식이다.
//   2. 시점이 퍼져 있어야 한다. 36수째부터 111수째까지 사다리로 놓았다.
//      전부 마지막 장에 몰리면 자라는 느낌이 안 난다.
//   3. 태그가 갈려야 한다. 지식·관찰에만 붙으면 고고학자만 또 이득을 본다.
//      신비·공포 / 해독·기록 / 사교·정보 / 방향·이동 / 잠입·탈출 로 나눠 놓았다.

export const INSIGHTS = [
  {
    id: 'black_disc',
    title: '검은 태양의 자리',
    need: ['black_sun', 'star_fall'],
    tags: ['신비', '공포'],
    value: 1,
    // 400판 중 30% · 평균 36수째 — 가장 먼저 열리는 문
    text:
      '빛을 내지 않는 원반과, 하늘에서 무언가 떨어진 날. ' +
      '둘은 같은 사건의 앞뒤다. 그것을 알고 보면 원반은 더 이상 신의 자리가 아니다.',
  },
  {
    id: 'same_hand',
    title: '같은 손',
    need: ['surveyor_hand', 'same_hand'],
    tags: ['해독', '기록'],
    value: 1,
    // 38% · 61수째 — 1장의 벽과 2장의 벽돌이 만난다
    text:
      '거리와 각도와 날짜. 이집트의 벽과 수메르의 도장이 같은 문체다. ' +
      '한 번 알아보고 나면, 다음 벽에서는 무엇을 먼저 찾아야 하는지 안다.',
  },
  {
    id: 'their_road',
    title: '앞서간 사람의 길',
    need: ['crane_expedition', 'ottoman_permit'],
    tags: ['잠입', '탈출'],
    value: 1,
    // 18% · 53수째 — 흔한 단서와 드문 단서의 짝
    text:
      '허가는 돈으로 났고, 짐은 삽보다 무겁다. 그가 어떻게 움직이는지 알게 됐다. ' +
      '앞서간 사람의 발자국은 피할 곳이자 지나갈 곳이다.',
  },
  {
    id: 'erased',
    title: '지워진 자리',
    need: ['madan_warning', 'french_survey'],
    tags: ['방향', '이동'],
    value: 1,
    // 19% · 91수째 — 두 대륙에서 같은 방식으로 길이 지워진다
    text:
      '갈대밭에서도 밀림에서도, 지도에 없는 곳은 원래 없던 곳이 아니다. ' +
      '지운 사람이 있다. 지운 자국은 그 자체로 방향이다.',
  },
  {
    id: 'closers',
    title: '닫는 일',
    need: ['door_opener', 'the_sealers'],
    tags: ['사교', '정보'],
    value: 1,
    // 49% · 90수째 — 가장 잘 열리는 조합
    text:
      '문을 여는 자가 있으면 닫는 자도 있다. 그들은 대를 이어 이름을 남기지 않았다. ' +
      '누구에게 무엇을 물어야 하는지가 그때부터 달라진다.',
  },
  {
    id: 'the_count',
    title: '세는 자의 셈',
    need: ['eighth_gate', 'third_record'],
    tags: ['해독', '신비'],
    value: 2,
    // 25% · 111수째 — 마지막에 열리는 것이라 값이 커야 한다
    text:
      '일곱은 오래전에 새겨졌고 여덟 번째는 최근이다. 그리고 세 대륙의 필체가 하나다. ' +
      '세는 사람이 아직 세고 있다는 뜻이고, 그가 무엇을 세는지 이제 당신도 센다.',
  },
];

const BY_ID = Object.fromEntries(INSIGHTS.map((i) => [i.id, i]));

export function getInsight(id) {
  return BY_ID[id] || null;
}

/** 이 상태에서 성립하는 통찰 전부. 상태에 저장하지 않고 단서에서 매번 읽는다. */
export function heldInsights(state) {
  const clues = state?.clues || [];
  return INSIGHTS.filter((i) => i.need.every((c) => clues.includes(c)));
}

/** 그중 이 판정에 걸리는 것. */
export function insightsFor(state, tags = []) {
  return heldInsights(state).filter((i) => i.tags.some((t) => tags.includes(t)));
}
