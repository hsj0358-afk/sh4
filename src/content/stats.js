// 능력치 정의. 1~5 범위에서 시작한다.

export const STATS = [
  { id: '지식', desc: '역사, 언어, 문헌. 유적이 남긴 기록을 읽는다.' },
  { id: '관찰', desc: '흔적과 위화감을 알아챈다. 함정을 먼저 보는 눈.' },
  { id: '탐험', desc: '지형, 이동, 등반, 야영. 몸으로 길을 낸다.' },
  { id: '설득', desc: '대화, 협상, 거짓말. 사람을 움직인다.' },
  { id: '민첩', desc: '손끝과 반사신경. 잠입과 회피.' },
  { id: '의지', desc: '공포와 유혹을 버틴다. 정신력의 방벽.' },
  { id: '체력', desc: '힘과 지구력. 밀고, 버티고, 견딘다.' },
  { id: '신비', desc: '신비학과 금서의 지식. 알아서는 안 될 것에 대한 이해.' },
];

export const STAT_IDS = STATS.map((s) => s.id);

export function emptyStats(base = 1) {
  const out = {};
  for (const id of STAT_IDS) out[id] = base;
  return out;
}
