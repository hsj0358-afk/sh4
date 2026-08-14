// 보정치 계산. 판정 하나가 어떤 근거로 그 숫자가 되었는지 전부 남긴다.
// 플레이어가 "왜 이 숫자인가"를 항상 확인할 수 있어야 한다는 원칙(기획서 7-3).

import { itemBonus } from '../content/items.js';
import { companionAssist } from '../content/companions.js';
import { conditionPenalty, dangerPressure } from './state.js';

/** 직업 고유 태그가 걸리면 +2. 기획서의 직업별 특전을 규칙으로 옮긴 것. */
const PERK_VALUE = 2;

/**
 * @param {object} state
 * @param {object} check { stat, tags, target, bonus }
 * @returns {{ modifier:number, target:number, breakdown:Array<{label:string,value:number}> }}
 */
export function buildCheck(state, check) {
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

  // 5. 상황 보정 (콘텐츠가 직접 지정)
  if (check.bonus) breakdown.push({ label: check.bonusLabel || '상황', value: check.bonus });

  // 6. 상태 페널티
  const cond = conditionPenalty(state);
  if (cond.value) breakdown.push({ label: cond.reasons.join('·'), value: cond.value });

  const modifier = breakdown.reduce((sum, b) => sum + b.value, 0);

  // 목표값에는 위험도 압박이 더해진다.
  const pressure = dangerPressure(state.danger);
  const target = (check.target ?? 12) + pressure;

  return {
    modifier,
    target,
    baseTarget: check.target ?? 12,
    pressure,
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
