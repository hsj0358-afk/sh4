// 시계.
//
// 1틱 = 30분. 1897년 11월 3일 오전 8시에 출발한다.
//
// 규칙도 콘텐츠도 UI도 시간을 읽는다. 콘텐츠가 특히 그렇다 — 유적에서 나온 장면이
// "해가 능선 위로 올라오고 있다" 고 쓰려면 정말로 아침인지 알아야 한다.
// 한때 그 문장이 고정되어 있어서, 오후 10시 반에 나온 사람도 일출을 봤다.
//
// 어느 층에도 속하지 않는 순수 계산이라 여기 따로 둔다.

export const MINUTES_PER_TICK = 30;
const START_DAY = { year: 1897, month: 11, day: 3 };
const START_MINUTES = 8 * 60; // 오전 8시 출발

/** 출발로부터 흐른 시간(시간 단위). */
export function hoursSince(tick) {
  return (tick * MINUTES_PER_TICK) / 60;
}

/** 지금 몇 시인가 (0~23). */
export function hourOfDay(tick) {
  return Math.floor(((START_MINUTES + tick * MINUTES_PER_TICK) % (24 * 60)) / 60);
}

/**
 * 하루의 어느 때인가.
 * 서술이 "아침 빛" 인지 "랜턴 불빛" 인지 고르는 데 쓴다.
 */
export function phaseOfDay(tick) {
  const h = hourOfDay(tick);
  if (h < 5) return 'night';
  if (h < 8) return 'dawn';
  if (h < 11) return 'morning';
  if (h < 16) return 'day';
  if (h < 19) return 'evening';
  return 'night';
}

/**
 * 다음번 그 시각까지 몇 틱인가.
 *
 * 밤을 보내는 선택지들이 전부 고정된 시간을 썼다. 아침 열 시에 천막을 치고
 * 여섯 시간 뒤에 「새벽 세 시」를 읽는 일이 생겼다. 자는 것은 정해진 만큼이
 * 아니라 아침까지다 — 그래서 늦게 눕는 사람이 시간을 덜 쓴다. 언제 눕느냐가
 * 그제서야 판단이 된다.
 */
export function ticksUntil(tick, hour) {
  const day = 24 * 60;
  const now = (START_MINUTES + tick * MINUTES_PER_TICK) % day;
  const delta = (((hour * 60 - now) % day) + day) % day;
  return Math.round((delta || day) / MINUTES_PER_TICK);
}

/**
 * 날짜는 달을 넘긴다. 캠페인이 세 장으로 늘면서 여정만 8주가 되었고,
 * 그때까지 "11월 59일" 이라고 적혀 있었다.
 */
export function formatClock(tick) {
  const total = START_MINUTES + tick * MINUTES_PER_TICK;
  const dayOffset = Math.floor(total / (24 * 60));
  const m = total % (24 * 60);
  const hh = Math.floor(m / 60);
  const mm = m % 60;

  const d = new Date(Date.UTC(START_DAY.year, START_DAY.month - 1, START_DAY.day + dayOffset));
  const ampm = hh < 12 ? '오전' : '오후';
  const h12 = hh % 12 === 0 ? 12 : hh % 12;

  return {
    date: `${d.getUTCFullYear()}년 ${d.getUTCMonth() + 1}월 ${d.getUTCDate()}일`,
    time: `${ampm} ${h12}시${mm ? ` ${mm}분` : ''}`,
    night: hh >= 19 || hh < 5,
    phase: phaseOfDay(tick),
  };
}
