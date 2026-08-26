// 신뢰와 배신 (기획서 18절).
//
// 지금까지 신뢰도는 판정 보정만 깎았다. 낮아도 불편할 뿐 아무 일도 일어나지 않았고,
// 그러면 관계를 관리할 이유가 없다. 관계가 수치가 되려면 등을 돌릴 수도 있어야 한다.
//
// 배신은 벌이 아니라 결과다. 그래서 세 가지 원칙을 지킨다.
//
//   1. 예고된다 — 신뢰도가 낮으면 화면에 경고가 뜬다. 뒤통수를 치지 않는다.
//   2. 이유가 있다 — 무엇이 그 사람을 그렇게 만들었는지 문장으로 남긴다.
//   3. 되돌릴 수 있다 — 떠나기 전까지는 신뢰를 회복할 시간이 있다.

import { subj, topic, obj } from '../korean.js';

/** 배신이 일어날 수 있는 순간. */
export const MOMENT = {
  CHAPTER: 'chapter', // 다음 지역으로 떠나기 전
  RELIC: 'relic', // 핵심 유물을 손에 넣은 직후
  COMBAT: 'combat', // 지원을 요청했을 때
};

/** 신뢰도가 이 아래면 위태롭다. 화면에 경고가 뜬다. */
export const SHAKY_TRUST = 1;
export const SHAKY_AFFINITY = 1;

/**
 * 이 사람은 지금 흔들리는가.
 * 신뢰도가 바닥이고 호감도도 낮아야 한다. 둘 중 하나만 낮으면 버틴다 —
 * 신뢰하지 않아도 좋아하면 남고, 좋아하지 않아도 믿으면 남는다.
 *
 * 문턱은 시작값보다 아래에 있다. 어느 동료도 합류하는 순간부터 흔들리지 않는다는 뜻이다.
 * 배신은 플레이어가 만든 결과여야지, 캐릭터에 붙은 태그여서는 안 된다.
 */
export function isShaky(companion) {
  if (!companion || !companion.present) return false;
  return companion.trust <= SHAKY_TRUST && companion.affinity <= SHAKY_AFFINITY;
}

/** 흔들리는 사람이 실제로 등을 돌릴 확률. */
function risk(companion, moment) {
  if (!isShaky(companion)) return 0;
  const base = companion.trust <= 0 ? 0.55 : 0.3;
  const bonus = companion.injured ? 0.15 : 0;
  const byMoment = { chapter: 1, relic: 0.8, combat: 0.6 }[moment] ?? 1;
  return Math.min(0.8, (base + bonus) * byMoment);
}

const KINDS = {
  // 조용히 떠난다. 가장 흔하고 가장 아프다.
  leave: {
    id: 'leave',
    text: (c) => [
      `${topic(c.name)} 아침에 없었다.`,
      '짐도, 인사도, 쪽지도 없다. 남은 것은 접힌 담요뿐이다.',
      '언제부터 떠날 생각이었는지는 알 수 없다. 물어볼 사람이 없으니까.',
    ],
    effects: (c) => ({ companion: { id: c.id, present: false } }),
  },
  // 값나가는 것을 하나 가져간다.
  take: {
    id: 'take',
    text: (c, item) => [
      `${subj(c.name)} 떠났다. 그리고 ${item}도 함께 사라졌다.`,
      '가져갈 만한 것을 정확히 골랐다. 무엇이 값나가는지 옆에서 다 봤을 테니까.',
      '탓할 말이 떠오르지 않는다. 그 사람 몫을 제때 치른 적이 없다.',
    ],
    effects: (c, item) => ({
      companion: { id: c.id, present: false },
      removeItems: [item],
    }),
  },
  // 판다. 크레인이든 총독부든, 사는 쪽은 늘 있다.
  sell: {
    id: 'sell',
    text: (c) => [
      `${topic(c.name)} 남았다. 그것이 더 나쁜 쪽이라는 것을 사흘 뒤에 알게 된다.`,
      '당신이 어디를 파는지, 무엇을 찾았는지 이미 다른 쪽이 알고 있었다.',
      '누가 말했는지는 물을 필요가 없다. 이 자리에 있던 사람은 넷뿐이었다.',
    ],
    effects: (c) => ({ danger: 4, companion: { id: c.id, trust: -1 } }),
  },
};

/**
 * 배신을 판정한다.
 *
 * @param {object} state
 * @param {object} rng
 * @param {string} moment MOMENT 중 하나
 * @returns {{ companion, kind, text, effects } | null}
 */
export function checkBetrayal(state, rng, moment) {
  const shaky = Object.values(state.companions).filter((c) => isShaky(c));
  if (!shaky.length) return null;

  // 가장 흔들리는 사람부터. 같으면 먼저 합류한 사람.
  shaky.sort((a, b) => a.trust + a.affinity - (b.trust + b.affinity));
  const c = shaky[0];

  if (!rng.chance(risk(c, moment))) return null;

  // 가져갈 만한 것이 있으면 가져가고, 남아서 파는 쪽이 더 그럴듯하면 판다.
  const worth = state.inventory
    .map((i) => i.name)
    .filter((n) => ['relic', 'special'].includes(itemTier(n)));

  let kind = KINDS.leave;
  let item = null;
  if (worth.length && rng.chance(0.5)) {
    kind = KINDS.take;
    item = rng.pick(worth);
  } else if (moment === MOMENT.CHAPTER && rng.chance(0.3)) {
    kind = KINDS.sell;
  }

  return {
    companion: c,
    kind: kind.id,
    text: kind.text(c, item),
    effects: kind.effects(c, item),
  };
}

/**
 * 전투 중에 지원을 요청했을 때, 그 사람이 응하지 않을 수도 있다.
 * 등을 돌리는 것보다 가벼운 배신이지만 대가는 즉시 치러진다 — 한 턴을 잃는다.
 *
 * @returns {{ kind, companion, text, effects } | null}
 */
export function checkRefusal(companion, rng) {
  if (!isShaky(companion)) return null;
  if (!rng.chance(companion.trust <= 0 ? 0.5 : 0.25)) return null;
  return {
    kind: 'refuse',
    companion,
    text: [
      `${obj(companion.name)} 불렀다. 그가 이쪽을 봤다.`,
      '그리고 움직이지 않았다.',
      '"그건 당신 일이잖아요." 틀린 말이 아니어서 되받을 수가 없다.',
    ],
    effects: { companion: { id: companion.id, affinity: -1 } },
  };
}

// 아이템 등급은 콘텐츠가 안다. 순환 참조를 피하려고 주입받는다.
let itemTierFn = () => 'gear';
export function setItemTier(fn) {
  itemTierFn = fn;
}
function itemTier(name) {
  return itemTierFn(name);
}

/** 이 사람에 대한 경고 한 줄. */
export function warningFor(companion) {
  return companion.trust <= 0
    ? `${topic(companion.name)} 더 이상 당신을 믿지 않는다. 다음 항구에서 내릴 것이다.`
    : `${subj(companion.name)} 눈을 잘 마주치지 않는다. 아직 늦지 않았을 것이다.`;
}

/** 관계가 다시 붙었을 때의 한 줄. 되돌릴 수 있다는 것도 보여야 한다. */
export function recoveryFor(companion) {
  return `${subj(companion.name)} 다시 당신 쪽을 본다. 무슨 말인가 하려다 말았다.`;
}

/** 화면에 띄울 경고. 흔들리는 사람이 있으면 미리 알려 준다. */
export function warnings(state) {
  return Object.values(state.companions)
    .filter((c) => isShaky(c))
    .map((c) => ({ id: c.id, name: c.name, text: warningFor(c) }));
}
