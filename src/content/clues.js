// 단서 도감. 획득한 단서는 로그북에 쌓이고, 일부는 판정과 선택지를 연다.
// tier: 'field'(현장 단서) | 'core'(메인 미스터리) | 'lead'(다음 지역 연결)

export const CLUES = {
  crane_expedition: {
    tier: 'field',
    title: '크레인 원정대',
    text:
      '아셔 크레인 경의 원정대가 3주 먼저 계곡에 들어왔다. ' +
      '발굴 허가는 없고, 짐은 많다. 그들이 찾는 것은 무덤이 아니다.',
  },
  sealed_by_locals: {
    tier: 'field',
    title: '봉해진 입',
    text:
      '현지 인부들은 계곡 서쪽 지류에 대해 말하지 않는다. ' +
      '금기라서가 아니라, 말한 사람들이 돌아오지 않았기 때문이다.',
  },
  surveyor_hand: {
    tier: 'core',
    title: '측량사의 문체',
    text:
      '벽의 기록은 제사장의 문장이 아니다. 거리와 각도와 날짜를 적는 문체다. ' +
      '누군가 이곳을 신전이 아니라 관측소로 썼다.',
  },
  black_sun: {
    tier: 'core',
    title: '검은 태양',
    text:
      '빛을 내지 않는 원반. 그 아래에서 사람들은 경배하지 않고 엎드려 숨는다. ' +
      '이집트의 신들 중 이런 형상은 없다.',
  },
  star_fall: {
    tier: 'core',
    title: '별이 떨어진 날',
    text:
      '기록은 한 날짜에 몰려 있다. 하늘에서 무언가 떨어졌고, ' +
      '그날 이후의 문장은 필체가 바뀐다. 같은 사람이 쓴 것 같지 않다.',
  },
  door_opener: {
    tier: 'core',
    title: '문을 여는 자',
    text:
      '반복되는 호칭이 하나 있다. 이름이 아니라 직책에 가깝다. ' +
      '문을 여는 자. 그는 안에서 열었는가, 밖에서 열었는가.',
  },
  not_first: {
    tier: 'core',
    title: '처음이 아니었다',
    text:
      '가장 아래층의 문장은 이집트어가 아니다. 그리고 그 아래에 또 다른 층이 있다. ' +
      '이 무덤은 무덤 위에 지어졌고, 그 무덤도 무언가 위에 지어졌다.',
  },
  wrong_sky: {
    tier: 'core',
    title: '어긋난 하늘',
    text:
      '기호판의 별자리는 지금의 하늘과 맞지 않는다. 세차 운동으로 계산하면 ' +
      '만 년 이상 어긋나 있다. 이 별들을 본 사람은 이집트인이 아니었다.',
  },
  mesopotamia_lead: {
    tier: 'lead',
    title: '두 강 사이의 문',
    text:
      '기호판의 가장자리에 새겨진 좌표는 이집트를 가리키지 않는다. ' +
      '동쪽. 두 강 사이. 같은 원반이 그곳에도 새겨져 있다.',
  },
};

export const CLUE_TITLES = Object.fromEntries(
  Object.entries(CLUES).map(([k, v]) => [k, v.title]),
);
