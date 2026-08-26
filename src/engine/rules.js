// 보정치 계산. 판정 하나가 어떤 근거로 그 숫자가 되었는지 전부 남긴다.
// 플레이어가 "왜 이 숫자인가"를 항상 확인할 수 있어야 한다는 원칙(기획서 7-3).

import { itemBonus, hasLight } from '../content/items.js';
import { companionAssist } from '../content/companions.js';
import { getDifficulty } from '../content/difficulty.js';
import { conditionPenalty, dangerPressure } from './state.js';

/** 직업 고유 태그가 걸리면 +2. 기획서의 직업별 특전을 규칙으로 옮긴 것. */
const PERK_VALUE = 2;

/**
 * 상태 페널티와 위험도 압박을 합한 불이익의 상한.
 * 이 값을 넘으면 판정이 사실상 잠기고, 잠긴 판정의 실패가 다시 상태를 악화시킨다.
 * 4 는 능력치와 보정이 평범한 탐사자에게 대략 25~30% 의 성공률을 남긴다.
 */
export const MAX_PENALTY_STACK = 4;

/** 어두운 곳에서 빛 없이 하는 일의 대가. */
export const DARK_PENALTY = 2;

// 빛이 있는지는 소지품이 안다. 규칙은 그 답을 쓸 뿐이다.
export { hasLight };

/**
 * @param {object} state
 * @param {object} check { stat, tags, target, bonus }
 * @param {object} [opts] { dark } 장면의 사정. 콘텐츠가 아니라 GM 이 넘긴다.
 * @returns {{ modifier:number, target:number, breakdown:Array<{label:string,value:number}> }}
 */
export function buildCheck(state, check, opts = {}) {
  const tags = check.tags || [];
  const breakdown = [];

  // 1. 능력치
  const statValue = check.stat ? state.char.stats[check.stat] || 0 : 0;
  if (check.stat) breakdown.push({ label: check.stat, value: statValue });

  // 2. 직업 특전
  const perkHit = state.char.tags.some((t) => tags.includes(t));
  if (perkHit) breakdown.push({ label: `${state.char.profession} 전문`, value: PERK_VALUE });

  // 3. 장비 — 가장 잘 맞는 하나만 적용한다. 장비를 쌓아 판정을 무너뜨릴 수 없게.
  let bestItem = null;
  let bestItemValue = 0;
  for (const inv of state.inventory) {
    if (inv.uses !== null && inv.uses <= 0) continue;
    const v = itemBonus(inv.name, tags);
    if (v > bestItemValue) {
      bestItemValue = v;
      bestItem = inv.name;
    }
  }
  if (bestItem) breakdown.push({ label: bestItem, value: bestItemValue, item: bestItem });

  // 4. 동료 보조 — 마찬가지로 가장 큰 하나.
  let bestAlly = null;
  let bestAllyValue = 0;
  for (const c of Object.values(state.companions)) {
    const v = companionAssist(c, tags);
    if (v > bestAllyValue) {
      bestAllyValue = v;
      bestAlly = c;
    }
  }
  if (bestAlly) breakdown.push({ label: `${bestAlly.name} 지원`, value: bestAllyValue, companion: bestAlly.id });

  // 4.5 빛.
  //
  // 유적 안의 모든 서술은 램프가 있다는 전제로 쓰여 있다. 그것이 맞다 —
  // 아무도 빛 없이 무덤에 들어가지 않는다. 그런데 규칙에는 그 전제가 없어서,
  // 시장을 건너뛴 사람이 성냥 한 개비로 쐐기문자를 읽었다.
  //
  // 막지는 않는다. 어두운 곳에서 빛 없이 하는 일은 그냥 어려울 뿐이다.
  // 그리고 그 사실이 판정마다 화면에 뜬다.
  if (opts.dark && !hasLight(state)) {
    breakdown.push({ label: '빛이 없다', value: -DARK_PENALTY });
  }

  // 5. 상황 보정 — 콘텐츠가 직접 지정한다.
  //    함수를 주면 상태를 보고 정한다. "미리 살펴둔 사람이 유리하다" 같은 규칙이 여기 걸린다.
  const situational = typeof check.bonus === 'function' ? check.bonus(state) : check.bonus;
  if (situational) {
    breakdown.push({ label: check.bonusLabel || '상황', value: situational });
  }

  // 6. 상태 페널티와 위험도 압박 — 둘은 함께 한도를 갖는다.
  //
  // 중상 -2, 공황 -2, 위험도 +2 가 한꺼번에 걸리면 어떤 판정도 통하지 않고,
  // 실패는 다시 상태와 위험도를 악화시킨다. 그 고리에 들어가면 나올 방법이 없다.
  // 그래서 불이익의 합에 천장을 둔다. 바닥에서도 손은 남겨 둔다.
  const cond = conditionPenalty(state);
  let condValue = cond.value;
  let pressure = dangerPressure(state.danger);

  const stack = -condValue + pressure;
  let relieved = 0;
  if (stack > MAX_PENALTY_STACK) {
    relieved = stack - MAX_PENALTY_STACK;
    // 상황(위험도)부터 덜어낸다. 몸에 붙은 것은 마지막까지 남는다.
    const fromPressure = Math.min(relieved, pressure);
    pressure -= fromPressure;
    condValue += relieved - fromPressure;
  }

  if (condValue) breakdown.push({ label: cond.reasons.join('·'), value: condValue });
  if (relieved) breakdown.push({ label: '한계까지 몰린 사람의 집중', value: 0, relief: relieved });

  const modifier = breakdown.reduce((sum, b) => sum + b.value, 0);

  // 목표값에는 위험도 압박과 난이도가 더해진다.
  const shift = getDifficulty(state.difficulty).targetShift;
  const target = Math.max(5, (check.target ?? 12) + pressure + shift);

  return {
    modifier,
    target,
    baseTarget: check.target ?? 12,
    pressure,
    difficultyShift: shift,
    breakdown,
    usedItem: bestItem,
  };
}

/** 판정에 쓴 소모성 장비를 닳게 한다. */
export function checkWear(built) {
  if (!built.usedItem) return null;
  return built.usedItem;
}

/** 난이도 표시용 이름. */
export function difficultyLabel(target) {
  if (target <= 8) return '쉬움';
  if (target <= 12) return '보통';
  if (target <= 15) return '어려움';
  if (target <= 18) return '매우 어려움';
  return '지극히 어려움';
}
