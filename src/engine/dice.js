// 1D20 판정 시스템.
//
// 기획서 7-2의 결과 구간을 두 축으로 나눠 구현한다.
//
//   1) 자연 눈(natural) 1 / 20 은 목표값과 무관하게 대실패 / 대성공.
//   2) 그 외에는 총합(주사위 + 보정)을 목표값과 비교한다.
//        총합 >= 목표값            → 성공
//        총합 >= 목표값 - MARGIN   → 부분 성공 (대가를 치르고 얻는다)
//        그 미만                   → 실패
//
// 이렇게 하면 "10~14는 보통/부분 성공" 이라는 감각을 유지하면서도
// 난이도가 다른 판정끼리 규칙이 일관되게 적용된다.

export const PARTIAL_MARGIN = 3;

export const OUTCOME = {
  FUMBLE: 'fumble',
  FAIL: 'fail',
  PARTIAL: 'partial',
  SUCCESS: 'success',
  CRIT: 'crit',
};

/** 서술과 연출에서 쓰는 표시용 이름. */
export const OUTCOME_LABEL = {
  fumble: '대실패',
  fail: '실패',
  partial: '부분 성공',
  success: '성공',
  crit: '대성공',
};

export const OUTCOME_ORDER = [
  OUTCOME.FUMBLE,
  OUTCOME.FAIL,
  OUTCOME.PARTIAL,
  OUTCOME.SUCCESS,
  OUTCOME.CRIT,
];

/**
 * 판정 결과를 계산한다.
 * @param {number} natural 주사위 눈 (1~20)
 * @param {number} modifier 보정치 합계
 * @param {number} target 목표값
 */
export function resolve(natural, modifier, target) {
  const total = natural + modifier;

  let outcome;
  if (natural === 20) outcome = OUTCOME.CRIT;
  else if (natural === 1) outcome = OUTCOME.FUMBLE;
  else if (total >= target) outcome = OUTCOME.SUCCESS;
  else if (total >= target - PARTIAL_MARGIN) outcome = OUTCOME.PARTIAL;
  else outcome = OUTCOME.FAIL;

  return {
    natural,
    modifier,
    target,
    total,
    outcome,
    label: OUTCOME_LABEL[outcome],
    // 성공 계열인지 — 서사 분기에서 자주 쓴다.
    ok: outcome === OUTCOME.SUCCESS || outcome === OUTCOME.CRIT,
  };
}

/** 두 결과 중 어느 쪽이 나은가. 같으면 0. */
export function compareOutcome(a, b) {
  return OUTCOME_ORDER.indexOf(a) - OUTCOME_ORDER.indexOf(b);
}

/** 주사위를 굴려 판정까지 수행한다. */
export function rollCheck(rng, { modifier = 0, target = 12 } = {}) {
  return resolve(rng.int(1, 20), modifier, target);
}

/**
 * 서사 분기 테이블에서 가장 가까운 항목을 고른다.
 * 콘텐츠가 5구간을 전부 쓰지 않아도 되도록 완만하게 대체한다.
 *   대실패 → 실패, 대성공 → 성공, 부분 성공 → 성공 → 실패 순.
 */
export function selectBranch(branches, outcome) {
  if (!branches) return null;
  const fallback = {
    fumble: ['fumble', 'fail', 'partial', 'success'],
    fail: ['fail', 'partial', 'fumble', 'success'],
    partial: ['partial', 'success', 'fail'],
    success: ['success', 'partial', 'crit'],
    crit: ['crit', 'success', 'partial'],
  }[outcome] || [outcome];

  for (const key of fallback) {
    if (branches[key]) return branches[key];
  }
  return null;
}
