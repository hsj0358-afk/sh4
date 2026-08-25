// 세계 지도 (기획서 8절의 탐험 지역 목록).
//
// 좌표는 실제 위경도가 아니라 지도 SVG 위의 위치(0~100)다.
// 1897년의 지도는 정확할 필요가 없다. 그럴듯하면 된다.
//
// state: 'visited'(다녀옴) | 'known'(단서로 알게 됨) | 'rumor'(소문만) | 'unknown'
//   revealedBy 단서를 얻으면 'known' 으로 올라온다.

export const WORLD_SITES = [
  {
    id: 'luxor',
    short: '룩소르',
    name: '룩소르 · 왕가의 계곡',
    episode: 'luxor',
    x: 56.5,
    y: 47,
    note: '검은 태양이 처음 새겨진 곳.',
  },
  {
    id: 'mesopotamia',
    short: '메소포타미아',
    name: '메소포타미아 · 남부 습지',
    episode: 'mesopotamia',
    x: 63,
    y: 40,
    revealedBy: 'mesopotamia_lead',
    note: '두 강 사이. 같은 원반이 새겨져 있다.',
  },
  {
    id: 'greece',
    short: '그리스',
    name: '그리스 지하 신전',
    x: 52,
    y: 37,
    rumor: true,
    note: '신탁소 아래에 더 오래된 방이 있다는 기록.',
  },
  {
    id: 'sahara',
    short: '사하라',
    name: '사하라 오아시스 폐허',
    x: 47,
    y: 48,
    rumor: true,
    note: '모래가 물러난 해에만 드러난다.',
  },
  {
    id: 'angkor',
    short: '앙코르',
    name: '앙코르 · 서편 회랑',
    episode: 'angkor',
    x: 76,
    y: 53,
    rumor: true,
    revealedBy: 'angkor_lead',
    note: '밀림이 삼킨 회랑. 별자리 배치가 어긋나 있다.',
  },
  {
    id: 'machu',
    short: '마추픽추',
    name: '마추픽추',
    x: 24,
    y: 65,
    rumor: true,
    note: '아직 유럽에 알려지지 않은 능선 위의 도시.',
  },
  {
    id: 'chichen',
    short: '치첸이트사',
    name: '치첸이트사',
    x: 21,
    y: 50,
    rumor: true,
    note: '세노테 바닥에서 건져 올린 것들.',
  },
  {
    id: 'antarctica',
    short: '남극',
    name: '남극의 구조물',
    x: 50,
    y: 90,
    rumor: true,
    note: '포경선 일지에 한 줄. 「얼음 아래 직선」.',
  },
  {
    id: 'london',
    short: '런던',
    name: '런던 박물관 지하 보관고',
    x: 45.5,
    y: 25,
    rumor: true,
    note: '크레인의 지도가 나온 곳.',
  },
];

export function siteState(site, state) {
  if (site.episode && state.episode === site.episode) return 'visited';
  if (site.episode && (state.visitedEpisodes || []).includes(site.episode)) return 'visited';
  if (site.revealedBy && state.clues.includes(site.revealedBy)) return 'known';
  if (site.rumor) return 'rumor';
  return 'unknown';
}
