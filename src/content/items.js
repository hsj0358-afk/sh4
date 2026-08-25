// 아이템 정의.
//
// type: 'gear'(일반 장비) | 'relic'(유적 유물) | 'special'(특별 아이템) | 'supply'(소모 자원)
// bonus: 특정 태그의 판정에 붙는 보정. { tags: [...], value: n }
// uses: 내구도 / 잔량. null 이면 소모되지 않는다.

export const ITEMS = {
  // ── 일반 장비 ────────────────────────────────────────────────
  '횃불': {
    type: 'gear', uses: 6,
    desc: '역청을 먹인 삼베. 지하에서는 이것이 시야 전부다.',
    bonus: { tags: ['암흑', '조사'], value: 2 },
    note: '어두운 곳에서 자동으로 소모된다.',
  },
  '등반 로프': {
    type: 'gear', uses: 3,
    desc: '30피트. 매듭 자국이 손에 익었다.',
    bonus: { tags: ['등반', '탈출'], value: 2 },
  },
  '나침반': {
    type: 'gear', uses: null,
    desc: '황동 케이스. 유적 안에서는 가끔 거짓말을 한다.',
    bonus: { tags: ['이동', '방향'], value: 1 },
  },
  '현장 수첩': {
    type: 'gear', uses: null,
    desc: '반쯤 채워진 스케치와 메모.',
    bonus: { tags: ['해독', '기록'], value: 1 },
  },
  '확대경': {
    type: 'gear', uses: null,
    desc: '놋쇠 손잡이가 닳았다.',
    bonus: { tags: ['조사', '해독'], value: 2 },
  },
  '탁본 도구': {
    type: 'gear', uses: 3,
    desc: '얇은 종이와 목탄. 벽에 새겨진 것을 가져갈 수 있다.',
    bonus: { tags: ['기록', '해독'], value: 2 },
  },
  '만능 열쇠 꾸러미': {
    type: 'gear', uses: null,
    desc: '카이로에서 산 것. 절반은 쓸모없다.',
    bonus: { tags: ['함정', '잠입'], value: 2 },
  },
  '접이식 쇠지렛대': {
    type: 'gear', uses: null,
    desc: '지렛대이자 무기.',
    bonus: { tags: ['완력', '전투'], value: 1 },
  },
  '검은 천': {
    type: 'gear', uses: null,
    desc: '등불을 가리거나, 얼굴을 가리거나.',
    bonus: { tags: ['잠입'], value: 2 },
  },
  '웨블리 리볼버': {
    type: 'gear', uses: 6,
    desc: '.455구경. 좁은 통로에서는 소리가 먼저 도착한다.',
    bonus: { tags: ['전투'], value: 3 },
    note: '발포하면 위험도가 오른다.',
  },
  '군용 나이프': {
    type: 'gear', uses: null,
    desc: '날이 무디지만 손에 붙는다.',
    bonus: { tags: ['전투', '완력'], value: 1 },
  },
  '휴대용 사진기': {
    type: 'gear', uses: 4,
    desc: '건판 네 장. 한 장마다 신중해야 한다.',
    bonus: { tags: ['기록'], value: 2 },
  },
  '취재 수첩': {
    type: 'gear', uses: null,
    desc: '이름과 날짜와 거짓말이 뒤섞여 있다.',
    bonus: { tags: ['정보', '기록'], value: 1 },
  },
  '위조 소개장': {
    type: 'gear', uses: 1,
    desc: '왕립 지리학회의 인장. 자세히 보면 티가 난다.',
    bonus: { tags: ['사교', '정보'], value: 3 },
  },
  '신용장': {
    type: 'gear', uses: 2,
    desc: '카이로 지점에서 즉시 현금화된다.',
    bonus: { tags: ['자금', '사교'], value: 3 },
  },
  '금시계': {
    type: 'gear', uses: 1,
    desc: '뒷면에 아버지의 이름이 새겨져 있다. 뇌물로 쓰기엔 아깝다.',
    bonus: { tags: ['자금'], value: 2 },
  },
  '은제 휴대용 술병': {
    type: 'gear', uses: 2,
    desc: '브랜디. 용기 아니면 실수.',
    bonus: { tags: ['사교'], value: 1 },
  },
  '낡은 금서 사본': {
    type: 'gear', uses: null,
    desc: '원본은 불탔다고 한다. 읽을 때마다 조금씩 다르게 읽힌다.',
    bonus: { tags: ['신비', '해독'], value: 2 },
    note: '참조할 때마다 정신력을 조금 갉아먹는다.',
  },
  '의식용 분필': {
    type: 'gear', uses: 3,
    desc: '뼈를 갈아 섞었다는 소문이 있다.',
    bonus: { tags: ['신비'], value: 2 },
  },
  '은 부적': {
    type: 'gear', uses: null,
    desc: '별 여섯과 눈 하나. 효과는 증명된 적 없다.',
    bonus: { tags: ['공포'], value: 2 },
  },
  '수술용 겸자': {
    type: 'gear', uses: null,
    desc: '정밀한 손을 대신한다.',
    bonus: { tags: ['의료', '함정'], value: 1 },
  },

  // ── 소모 자원 ────────────────────────────────────────────────
  '의료 키트': {
    type: 'supply', uses: 3, consumable: true,
    desc: '거즈, 요오드, 바늘과 실.',
    use: { hp: 3, text: '상처를 씻고 꿰맸다. 통증이 잦아든다.' },
  },
  '모르핀 앰플': {
    type: 'supply', uses: 2, consumable: true,
    desc: '통증을 지운다. 판단력도 함께.',
    use: { hp: 4, san: -1, text: '통증이 멀어진다. 세계도 함께 멀어진다.' },
  },
  '붕대': {
    type: 'supply', uses: 2, consumable: true,
    desc: '깨끗하지는 않다.',
    use: { hp: 2, text: '피는 멎었다. 그거면 지금은 충분하다.' },
  },
  '수통': {
    type: 'supply', uses: 4, consumable: true,
    desc: '미지근한 물. 사막에서는 금보다 비싸다.',
    use: { hp: 1, san: 1, text: '물이 목을 타고 내려간다. 머리가 조금 맑아진다.' },
  },

  // ── 유적 유물 ────────────────────────────────────────────────
  '조각난 석판': {
    type: 'relic', uses: null,
    desc: '검은 원반 아래 사람들이 엎드린 부조. 원반에서 빛이 아니라 선이 뻗어 나온다.',
    bonus: { tags: ['해독'], value: 1 },
  },
  '별자리 기호판': {
    type: 'relic', uses: null,
    desc: '지금의 하늘과 맞지 않는 별자리. 만 년쯤 어긋나 있다.',
    bonus: { tags: ['해독', '신비'], value: 2 },
  },
  '상형문서': {
    type: 'relic', uses: null,
    desc: '파피루스 두루마리. 제사장이 아니라 측량사의 문체다.',
    bonus: { tags: ['해독'], value: 2 },
  },
  '의식용 부적': {
    type: 'relic', uses: null,
    desc: '녹청이 낀 청동. 쥐고 있으면 손끝이 차다.',
    bonus: { tags: ['공포', '신비'], value: 2 },
  },

  '점토 원통': {
    type: 'relic', uses: null,
    desc: '굴리면 문장이 이어지는 원통 인장. 쐐기 사이에 숫자가 섞여 있다.',
    bonus: { tags: ['해독'], value: 2 },
  },
  '왕 목록 사본': {
    type: 'relic', uses: null,
    desc: '홍수 이전의 왕들과 그 재위 기간. 숫자를 적은 손이 지나치게 침착하다.',
    bonus: { tags: ['해독', '신비'], value: 2 },
  },

  // ── 특별 아이템 ──────────────────────────────────────────────
  '검은 태양의 열쇠': {
    type: 'special', uses: null,
    desc: '열쇠라기보다 자물쇠에 가까운 형태. 어느 쪽이 열리는 쪽인지 알 수 없다.',
    bonus: { tags: ['신비', '해독'], value: 3 },
    note: '봉인된 문을 여는 데 쓰인다.',
  },
  '문의 각인': {
    type: 'special', uses: null,
    desc:
      '청동판에 새겨진 문의 목록. 일곱까지는 같은 손이, 여덟 번째는 다른 손이 새겼다. ' +
      '뒷면의 홈은 다른 대륙의 무언가와 맞물리게 되어 있다.',
    bonus: { tags: ['신비', '해독'], value: 3 },
    note: '이집트의 열쇠와 짝을 이룬다.',
  },

  '회랑 탁본첩': {
    type: 'relic', uses: null,
    desc: '나가 회랑의 부조를 뜬 것. 세 대륙의 문체가 한 권 안에 나란히 있다.',
    bonus: { tags: ['해독', '기록'], value: 3 },
  },
  '봉인단의 표식': {
    type: 'relic', uses: null,
    desc:
      '나무를 깎아 만든 원반. 안쪽이 검게 그을렸다. ' +
      '들고 있으면 어떤 사람들은 길을 비켜 주고, 어떤 사람들은 등을 돌린다.',
    bonus: { tags: ['사교', '신비'], value: 2 },
  },

  // ── 일반 장비 (밀림) ─────────────────────────────────────────
  '벌목도': {
    type: 'gear', uses: null,
    desc: '현지 대장간에서 벼린 것. 밀림에서는 이것이 지도이자 문이다.',
    bonus: { tags: ['이동', '완력', '전투'], value: 2 },
  },
  '프랑스 측량도': {
    type: 'gear', uses: null,
    desc: '1896년판. 서편 회랑 구역이 지워졌다가 다시 그려져 있다.',
    bonus: { tags: ['방향', '정보'], value: 2 },
  },
  '키니네': {
    type: 'supply', uses: 3, consumable: true,
    desc: '쓴맛이 혀에 오래 남는다. 밀림에서는 물보다 귀하다.',
    use: { hp: 3, text: '열이 내린다. 손끝의 떨림이 멎는다.' },
  },

  // ── 일반 장비 (두 강 사이) ───────────────────────────────────
  '역청 램프': {
    type: 'gear', uses: 8,
    desc: '역청을 태운다. 그을음이 많지만 젖어도 잘 꺼지지 않는다.',
    bonus: { tags: ['암흑', '조사'], value: 2 },
    note: '물가에서는 횃불보다 낫다.',
  },
};

export function getItem(name) {
  return ITEMS[name] || null;
}

export function itemBonus(name, tags) {
  const it = ITEMS[name];
  if (!it || !it.bonus) return 0;
  return it.bonus.tags.some((t) => tags.includes(t)) ? it.bonus.value : 0;
}
