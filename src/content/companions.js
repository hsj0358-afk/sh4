// 동료. 판정 보조와 서사 관계를 담당한다.
//
// assist: 이 태그의 판정에 보정을 준다. 호감도/신뢰도가 낮으면 보정이 줄어든다.
// hp: 동료도 다친다. 0이 되면 이탈한다.

export const COMPANIONS = {
  nadia: {
    id: 'nadia',
    name: '나디아 하룬',
    role: '현지 안내인 · 통역',
    desc:
      '룩소르에서 나고 자랐다. 유럽인 발굴단을 열 번 넘게 안내했고, ' +
      '그중 셋은 돌아오지 못했다. 그 이야기를 먼저 꺼내지는 않는다.',
    assist: { tags: ['사교', '정보', '이동', '방향'], value: 2 },
    hp: 8, maxHp: 8,
    affinity: 2, // 호감도 0~5
    trust: 2,    // 신뢰도 0~5
    skill: '현지어와 관습. 나디아가 앞장서면 문이 열리는 속도가 다르다.',
  },
  finch: {
    id: 'finch',
    name: '올리버 핀치',
    role: '측량기사 · 전 공병',
    desc:
      '왕립 공병대에서 나온 지 3년. 무너질 것과 버틸 것을 눈으로 구분한다. ' +
      '농담이 많은 편인데, 진짜 겁이 날 때만 그렇다.',
    assist: { tags: ['등반', '완력', '함정', '탈출'], value: 2 },
    hp: 10, maxHp: 10,
    affinity: 2,
    trust: 3,
    skill: '구조와 하중. 핀치는 천장이 언제 내려앉을지 안다.',
  },
  seraphina: {
    id: 'seraphina',
    name: '세라피나 볼트',
    role: '고문서 필사가',
    desc:
      '대영박물관 지하 보관고에서 8년을 보냈다. 사람보다 문서를 오래 봤고, ' +
      '그 사실을 부끄러워하지 않는다. 검은 태양이라는 말에 처음 반응한 사람이다.',
    assist: { tags: ['해독', '기록', '신비'], value: 2 },
    hp: 6, maxHp: 6,
    affinity: 1,
    trust: 2,
    skill: '죽은 언어. 세라피나는 문장이 아니라 필체를 읽는다.',
  },
  basim: {
    id: 'basim',
    name: '바심 알마단',
    role: '습지 뱃사공',
    desc:
      '삼대째 갈대 사이에서 배를 민다. 물길을 길이 아니라 물 색으로 읽는다. ' +
      '물 위에서는 무엇도 두려워하지 않고, 물 아래는 절대 내려가지 않는다.',
    assist: { tags: ['이동', '방향', '탈출'], value: 2 },
    hp: 9, maxHp: 9,
    affinity: 1,
    trust: 2,
    skill: '갈대의 미로. 바심이 앞장서면 습지는 길이 된다.',
  },
  sokha: {
    id: 'sokha',
    name: '속하',
    role: '회랑 안내인 · 채석공의 딸',
    desc:
      '아버지와 할아버지가 이 돌을 손봤다. 프랑스 측량대에서 3년을 일했고, ' +
      '도면에서 지워진 구역이 어디인지 아는 몇 안 되는 사람이다. ' +
      '왜 지워졌는지는 묻지 않기로 했다고 한다.',
    assist: { tags: ['이동', '방향', '조사'], value: 2 },
    hp: 8, maxHp: 8,
    affinity: 1,
    trust: 2,
    skill: '돌의 결. 속하는 어느 벽이 원래 있던 것이고 어느 벽이 나중에 세워졌는지 안다.',
  },
  crane: {
    id: 'crane',
    name: '아셔 크레인',
    role: '전 경쟁자 · 원정단장',
    desc:
      '두 대륙에서 당신을 막아섰고, 두 번 다 물러섰다. 조카를 잃었고 잠수부를 잃었다. ' +
      '독점하려던 사람이 지금은 그저 끝을 보고 싶어 한다. ' +
      '그 변화가 진심인지는, 아직 아무도 모른다.',
    assist: { tags: ['사교', '자금', '정보', '전투'], value: 2 },
    hp: 11, maxHp: 11,
    affinity: 2,
    trust: 1, // 두 번 총을 겨눴던 사람이다
    skill: '자금과 인맥. 그리고 런던 지하 보관고에서 나온 도면.',
  },
};

export function makeCompanion(id) {
  const base = COMPANIONS[id];
  if (!base) return null;
  return {
    id: base.id,
    name: base.name,
    role: base.role,
    hp: base.hp,
    maxHp: base.maxHp,
    affinity: base.affinity,
    trust: base.trust,
    injured: false,
    present: true,
  };
}

/**
 * 동료가 주는 판정 보정.
 * 신뢰도가 낮으면 제대로 돕지 않는다 — 관계가 곧 수치다.
 */
export function companionAssist(companion, tags) {
  if (!companion || !companion.present || companion.hp <= 0) return 0;
  const base = COMPANIONS[companion.id];
  if (!base || !base.assist) return 0;
  if (!base.assist.tags.some((t) => tags.includes(t))) return 0;

  let value = base.assist.value;
  if (companion.trust <= 1) value -= 1;
  if (companion.injured) value -= 1;
  if (companion.affinity >= 4) value += 1;
  return Math.max(0, value);
}
