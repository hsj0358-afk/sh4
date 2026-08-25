// 난이도 (기획서 18절).
//
// 난이도는 판정의 "성공률"만 흔드는 것이 아니라 탐사의 여유를 조절한다.
//   targetShift — 모든 판정의 목표값
//   hpBonus / sanBonus — 시작 여유분
//   damageScale — 받는 피해(체력·정신력 감소)의 배율
//
// 한 번 정하면 그 탐사 동안 바뀌지 않는다. 도중에 바꿀 수 있으면
// 판정의 긴장이 사라진다.

export const DIFFICULTIES = {
  gentle: {
    id: 'gentle',
    name: '기록자',
    tagline: '이야기를 보러 왔다',
    desc: '판정이 관대하고 상처가 얕다. 서사를 따라가는 데 집중할 수 있다.',
    targetShift: -1,
    hpBonus: 3,
    sanBonus: 3,
    damageScale: 0.7,
  },
  standard: {
    id: 'standard',
    name: '탐사자',
    tagline: '규칙대로',
    desc: '기획된 그대로의 난이도. 실패도 대실패도 제 몫을 한다.',
    targetShift: 0,
    hpBonus: 0,
    sanBonus: 0,
    damageScale: 1,
  },
  harsh: {
    id: 'harsh',
    name: '고고학자의 저주',
    tagline: '유적은 관대하지 않다',
    desc: '목표값이 오르고 피해가 깊다. 돌아 나오는 판단이 중요해진다.',
    targetShift: 1,
    hpBonus: -2,
    sanBonus: -2,
    damageScale: 1.35,
  },
};

export const DIFFICULTY_IDS = Object.keys(DIFFICULTIES);

export function getDifficulty(id) {
  return DIFFICULTIES[id] || DIFFICULTIES.standard;
}

/**
 * 피해량에 난이도를 반영한다.
 * 배율이 아무리 낮아도 1 미만으로 깎아 무효로 만들지는 않는다 —
 * 피해가 0이 되면 실패가 대가를 잃는다.
 */
export function scaleDamage(amount, difficultyId) {
  if (amount >= 0) return amount;
  const scale = getDifficulty(difficultyId).damageScale;
  const scaled = Math.round(amount * scale);
  return Math.min(-1, scaled);
}
